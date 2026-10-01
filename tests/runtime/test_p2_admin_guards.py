"""P2 §12 — Gli endpoint distruttivi di migrazione/manutenzione richiedono il ruolo
ADMIN (dependency get_current_admin_user). Prima erano aperti/senza controllo ruolo."""
from fastapi import FastAPI

from app.router_registry import register_all_routers
from app.utils.dependencies import get_current_admin_user
from tests.route_table import elenco_route


def _app():
    app = FastAPI()
    register_all_routers(app)
    return app


def _route_ha_admin(app, path_frag, metodo):
    for r in elenco_route(app):
        if path_frag in r.path and metodo in r.methods:
            # cerca ricorsivamente get_current_admin_user tra le dipendenze
            trovate = _raccogli_dipendenze(r.dependant)
            return get_current_admin_user in trovate
    return None


def _raccogli_dipendenze(dependant):
    out = set()
    for d in dependant.dependencies:
        if d.call:
            out.add(d.call)
        out |= _raccogli_dipendenze(d)
    return out


def test_endpoint_distruttivi_sono_admin_only():
    app = _app()
    casi = [
        ("/reset-learning", "DELETE"),
        ("/reset-dizionario", "DELETE"),
        ("/force-reimport", "POST"),
        ("/reimporta-da-filesystem", "POST"),
        ("/cleanup-orphan-movements", "POST"),
        ("/pulizia-pre-anno", "POST"),
        ("/migrazione-pulisci-bancari-cassa", "POST"),
        ("/cleanup-duplicati-forte", "POST"),
        ("/mittenti/migra-legacy", "POST"),
        ("/dizionario-email/reset", "DELETE"),
        ("/inizializza-piano-esteso", "POST"),
        ("/reset-riconciliazione", "POST"),
        # ERP-001 (19/07/2026): scrittura di massa su movimenti_banca,
        # prima richiamabile da qualunque utente autenticato non in sola
        # lettura.
        ("/apply-suggestions", "POST"),
        ("/decisioni/{decision_id}/approva", "POST"),
        ("/decisioni/{decision_id}/rifiuta", "POST"),
        ("/automazioni/ferma", "POST"),
        ("/automazioni/riprendi", "POST"),
    ]
    for frag, metodo in casi:
        res = _route_ha_admin(app, frag, metodo)
        assert res is True, f"{metodo} {frag}: manca la guardia admin (res={res})"


# ---------------------------------------------------------------------------
# Inventario delle route senza autenticazione (app.main:app, mount compresi).
#
# L'ERP e' protetto dal middleware globale per OGNI percorso /api/ che non sta in
# PUBLIC_PATHS; le sotto-app HR, Lotti e Menu vivono fuori da /api/ e si
# proteggono ciascuna con le proprie dipendenze. Una route nuova fuori dalle
# liste qui sotto fa fallire il test: o si protegge, o si aggiunge una voce con
# il motivo.
# ---------------------------------------------------------------------------
from starlette.routing import Mount  # noqa: E402

from app.middleware.authentication import (  # noqa: E402
    AuthenticationMiddleware, PUBLIC_PATHS, PUBLIC_PREFIXES,
)

_DIPENDENZE_AUTH = {
    # ERP
    "get_current_user", "get_current_admin_user", "richiedi_admin", "get_current_admin_mfa_user",
    "richiedi_api_key", "richiedi_codice_riservato", "_admin_mutui",
    # HR
    "require_admin", "require_staff", "require_gestione_hr", "get_identity",
    # Lotti
    "auth_dependency", "require_automation_or_admin",
    # Menu
    "verify_token",
}

_PUBBLICI_DI_SERVIZIO = {"/docs", "/redoc", "/openapi.json", "/robots.txt", "/sitemap.xml", "/favicon.ico"}

