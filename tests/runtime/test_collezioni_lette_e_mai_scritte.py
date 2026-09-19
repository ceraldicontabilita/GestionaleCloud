"""Una collezione letta e mai scritta e' una lettura che non risponde mai.

Il censimento del 19/09/2026 ha contato 196 nomi di collezione usati dal
codice contro 61 esistenti davvero. La differenza da sola non e' un difetto:
in questo archivio una collezione **nasce alla prima scrittura**, quindi
«non esiste» spesso vuol dire solo «funzione mai usata».

Il difetto vero e' un altro, ed e' silenzioso: una collezione che qualcuno
**legge** e che **nessuno scrive**, in nessun punto del codice. Quella query
non potra' mai restituire niente, non dara' mai un errore, e chi la usa
prende il vuoto per una risposta. Cosi' l'email delle scadenze F24 non e'
mai partita: cercava il destinatario in `configurazioni` e in `users`.

Questa guardia non pretende di azzerare la lista di colpo — sono decisioni di
dominio, una per una. Pretende che la lista **possa solo accorciarsi**: un
nome nuovo fa fallire la CI, e uno risolto va tolto da qui.
"""
import re
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]

SCRITTURE = (
    "insert_one", "insert_many", "update_one", "update_many", "replace_one",
    "find_one_and_update", "find_one_and_replace", "bulk_write",
    "delete_one", "delete_many",
)

#: Lette da `app/` e mai scritte da `app/`, misurate il 19/09/2026.
#:
#: Le cinque senza commento **esistono in produzione con dei dati**: qualcuno
#: le riempie da fuori Python. `entity_relations` per esempio la scrive un
#: trigger PL/pgSQL (`database/trg_bank_ec_before_write.sql`). Per quelle il
#: valore di questa lista e' proprio mostrare la dipendenza invisibile.
#:
#: Le altre sono **vuote anche in produzione**: nessuno le scrive, ne' dentro
#: ne' fuori. Ogni lettura mostra il vuoto senza dirlo. Si tolgono da qui man
#: mano che si decide, una per una: o la si popola, o la lettura va via.
NOTE = {
    "ai_decision_events",
    "ai_decisions",
    "collaudo_report",
    "entity_relations",            # la scrive il trigger, non Python
    "f24_email_settings",
    "sumup_payouts",
    # — vuote anche in produzione —
    "cartelle_email_attachments",
    "contratti_noleggio",
    "dati_isa_snapshot",
    "dati_provvisori",
    "dizionario_articoli",
    "documenti_scaricati",
    "email_accounts",
    "email_allegati",
    "libro_unico_presenze",
    "liquidazioni_iva",
    "pagamenti_esiti",
    "quietanze",
    "ritenute_acconto",
    "tax_collection_claims",
    "tfr_acconti",
    "utenti_pin",
    "verbali_autovelox",
    "voci_bilancio_manuali",
    "warehouse_products",
}

#: Non e' un nome di collezione: compare dentro una docstring che spiega
#: l'adattatore HR (`db["coll"]`).
FALSI_POSITIVI = {"coll"}


def _lette_e_mai_scritte() -> set:
    lette, scritte = set(), set()
    for py in RADICE.glob("app/**/*.py"):
        if "__pycache__" in str(py):
            continue
        src = py.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(
            r'(?<![\w.])db\[\s*["\']([a-z0-9_]+)["\']\s*\]\s*\.?\s*(\w+)?', src
        ):
            (scritte if m.group(2) in SCRITTURE else lette).add(m.group(1))
    # Anche i test scrivono: una collezione popolata solo dai test resta vuota
    # in produzione, quindi qui conta soltanto cio' che scrive `app/`.
    return lette - scritte - FALSI_POSITIVI


def test_nessuna_collezione_letta_e_mai_scritta_in_piu() -> None:
    nuove = sorted(_lette_e_mai_scritte() - NOTE)
    assert not nuove, (
        "Collezioni lette che nessuno scrive: la query non potra' mai "
        f"restituire niente e non dara' errore. {nuove}"
    )


def test_la_lista_puo_solo_accorciarsi() -> None:
    risolte = sorted(NOTE - _lette_e_mai_scritte())
    assert not risolte, (
        "Queste non sono piu' orfane: toglierle da NOTE, cosi' la guardia "
        f"resta stretta. {risolte}"
    )


def test_il_destinatario_f24_non_dipende_piu_solo_da_quelle_due() -> None:
    """Controprova del difetto chiuso: `configurazioni` e `users` restano in
    lista, ma l'email ora ha una terza fonte che esiste davvero."""
    sorgente = (RADICE / "app" / "services" / "f24_scadenze_notifiche.py").read_text(
        encoding="utf-8"
    )
    assert "ADMIN_EMAIL" in sorgente
