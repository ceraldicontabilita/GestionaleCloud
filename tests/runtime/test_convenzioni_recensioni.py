import asyncio
from pathlib import Path

import pytest

from app.services import convenzioni_recensioni as servizio


ROOT = Path(__file__).resolve().parents[2]


def test_interfaccia_canali_e_consensi_espliciti_separati():
    html = (ROOT / "frontend_colazioni" / "index.html").read_text(encoding="utf-8")

    assert "Invia al cliente con WhatsApp" in html
    assert "Copia link per NFC" in html
    assert 'linkOspite(id,"whatsapp")' in html
    assert 'linkOspite(id,"qr")' in html
    assert "copiaCanale('${id}','nfc')" in html
    assert "copiaCanale('${id}','wifi')" in html
    assert 'id="geo_ok" type="checkbox"' in html
    assert 'id="wa_ok" type="checkbox"' in html
    assert 'id="geo_ok" type="checkbox" checked' not in html
    assert 'id="wa_ok" type="checkbox" checked' not in html
    assert "navigator.geolocation.getCurrentPosition" in html
    assert 'eventoOspite("geolocalizzazione","revocato")' in html
    assert 'eventoOspite("whatsapp","revocato")' in html
    assert 'p.google_url||RECENSIONE_GOOGLE' in html
    assert 'p.tripadvisor_url||RECENSIONE_TRIPADVISOR' in html
    assert 'f("review_invite_delay_minutes"' in html


def test_migrazione_protegge_dati_e_registra_audit_e_coda():
    sql = (
        ROOT
        / "supabase"
        / "migrations"
        / "20261001143000_convenzioni_consensi_recensioni.sql"
    ).read_text(encoding="utf-8")

    for tabella in (
        "bb_ospite_aperture",
        "bb_ospite_consensi",
        "bb_ospite_posizioni",
        "bb_ospite_contatti",
        "bb_voucher_recensioni_inviti",
        "bb_voucher_recensioni_click",
    ):
        assert f"alter table public.{tabella} enable row level security" in sql
    assert "informativa_versione" in sql
    assert "struttura_id" in sql
    assert "avvenuto_il timestamptz" in sql
    assert "delete from public.bb_ospite_posizioni" in sql
    assert "consenso_attivo=false" in sql
    assert "for update skip locked" in sql
    assert "perform public.gc_assert_runtime_secret()" in sql
    assert "if eventi_ora>=120" in sql
    assert "'review_google_url','review_tripadvisor_url'" in sql
    assert "'msg_invito','sumup_merchant_code','supplemento_tavolo'" in sql


def test_numero_whatsapp_cifrato_e_ripristinabile(monkeypatch):
    monkeypatch.setattr(servizio.settings, "WHATSAPP_REVIEW_DATA_KEY", "ab" * 32)
    cifrato, impronta, finale = servizio.cifra_telefono("+39 333 123 4567")

    assert "+393331234567" not in cifrato
    assert len(impronta) == 64
    assert finale == "4567"
    assert servizio.decifra_telefono(cifrato) == "+393331234567"


@pytest.mark.parametrize("numero", ["3331234567", "+00", "+39 abc", ""])
def test_numero_whatsapp_rifiuta_formati_non_internazionali(numero):
    with pytest.raises(ValueError):
        servizio.normalizza_telefono(numero)


def test_endpoint_pubblico_e_segreti_render_sono_espliciti():
    auth = (ROOT / "app" / "middleware" / "authentication.py").read_text(encoding="utf-8")
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    router = (ROOT / "app" / "routers" / "colazioni.py").read_text(encoding="utf-8")

    assert '"/api/colazioni/ospite/evento"' in auth
    assert '@router.post("/ospite/evento"' in router
    assert "WHATSAPP_REVIEW_ACCESS_TOKEN" in render
    assert "WHATSAPP_REVIEW_DATA_KEY" in render
    assert 'WHATSAPP_REVIEW_PROVIDER\n        value: "disabled"' in render


def test_worker_non_reclama_la_coda_senza_provider(monkeypatch):
    monkeypatch.setattr(servizio.settings, "WHATSAPP_REVIEW_PROVIDER", "disabled")

    async def rpc_non_deve_partire(*_args, **_kwargs):
        raise AssertionError("la coda non deve essere reclamata")

    monkeypatch.setattr(servizio, "_rpc", rpc_non_deve_partire)
    assert asyncio.run(servizio.processa_inviti_recensione()) == {
        "stato": "disattivato",
        "processati": 0,
        "inviati": 0,
    }