# percorso -> (metodi ammessi, motivo). ERP, senza token per costruzione.
_ERP_SENZA_TOKEN = {
    "/": ({"GET"}, "pagina di benvenuto/SPA: nessun dato"),
    "/health": ({"GET"}, "liveness per Render"),
    "/api/health": ({"GET"}, "liveness per Render"),
    "/api/ping": ({"GET"}, "liveness"),
    "/api/sezioni": ({"GET"}, "mappa del sito: solo nomi e percorsi"),
    "/api/sezioni/": ({"GET"}, "mappa del sito: solo nomi e percorsi"),
    "/api/auth/verify": ({"GET"}, "verifica da se' il token (401 se assente)"),
    "/api/auth/logout": ({"POST"}, "chiude la sessione di chi la porta"),
    "/api/auth/pin-login": ({"POST"}, "login: nasce qui la sessione, limitato per tentativi"),
    "/api/auth/mfa/verify-login": ({"POST"}, "seconda fase del login: challenge firmata piu' OTP"),
    "/api/banca/enable-banking/callback": ({"GET"}, "ritorno dalla banca: vale solo con lo state monouso"),
    "/privacy": ({"GET"}, "pagina legale"),
    "/terms": ({"GET"}, "pagina legale"),
    "/data-deletion": ({"GET"}, "pagina legale"),
    "/api/privacy": ({"GET"}, "pagina legale"),
    "/api/terms": ({"GET"}, "pagina legale"),
    "/api/data-deletion": ({"GET"}, "pagina legale"),
    "/lotti": ({"GET", "HEAD"}, "redirect al prefisso con barra"),
    "/menu": ({"GET", "HEAD"}, "redirect al prefisso con barra"),
    "/hr": ({"GET", "HEAD"}, "redirect al prefisso con barra"),
    "/convenzioni": ({"GET", "HEAD"}, "redirect al prefisso con barra"),
    "/colazioni": ({"GET"}, "redirect al vecchio indirizzo"),
    "/colazioni/{resto:path}": ({"GET"}, "redirect al vecchio indirizzo"),
    "/{full_path:path}": ({"GET"}, "SPA e file statici dell'ERP (le /api/ non passano di qui)"),
}

# (dominio, percorso) -> (metodi ammessi, motivo). Sotto-app senza dipendenza di accesso.
# Esistono solo dove il bundle del frontend e' compilato (non in CI): non sono voci morte.
_STATICHE_OPZIONALI = {
    ("hr", "/hr/{full_path:path}"): ({"GET"}, "pagine statiche dell'app HR: nessun dato, solo il bundle"),
    ("menu", "/menu/{full_path:path}"): ({"GET"}, "pagine statiche del Menu: nessun dato, solo il bundle"),
}

_SOTTOAPP_SENZA_TOKEN = {
    ("lotti", "/lotti/api/health"): ({"GET"}, "liveness"),
    ("hr", "/hr/api/health"): ({"GET"}, "liveness"),
    ("menu", "/menu/api/health"): ({"GET"}, "liveness"),
    ("hr", "/hr/api/auth/dipendenti-attivi"): ({"GET"}, "tocca il tuo nome: solo nomi, non sono un segreto"),
    ("hr", "/hr/api/auth/pin-login"): ({"POST"}, "login a PIN del portale, limitato per tentativi"),
    ("hr", "/hr/api/auth/session"): ({"GET"}, "legge il cookie ERP e risponde 401 se manca"),
    ("menu", "/menu/api/qrcode/session"): ({"GET"}, "legge il cookie ERP e risponde 401 se manca"),
    ("menu", "/menu/api/qrcode/menu-url"): ({"GET"}, "indirizzo pubblico del menu per il QR"),
    # Menu pubblico dei clienti: i 14 allergeni sono un obbligo di legge.
    ("menu", "/menu/api/menu/"): ({"GET"}, "menu pubblico"),
    ("menu", "/menu/api/menu/titolare"): ({"GET"}, "dati dell'esercente da esporre per legge"),
    ("menu", "/menu/api/menu/categories"): ({"GET"}, "menu pubblico"),
    ("menu", "/menu/api/menu/categories/{category_id}"): ({"GET"}, "menu pubblico"),
    ("menu", "/menu/api/menu/subcategories/{subcategory_id}"): ({"GET"}, "menu pubblico"),
    ("menu", "/menu/api/menu/products/{product_id}"): ({"GET"}, "menu pubblico"),
    ("menu", "/menu/api/menu/allergens"): ({"GET"}, "menu pubblico, obbligo di legge"),
    ("menu", "/menu/api/menu/search"): ({"GET"}, "menu pubblico"),
    ("menu", "/menu/api/menu/carta"): ({"GET"}, "menu pubblico"),
    ("menu", "/menu/api/sale/"): ({"GET"}, "sale da scegliere dal QR del cliente"),
    ("menu", "/menu/api/sale/{sala_id}"): ({"GET"}, "sala da scegliere dal QR del cliente"),
    ("menu", "/menu/api/orders/"): ({"POST"}, "ordine del cliente dal QR: senza token e' sempre non pagato"),
    ("menu", "/menu/api/orders/{order_id}"): ({"GET"}, "il cliente segue il proprio ordine (id non indovinabile)"),
}


def _nomi_dipendenze(dependant, out=None):
    out = set() if out is None else out
    for d in dependant.dependencies:
        if d.call:
            out.add(getattr(d.call, "__name__", ""))
        _nomi_dipendenze(d, out)
    return out


