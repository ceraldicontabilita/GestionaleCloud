from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SQL = (ROOT / "frontend_colazioni" / "sql" / "supabase-25.sql").read_text(
    encoding="utf-8"
)


def test_json_fiscale_non_dipende_da_un_altra_funzione():
    blocco = SQL[SQL.index("create or replace function public.bb_fiscali_json") :]
    assert "bb_fiscali_ok(s)" not in blocco
    assert "'completi'," in blocco
    assert "coalesce(s.ragione_sociale,'')<>''" in blocco


def test_funzioni_fiscali_hanno_schema_e_search_path_espliciti():
    assert "public.bb_fiscali_ok(s public.bb_strutture)" in SQL
    assert "public.bb_fiscali_json(s public.bb_strutture)" in SQL
    assert SQL.count("set search_path=public") == 2


def test_helper_fiscali_non_sono_rpc_pubbliche():
    assert "revoke all on function public.bb_fiscali_ok" in SQL
    assert "revoke all on function public.bb_fiscali_json" in SQL
    assert "grant execute" not in SQL
