from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_AND_PRODUCT_TEXT = (
    REPOSITORY_ROOT / "app",
    REPOSITORY_ROOT / "frontend" / "src",
    REPOSITORY_ROOT / "docs",
    REPOSITORY_ROOT / "scripts",
)
FORBIDDEN_TOKEN = "mongo" + "db"


def test_drive_only_product_has_no_forbidden_backend_references():
    offenders = []

    for root in RUNTIME_AND_PRODUCT_TEXT:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".py", ".js", ".jsx", ".ts", ".tsx"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            if FORBIDDEN_TOKEN in text:
                offenders.append(path.relative_to(REPOSITORY_ROOT).as_posix())

    assert offenders == [], (
        "Drive/Sheets è l'unico archivio operativo; rimossi i riferimenti al "
        f"backend escluso. File da correggere: {offenders}"
    )
