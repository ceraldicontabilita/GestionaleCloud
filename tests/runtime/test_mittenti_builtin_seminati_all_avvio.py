"""Guardia: i mittenti istituzionali esistono dopo la connessione all'archivio.

`Database._ensure_builtin_senders()` esisteva dal giorno in cui e' stata
scritta, ma **non la chiamava nessuno**: zero riferimenti in tutto il
repository. Nessun errore, nessuna traccia — solo silenzio, come il nome di
campo sbagliato della regola 11 di CLAUDE.md.

Il costo, misurato sui dati veri il 20/09/2026: `mittenti_email` **vuota**, zero
righe. `senders_attendibili()` restituiva sempre l'insieme vuoto, e lo scanner
dei verbali si fermava alla prima riga —

    [SCHEDULER-VERBALI-GMAIL] {'email_scansionate': 0, ...,
     'errori': ['Nessun mittente attendibile per i verbali']}

— ogni 30 minuti, in un log che nessuno legge. Nessun verbale della Polizia
Locale, di ASIA, della Prefettura o di Arval e' mai stato acquisito dalla posta,
e nemmeno le dimissioni telematiche del Ministero del Lavoro, che fanno
scattare la scadenza UNILAV a 5 giorni.

Il rifiuto in se' e' giusto: una whitelist vuota deve dare zero download, non
scaricare da chiunque (fail-closed). Il difetto e' che la whitelist non veniva
mai riempita.

Questa guardia prova il comportamento, non il testo del sorgente: connette un
archivio finto e guarda cosa c'e' dentro `mittenti_email` quando ha finito.
"""
import asyncio

import pytest

from app.database import Database
from app.services.mittenti import BUILTIN_MITTENTI


class _Esito:
    def __init__(self, inserito):
        self.upserted_id = "nuovo" if inserito else None


class _Collezione:
    def __init__(self):
        self.documenti = {}

    async def update_one(self, filtro, update, upsert=False):
        chiave = (filtro["pattern"], filtro["canale"])
        nuovo = chiave not in self.documenti
        if nuovo:
            self.documenti[chiave] = dict(update["$setOnInsert"])
        return _Esito(nuovo)


class _ArchivioFinto:
    """Il minimo che `connect_db` tocca: si idrata e serve le collezioni."""

    def __init__(self, *_args, **_kwargs):
        self.collezioni = {}
        self.idratato = False

    async def hydrate(self):
        self.idratato = True

    def __getitem__(self, nome):
        return self.collezioni.setdefault(nome, _Collezione())


@pytest.fixture
def archivio(monkeypatch):
    creati = []

    def _fabbrica(*args, **kwargs):
        finto = _ArchivioFinto(*args, **kwargs)
        creati.append(finto)
        return finto

    monkeypatch.setattr(
        "app.services.supabase_runtime_database.SupabaseRuntimeDatabase",
        _fabbrica,
    )
    monkeypatch.setattr(Database, "client", None, raising=False)
    monkeypatch.setattr(Database, "db", None, raising=False)
    yield creati


def test_connettersi_semina_i_mittenti_istituzionali(archivio):
    asyncio.run(Database.connect_db())

    assert archivio, "connect_db non ha costruito l'archivio"
    seminati = archivio[0].collezioni.get("mittenti_email")
    assert seminati is not None, (
        "Dopo la connessione `mittenti_email` non e' stata nemmeno toccata: "
        "la whitelist resta vuota e la posta non acquisisce piu' niente "
        "(verbali, dimissioni telematiche, F24, PagoPA, bollette)."
    )
    attesi = {m["pattern"] for m in BUILTIN_MITTENTI}
    trovati = {pattern for pattern, _canale in seminati.documenti}
    assert trovati == attesi, (
        "Mittenti istituzionali mancanti dopo la connessione: "
        f"{sorted(attesi - trovati)}"
    )


def test_il_seeding_non_fa_fallire_l_avvio_se_va_storto(archivio, monkeypatch):
    """Una configurazione email rotta non deve impedire l'avvio del gestionale.

    E' la ragione per cui `_ensure_builtin_senders` cattura tutto: se domani
    quella rete sparisse, un errore sui mittenti spegnerebbe la contabilita'.
    """
    async def _esplode(_db):
        raise RuntimeError("collezione non raggiungibile")

    monkeypatch.setattr("app.services.mittenti.assicura_mittenti_builtin", _esplode)

    asyncio.run(Database.connect_db())  # non deve sollevare

    assert Database.db is not None, "l'archivio deve restare connesso"
