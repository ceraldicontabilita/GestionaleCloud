"""Un solo archivio F24, e un solo punto di scrittura.

Il 19/09/2026 sono state rimosse le due copie di `routers/f24_parser.py`
(1.561 righe in tutto). Scrivevano nella collection `f24_pagamenti`, che in
produzione **non esiste**: misurate le collection F24 in
`gestionale.documents`, l'unica con dati e' `f24_unificato` (93 righe,
aggiornata al 15/09/2026).

La copia ERP era gia' smontata dal registro dei router e la sua `import_f24`
non aveva chiamanti: il workflow «F24_COMPLETO» che la invocava non compare
in nessun file del repository. La copia HR era montata a `/api/paghe` ma
puntava a `hr.app_f24_pagamenti`, che nello schema HR non esiste, e nessun
frontend chiamava le sue sei rotte.

L'ingest F24 vivo passa tutto da `services/f24_canonico.salva_f24`
(`document_data_saver`, `llm_document_parser`, `post_download_pipeline`).
"""
import re
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]

# `paghe_riconciliazione.riconcilia_tutti_f24` aggiorna ancora
# `f24_pagamenti`: e' tenuta per l'audit storico e non ha chiamanti, quindi
# lavora su una collection vuota. Resta l'unica eccezione ammessa.
SCRITTORI_AMMESSI = {"app/services/paghe_riconciliazione.py"}

SCRITTURA = re.compile(
    r"f24_pagamenti[\"'\]]*\s*\.\s*(insert_one|insert_many|update_one|update_many|"
    r"replace_one|delete_one|delete_many)"
)


def test_nessun_router_f24_duplicato():
    for percorso in ("app/routers/f24_parser.py", "app/hr/routers/f24_parser.py"):
        assert not (RADICE / percorso).exists(), (
            f"{percorso} e' tornato: scriveva su `f24_pagamenti`, che in "
            "produzione non esiste. L'archivio F24 e' `f24_unificato`."
        )


def test_f24_pagamenti_non_ha_nuovi_scrittori():
    colpevoli = set()
    for percorso in (RADICE / "app").rglob("*.py"):
        try:
            testo = percorso.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if SCRITTURA.search(testo):
            colpevoli.add(percorso.relative_to(RADICE).as_posix())

    nuovi = sorted(colpevoli - SCRITTORI_AMMESSI)
    assert not nuovi, (
        "Scritture nuove su `f24_pagamenti`, collection che in produzione non "
        "esiste: un F24 salvato li' non compare in nessuna lista e non conta "
        "nelle scadenze. Il punto di scrittura e' "
        "`services/f24_canonico.salva_f24`.\n  " + "\n  ".join(nuovi)
    )


def test_il_punto_di_scrittura_canonico_esiste_ed_e_usato():
    from app.services.f24_canonico import salva_f24

    assert callable(salva_f24)

    chiamanti = set()
    for percorso in (RADICE / "app").rglob("*.py"):
        try:
            testo = percorso.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if percorso.name == "f24_canonico.py":
            continue
        if "salva_f24(" in testo:
            chiamanti.add(percorso.relative_to(RADICE).as_posix())

    assert chiamanti, "nessuno chiama salva_f24: l'ingest F24 non passa piu' di li'"
