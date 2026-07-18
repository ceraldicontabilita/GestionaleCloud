"""P1 §5.9 — Magazzino: GestionaleCloud non usa la giacenza fisica. Nessuna NUOVA
scrittura (insert/update/replace/bulk) sulle collezioni di giacenza elencate nel
prompt. (I cascade `delete_many` di pulizia su warehouse_stocks sono ammessi: non
creano giacenza; le collezioni condivise NON vengono droppate.)"""
import pathlib

APP = pathlib.Path(__file__).resolve().parent.parent / "app"

GIACENZA = [
    "warehouse_stocks",
    "warehouse_products",
    "magazzino",
    "magazzino_articoli",
    "magazzino_movimenti",
    "movimenti_magazzino",
]

WRITE_OPS = (".insert_one", ".insert_many", ".update_one", ".update_many",
             ".replace_one", ".bulk_write")


def test_nessuna_nuova_scrittura_giacenza():
    offenders = []
    for p in APP.rglob("*.py"):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for coll in GIACENZA:
                for op in WRITE_OPS:
                    if f'db["{coll}"]{op}' in line or f"db['{coll}']{op}" in line \
                            or f'get_collection("{coll}"){op}' in line:
                        offenders.append(f"{p.relative_to(APP)}:{i} -> {coll}{op}")
    assert offenders == [], f"nuove scritture di giacenza vietate (§5.9): {offenders}"
