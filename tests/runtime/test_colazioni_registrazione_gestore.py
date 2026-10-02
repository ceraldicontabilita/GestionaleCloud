from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "frontend_colazioni" / "index.html").read_text(encoding="utf-8")
SQL = (ROOT / "frontend_colazioni" / "sql" / "supabase-24.sql").read_text(
    encoding="utf-8"
)


def test_la_demo_non_mostra_il_login_con_pin_di_prova():
    blocco = HTML[HTML.index("async function hotelLogin"):HTML.index("async function hotelEntra")]
    assert "if(h.demo)" in blocco
    assert "Non inserire il PIN dimostrativo" in blocco


def test_condividi_demo_crea_un_invito_di_registrazione():
    blocco = HTML[HTML.index("async function condividiGestore"):HTML.index("async function invRigenera")]
    pagina = HTML[HTML.index("function pInvito"):HTML.index("async function invRigenera")]
    assert "s.demo||!!s.invito_token||!s.attivo" in blocco
    assert "bb_tit_invito_rigenera" in blocco
    assert "navigator.share" in blocco
    assert "WhatsApp" not in pagina
    assert "mailto:" not in pagina


def test_registrazione_rimuove_lo_stato_demo_e_rifiuta_i_pin_di_prova():
    assert "if s.demo then return json_build_object('ok',false,'registrazione_richiesta',true" in SQL
    assert "if ppin in ('1111','2222','3333')" in SQL
    assert "invito_token=null, demo=false" in SQL
