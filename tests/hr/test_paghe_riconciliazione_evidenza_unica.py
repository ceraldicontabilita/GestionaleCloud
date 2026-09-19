"""La riconciliazione paghe di HR usa lo stesso motore dell'ERP.

Fino al 19/09/2026 `services/paghe_riconciliazione.py` esisteva in due copie e
la deriva toccava il punto piu' delicato: **quali movimenti bancari valgono
come prova di pagamento**. La copia HR cercava senza il filtro
`_solo_evidenza_ufficiale` e senza il vincolo `in_attesa_estratto_ufficiale`,
quindi poteva saldare un F24 con una riga che l'ERP esclude di proposito.

Non era un ramo morto: `POST /api/paghe/riconcilia-f24`
(`app/hr/routers/f24_parser.py`) chiamava proprio quella copia.
"""
import asyncio

from app.hr.services import paghe_riconciliazione as copia_hr
from app.services import paghe_riconciliazione as motore
from app.services.bank_evidence import filtro_solo_evidenza_ufficiale


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


class _Collection:
    def __init__(self, registro, nome):
        self._registro, self._nome = registro, nome

    async def find_one(self, query, *a, **k):
        self._registro.setdefault(self._nome, []).append(query)
        return None

    async def count_documents(self, query, *a, **k):
        self._registro.setdefault(self._nome, []).append(query)
        return 0


class _Db:
    """Registra le query senza restituire nulla: qui conta il filtro, non l'esito."""

    def __init__(self):
        self.query = {}

    def __getattr__(self, nome):
        return _Collection(self.query, nome)

    def __getitem__(self, nome):
        return _Collection(self.query, nome)


def _contiene(struttura, atteso) -> bool:
    if struttura == atteso:
        return True
    if isinstance(struttura, dict):
        return any(_contiene(v, atteso) for v in struttura.values())
    if isinstance(struttura, list):
        return any(_contiene(v, atteso) for v in struttura)
    return False


def test_la_copia_hr_e_un_re_export_del_modulo_unico():
    for nome in (
        "cerca_in_estratto_conto",
        "riconcilia_tutti_f24",
        "riconcilia_tutti_stipendi",
        "esegui_riconciliazione_paghe_completa",
    ):
        assert getattr(copia_hr, nome) is getattr(motore, nome), (
            f"{nome} sul lato HR non e' la funzione del modulo unico."
        )


def test_la_ricerca_bancaria_accetta_solo_evidenza_ufficiale():
    # Deliberatamente dal lato HR: era quello senza filtri.
    db = _Db()
    _run(copia_hr.cerca_in_estratto_conto(db, 1500.0, "2026-03-31"))

    query_ecm = db.query["estratto_conto_movimenti"]
    assert query_ecm, "nessuna ricerca sull'estratto conto"
    atteso = filtro_solo_evidenza_ufficiale()["$or"]
    assert all(_contiene(q, atteso) for q in query_ecm), (
        "Una ricerca sull'estratto conto senza il filtro di evidenza "
        f"ufficiale: {query_ecm}"
    )

    query_pnb = db.query["prima_nota_banca"]
    assert query_pnb, "nessuna ricerca in prima nota banca"
    assert all(
        q.get("in_attesa_estratto_ufficiale") == {"$ne": True} for q in query_pnb
    ), (
        "Un movimento ancora in attesa dell'estratto ufficiale non puo' "
        f"saldare un documento: {query_pnb}"
    )


def test_la_ricerca_tollera_entrambe_le_convenzioni_di_segno():
    """In estratto_conto_movimenti l'uscita e' negativa, in prima nota positiva."""
    db = _Db()
    _run(copia_hr.cerca_in_estratto_conto(db, 1500.0, "2026-03-31"))

    q = db.query["estratto_conto_movimenti"][0]
    assert _contiene(q, {"$gte": 1500.0 - 1.0, "$lte": 1500.0 + 1.0})
    assert _contiene(q, {"$gte": -(1500.0 + 1.0), "$lte": -(1500.0 - 1.0)})


def test_le_buste_sotto_cinquanta_euro_non_si_riconciliano():
    """Un netto di pochi euro e' quasi certo un valore mal letto dal PDF."""
    import inspect

    corpo = inspect.getsource(motore.riconcilia_tutti_stipendi)
    assert '"netto_mese": {"$gte": 50}' in corpo, (
        "La soglia sul netto e' sparita: senza, un numero di pagina o "
        "un'aliquota letti male dal parser vengono cercati in banca."
    )
