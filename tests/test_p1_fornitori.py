"""P1 §5.7 — Fornitori: canonica UNICA `fornitori`. Tutti gli alias inglesi
(`Collections.SUPPLIERS`, `COLL_SUPPLIERS`, `SupplierCollections.SUPPLIERS`) risolvono
a `fornitori`; regola cardine del prompt: il POST /api/suppliers pubblico NON deve
scrivere nella collezione `suppliers`."""
import pathlib

from app.db_collections import COLL_FORNITORI, COLL_SUPPLIERS
from app.database import Collections
from app.services.suppliers.constants import Collections as SupplierCollections

APP = pathlib.Path(__file__).resolve().parent.parent / "app"


def test_alias_risolvono_a_fornitori():
    assert COLL_FORNITORI == "fornitori"
    assert COLL_SUPPLIERS == "fornitori"
    assert Collections.SUPPLIERS == "fornitori"
    assert SupplierCollections.SUPPLIERS == "fornitori"


def test_nessuna_scrittura_su_suppliers_letterale():
    offenders = []
    for p in APP.rglob("*.py"):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for op in (".insert_one", ".insert_many", ".update_one",
                       ".update_many", ".replace_one", ".bulk_write", ".delete_one"):
                if f'db["suppliers"]{op}' in line or f"db['suppliers']{op}" in line \
                        or f'get_collection("suppliers"){op}' in line:
                    offenders.append(f"{p.relative_to(APP)}:{i}")
    assert offenders == [], f"scritture vietate sulla collection suppliers: {offenders}"
