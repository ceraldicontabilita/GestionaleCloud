import pytest

from app.hr.db_supabase import SupabaseDatabase


def test_hr_collection_uses_configured_schema():
    db = SupabaseDatabase(object(), schema="hr")
    assert db["cedolini"]._sql_tab == '"hr"."app_cedolini"'


def test_hr_schema_rejects_sql_identifiers():
    with pytest.raises(ValueError):
        SupabaseDatabase(object(), schema='hr"; drop schema hr; --')