def _tutte_le_route():
    """(app, [(dominio, percorso completo, metodi, nomi dipendenze, route)]) di app.main:app."""
    import app.main as principale
    from tests.route_table import route_montate

    righe = []

    def scendi(sotto, prefisso, dominio):
        for r in route_montate(sotto):
            righe.append((dominio, prefisso + r.path, set(r.methods or ()), _nomi_dipendenze(r.dependant), r))
        for r in sotto.routes:
            if isinstance(r, Mount) and hasattr(r.app, "router"):
                scendi(r.app, prefisso + r.path, r.path.strip("/") or "erp")

    scendi(principale.app, "", "erp")
    return principale.app, righe


def test_il_middleware_globale_e_montato_sull_erp():
    app, _ = _tutte_le_route()
    assert any(m.cls is AuthenticationMiddleware for m in app.user_middleware), (
        "senza AuthenticationMiddleware ogni route /api/ dell'ERP che non dichiara una dipendenza e' aperta")


def test_le_liste_pubbliche_del_middleware_sono_motivate():
    # Un percorso nuovo nel middleware rende pubblica la route: serve il motivo qui.
    non_motivati = sorted(p for p in PUBLIC_PATHS if p not in _ERP_SENZA_TOKEN and p not in _PUBBLICI_DI_SERVIZIO)
    assert not non_motivati, f"PUBLIC_PATHS senza motivo nel test: {non_motivati}"
    assert list(PUBLIC_PREFIXES) == ["/docs", "/redoc"], (
        "un prefisso pubblico nuovo rende pubbliche tutte le route sotto")


def test_nessuna_route_erp_senza_token_fuori_dalla_lista_bianca():
    _, righe = _tutte_le_route()
    difetti = []
    for dominio, percorso, metodi, _dip, _r in righe:
        if dominio != "erp":
            continue
        pubblica_per_middleware = (percorso in PUBLIC_PATHS
                                   or any(percorso.startswith(p) for p in PUBLIC_PREFIXES)
                                   or not percorso.startswith("/api/"))
        if not pubblica_per_middleware:
            continue  # /api/ non pubblica: la chiude il middleware
        ammessa = _ERP_SENZA_TOKEN.get(percorso)
        if ammessa is None or not metodi <= ammessa[0]:
            difetti.append(f"{sorted(metodi)} {percorso}")
    assert not difetti, "route ERP raggiungibili senza token e non in lista bianca motivata: " + "; ".join(difetti)


def test_nessuna_route_di_hr_lotti_menu_senza_dipendenza_di_accesso():
    _, righe = _tutte_le_route()
    difetti = []
    for dominio, percorso, metodi, dip, _r in righe:
        if dominio == "erp" or dip & _DIPENDENZE_AUTH:
            continue
        if any(d.startswith("require_") or d in {"dipendenza", "_checker"} for d in dip):
            continue  # require_roles(...) / require_permesso(...) producono funzioni interne
        ammessa = _SOTTOAPP_SENZA_TOKEN.get((dominio, percorso)) or _STATICHE_OPZIONALI.get((dominio, percorso))
        if ammessa is None or not metodi <= ammessa[0]:
            difetti.append(f"{dominio} {sorted(metodi)} {percorso}")
    assert not difetti, "route senza autenticazione e non in lista bianca motivata: " + "; ".join(difetti)


def test_la_lista_bianca_non_contiene_voci_morte():
    _, righe = _tutte_le_route()
    esistenti_erp = {p for d, p, *_ in righe if d == "erp"}
    esistenti_sub = {(d, p) for d, p, *_ in righe if d != "erp"}
    assert not (set(_ERP_SENZA_TOKEN) - esistenti_erp), "voci ERP in lista bianca senza route"
    assert not (set(_SOTTOAPP_SENZA_TOKEN) - esistenti_sub), "voci sotto-app in lista bianca senza route"


def _chiamate(dependant, out=None):
    out = set() if out is None else out
    for d in dependant.dependencies:
        if d.call:
            out.add(d.call)
        _chiamate(d, out)
    return out


def test_ogni_route_mutui_e_solo_admin():
    """Dati finanziari, letture comprese: router Mutui e parser dei piani."""
    from app.routers.mutui import _admin_mutui

    _, righe = _tutte_le_route()
    mutui = [(p, m, r) for d, p, m, _dip, r in righe if d == "erp" and p.startswith("/api/mutui")]
    assert len(mutui) >= 8, "le route Mutui non si trovano piu': il test non verificherebbe niente"
    senza = [f"{sorted(m)} {p}" for p, m, r in mutui if _admin_mutui not in _chiamate(r.dependant)]
    assert not senza, "route Mutui senza guardia admin: " + "; ".join(senza)
