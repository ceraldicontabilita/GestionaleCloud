from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_AND_PRODUCT_TEXT = (
    REPOSITORY_ROOT / "app",
    REPOSITORY_ROOT / "frontend" / "src",
    REPOSITORY_ROOT / "docs",
    REPOSITORY_ROOT / "scripts",
)
FORBIDDEN_TOKEN = "mongo" + "db"
# App esterne portate pari pari dentro il gestionale (decisione del titolare
# 03/09/2026): conservano il proprio codice, compresa l'API Mongo in memoria
# (mongomock) di Lotti. Non sono l'archivio del gestionale, la guardia non le
# riguarda.
APP_PORTATE_PARI_PARI = {"lotti", "menu", "hr"}


def test_drive_only_product_has_no_forbidden_backend_references():
    offenders = []

    for root in RUNTIME_AND_PRODUCT_TEXT:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".py", ".js", ".jsx", ".ts", ".tsx"}:
                continue
            relative = path.relative_to(REPOSITORY_ROOT).parts
            if len(relative) > 1 and relative[0] == "app" and relative[1] in APP_PORTATE_PARI_PARI:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            if FORBIDDEN_TOKEN in text:
                offenders.append(path.relative_to(REPOSITORY_ROOT).as_posix())

    assert offenders == [], (
        "Drive/Sheets è l'unico archivio operativo; rimossi i riferimenti al "
        f"backend escluso. File da correggere: {offenders}"
    )
