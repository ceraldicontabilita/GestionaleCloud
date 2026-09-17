"""I gate devono includere tutte le sotto-app e gli hub del catalogo."""
from pathlib import Path

from scripts import audit_static, audit_architettura


def test_presenza_entrypoint_attuali_senza_vecchio_hr():
    findings = []
    audit_static.audit_required_files(findings)
    assert findings == []
    assert {path.parent.name for path in audit_static.FRONTENDS if path.name == "src"} == {
        "frontend", "frontend_lotti", "frontend_menu", "frontend_hr",
    }


def test_router_delle_quattro_app_inclusi():
    relative = {path.relative_to(audit_architettura.APP).as_posix()
                for path in audit_architettura.ROUTER_ROOTS}
    assert relative == {"routers", "lotti/routers", "hr/routers", "menu/routes"}
    assert all(path.is_dir() for path in audit_architettura.ROUTER_ROOTS)
