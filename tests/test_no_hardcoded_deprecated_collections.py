"""
Piano residuo P1 §12 — blocca l'uso di collection MongoDB deprecate.

Le collezioni sotto sono deprecate/legacy (vedi
`app/db_collections.py::COLLEZIONI DEPRECATE - NON USARE` e le costanti
marcate LEGACY/DEPRECATA): scrivere o leggere da queste per errore riporta
in vita dati vuoti o sbagliati (es. `employees`/`warehouse_stocks` sono
staccate dai flussi reali — vedi bug corretti in
app/services/trattenute_verbali_service.py e app/routers/paypal_statements.py,
audit 14/07/2026). Le collezioni "LEGACY/ARCHIVIO" mantenute apposta per un
flusso specifico (`indice_documenti`, `extracted_documents`,
`libro_unico_presenze`, `documenti_classificati` — quest'ultima è in realtà
già il nome canonico) NON sono in questa lista.

Eccezioni esplicite (cleanup/migrazione intenzionali, non bug):
- app/scripts/*: gli script di migrazione leggono le collezioni legacy per
  definizione.
- app/services/cascade_operations.py, app/routers/suppliers_module/base.py:
  cancellano (delete_many) anche dai residui in warehouse_stocks durante
  l'eliminazione a cascata di un fornitore — pulizia, non lettura di dati
  come fonte di verità.
- app/utils/warehouse_helpers.py: modulo orfano (0 importer in tutto il
  repo, verificato 14/07/2026) che legge warehouse_stocks con uno schema
  (descrizione/codice/giacenza) incompatibile con quello reale di
  warehouse_inventory (nome/codice_articolo_fornitore/...) — debito tecnico
  noto (memoria/PIANO_CONSOLIDAMENTO_TRACKING.md op.12): se mai viene
  ri-agganciato va riscritto, non basta cambiare il nome della collection.
"""
import os
import re

APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")

COLLEZIONI_DEPRECATE = [
    "f24", "f24_models", "movimenti_f24_banca", "estratto_conto",
    "bank_statements", "warehouse_stocks", "anagrafica_dipendenti",
    "buste_paga", "fatture_ricevute", "invoices_emesse", "payslips",
    "staff", "employees", "suppliers",
]

FILE_ESENTI = {
    os.path.normpath(os.path.join(APP_DIR, "services", "cascade_operations.py")),
    os.path.normpath(os.path.join(APP_DIR, "routers", "suppliers_module", "base.py")),
    os.path.normpath(os.path.join(APP_DIR, "utils", "warehouse_helpers.py")),
}

PATTERN = re.compile(
    r'db\[\s*["\'](' + "|".join(re.escape(c) for c in COLLEZIONI_DEPRECATE) + r')["\']\s*\]'
    r'|db\.get_collection\(\s*["\'](' + "|".join(re.escape(c) for c in COLLEZIONI_DEPRECATE) + r')["\']\s*\)'
)


def _tutti_i_file_py():
    out = []
    for root, dirs, files in os.walk(APP_DIR):
        dirs[:] = [d for d in dirs if d not in ("__pycache__",)]
        if os.path.normpath(root).startswith(os.path.normpath(os.path.join(APP_DIR, "scripts"))):
            continue
        for f in files:
            if f.endswith(".py"):
                out.append(os.path.normpath(os.path.join(root, f)))
    return out


def test_nessuna_collection_deprecata_hardcoded_fuori_dagli_script_di_migrazione():
    violazioni = []
    for path in _tutti_i_file_py():
        if path in FILE_ESENTI:
            continue
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for numero_riga, riga in enumerate(fh, start=1):
                m = PATTERN.search(riga)
                if m:
                    nome = m.group(1) or m.group(2)
                    violazioni.append(f"{path}:{numero_riga} usa la collection deprecata '{nome}'")

    assert not violazioni, (
        "Trovati riferimenti a collection MongoDB deprecate (vedi "
        "app/db_collections.py per la canonica corretta):\n" + "\n".join(violazioni)
    )
