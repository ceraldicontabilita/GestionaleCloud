from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SQL = (ROOT / "frontend_colazioni" / "sql" / "supabase-26.sql").read_text(
    encoding="utf-8"
).lower()
HTML = (ROOT / "frontend_colazioni" / "index.html").read_text(encoding="utf-8")


def test_eventi_prenotazione_ed_extra_sono_accodati_da_trigger():
    assert "after insert on public.bb_vouchers" in SQL
    assert "after update of extra on public.bb_vouchers" in SQL
    assert "'prenotazione_hotel'" in SQL
    assert "'extra_ospite'" in SQL
    assert "on conflict(chiave) do nothing" in SQL
    assert "public.bb_tok_hash" in SQL
    assert "md5(" not in SQL


def test_coda_privata_e_rpc_riservate_al_runtime():
    assert "enable row level security" in SQL
    assert "revoke all on public.bb_notifiche_operative" in SQL
    assert "revoke all on function public.bb_accoda_notifica_voucher()" in SQL
    assert SQL.count("perform public.gc_assert_runtime_secret()") == 2
    assert "for update skip locked" in SQL


def test_produzione_mobile_usa_card_e_navigazione_senza_scroll():
    blocco = HTML[HTML.index("function prodTab()") : HTML.index("function stampaProd()")]
    assert 'class="production-item"' in blocco
    assert "<table>" not in blocco
    assert ".owner-tabs{display:grid" in HTML
    assert "overflow-x:hidden" in HTML
