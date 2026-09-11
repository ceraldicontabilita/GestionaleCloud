from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_admin_technical_pages_are_not_duplicated_in_global_navigation():
    nav = read("frontend/src/navigation.config.js")
    assert "{ to: '/utenti'" not in nav
    assert "{ to: '/impostazioni-ai'" not in nav
    assert "{ to: '/admin', label: 'Admin'" in nav


def test_admin_hub_keeps_shortcuts_to_users_and_ai_settings():
    admin = read("frontend/src/pages/hub/AdminHub.jsx")
    assert 'to="/utenti"' in admin
    assert 'to="/impostazioni-ai"' in admin
    assert 'data-testid="admin-shortcut-utenti"' in admin
    assert 'data-testid="admin-shortcut-ai"' in admin


def test_ai_settings_direct_route_is_admin_protected():
    main = read("frontend/src/main.jsx")
    expected = (
        '{ path: "impostazioni-ai", element: '
        '<RequireAdmin><LazyPage><ImpostazioniAI /></LazyPage></RequireAdmin> }'
    )
    assert expected in main


def test_dashboard_exposes_real_operational_shortcuts_and_counters():
    dashboard = read("frontend/src/pages/Dashboard.jsx")
    operativita = read("frontend/src/components/DashboardOperativita.jsx")

    assert "DashboardOperativita" in dashboard
    assert '<DashboardOperativita scadenze={scadenze} erroriApi={erroriApi} />' in dashboard
    assert "api" in operativita
    assert ".get('/api/alerts/summary'" in operativita
    assert "scadenze?.scadenze" in operativita

    for route in (
        "/dashboard/alerts",
        "/documenti/import",
        "/riconciliazione",
        "/scadenze",
        "/strumenti/commercialista",
    ):
        assert route in operativita
