"""Il repository trova il documento su entrambi gli archivi.

I due adattatori tengono la chiave in campi diversi: il runtime dell'ERP
(`services/supabase_runtime_database.py`) indicizza per `_id`, quello dell'app
HR (`app/hr/db_supabase.py`) per `id`. Fino al 19/09/2026 esistevano due
`base_repository`, e quello HR era rimasto a MongoDB: costruiva
`ObjectId(doc_id)` su identificativi testuali, sollevando `InvalidId` dentro un
`except` che lo inghiottiva.

Conseguenza misurata in produzione: l'unico utente di `hr.app_users`
(`ceraldi`, id `08d4732b-…`, un UUID) non aveva **mai** ricevuto un
`last_login`, perche' `app/hr/routers/pin_login.py` chiama `update_last_login`
a ogni accesso col PIN e quella catena finiva sempre nell'`InvalidId`.
"""
import asyncio

import pytest

from app.hr.repositories import BaseRepository as hr_base
from app.hr.repositories import UserRepository as hr_user
from app.repositories import BaseRepository as erp_base
from app.repositories import UserRepository as erp_user

UUID_HR = "08d4732b-6127-4e00-a8b6-0aedb8b97e64"


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


class _Risultato:
    def __init__(self, modified):
        self.modified_count = modified
        self.upserted_id = None


class _CollectionFinta:
    """Imita un archivio che tiene la chiave in `campo_chiave`."""

    name = "users"

    def __init__(self, documenti, campo_chiave):
        self._documenti = documenti
        self._campo = campo_chiave

    def _corrisponde(self, doc, filtro):
        if "$or" in filtro:
            return any(self._corrisponde(doc, f) for f in filtro["$or"])
        return all(doc.get(k) == v for k, v in filtro.items())

    async def find_one(self, filtro, *a, **k):
        for doc in self._documenti:
            if self._corrisponde(doc, filtro):
                return dict(doc)
        return None

    async def update_one(self, filtro, aggiornamento, upsert=False):
        for doc in self._documenti:
            if self._corrisponde(doc, filtro):
                doc.update(aggiornamento["$set"])
                return _Risultato(1)
        return _Risultato(0)


@pytest.mark.parametrize("campo_chiave", ["_id", "id"])
def test_update_by_id_funziona_su_entrambi_gli_archivi(campo_chiave):
    documenti = [{campo_chiave: UUID_HR, "username": "ceraldi"}]
    repo = hr_base(_CollectionFinta(documenti, campo_chiave))

    esito = _run(repo.update(UUID_HR, {"last_login": "2026-09-19T00:00:00Z"}))

    assert esito is True, (
        f"Aggiornamento fallito su un archivio che indicizza per "
        f"`{campo_chiave}`: l'identificativo e' testuale, non un ObjectId."
    )
    assert documenti[0]["last_login"] == "2026-09-19T00:00:00Z"


@pytest.mark.parametrize("campo_chiave", ["_id", "id"])
def test_find_by_id_non_torna_none_su_un_archivio_senza_underscore_id(campo_chiave):
    documenti = [{campo_chiave: UUID_HR, "username": "ceraldi"}]
    repo = hr_base(_CollectionFinta(documenti, campo_chiave))

    trovato = _run(repo.find_by_id(UUID_HR))

    assert trovato is not None, (
        "Documento presente ma non restituito: il vecchio `pop('_id')` senza "
        "default sollevava KeyError e l'except lo trasformava in None."
    )
    assert trovato["username"] == "ceraldi"


def test_un_solo_repository_per_i_due_rami():
    assert hr_base is erp_base
    assert hr_user is erp_user


def test_il_ruolo_predefinito_e_quello_del_vocabolario_erp():
    """`"user"` non compariva fra i ruoli validi dell'app HR: non concedeva
    nulla che `"operatore"` non conceda."""
    import inspect

    sorgente = inspect.getsource(erp_user)
    assert 'user_data["role"] = "operatore"' in sorgente
    assert 'user_data["role"] = "user"' not in sorgente
