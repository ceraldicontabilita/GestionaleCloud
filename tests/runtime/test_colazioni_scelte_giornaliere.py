from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SQL27 = (ROOT / "frontend_colazioni" / "sql" / "supabase-27.sql").read_text(
    encoding="utf-8"
).lower()
SQL = (ROOT / "frontend_colazioni" / "sql" / "supabase-28.sql").read_text(
    encoding="utf-8"
).lower()
HTML = (ROOT / "frontend_colazioni" / "index.html").read_text(encoding="utf-8")


def test_unico_qr_con_scelte_separate_per_giorno():
    assert "create table if not exists public.bb_voucher_giorni" in SQL27
    assert "primary key(voucher_id,giorno)" in SQL27
    assert "bb_ospite_salva(text,jsonb,jsonb,date)" in SQL
    assert "il giorno scelto è fuori dal soggiorno" in SQL
    assert "non si modificano colazioni di un giorno passato" in SQL
    assert "pgiorno:G.giorno" in HTML
    assert "stesso qr" in HTML.lower()


def test_interfaccia_ospite_compatta_con_tre_azioni():
    assert "Cambia un prodotto" in HTML
    assert "Aggiungi extra" in HTML
    assert ">Allergie<" in HTML
    assert 'panel:"home"' in HTML
    assert "Solo per il ${dmy(G.giorno)}" in HTML
    assert 'G.panel!=="extra"' in HTML


def test_produzione_e_scanner_usano_la_scelta_del_giorno():
    assert "const vGiorno=(v,g)=>" in HTML
    assert ".map(v=>vGiorno(v,PDAY))" in HTML
    assert "sc:=public.bb_scelta_giorno(v.id,public.bb_oggi())" in SQL
    assert "bb_vouchers_notifica_extra" in SQL


def test_tabella_giornaliera_non_e_leggibile_dal_browser():
    assert "enable row level security" in SQL27
    assert "revoke all on public.bb_voucher_giorni from public,anon,authenticated" in SQL27
    assert "perform public.bb_limite_ospite()" in SQL
