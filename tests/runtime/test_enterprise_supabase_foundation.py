from pathlib import Path


MIGRATIONS = Path("supabase/migrations")


def test_migrazione_outbox_enterprise_e_versionata_nel_repository():
    sql = (MIGRATIONS / "20261006145136_enterprise_platform_foundation.sql").read_text(
        encoding="utf-8"
    ).lower()

    assert "create table if not exists gestionale.domain_outbox" in sql
    assert "unique (event_type, aggregate_type, aggregate_id, source_version)" in sql
    assert "for update skip locked" in sql
    assert "perform public.gc_assert_runtime_secret()" in sql
    assert "revoke all on table gestionale.domain_outbox" in sql


def test_archivi_hr_storici_hanno_rls_e_solo_policy_interna():
    sql = (MIGRATIONS / "20261006173153_secure_hr_legacy_tables.sql").read_text(
        encoding="utf-8"
    ).lower()
    tabelle = (
        "app_pagamenti_storico",
        "app_bonifici_duplicati_20260914",
        "app_paghe_mensili_rimosse_20260914",
        "app_dipendenti_modifiche_20260914",
        "app_bonifici_modifiche_20260914",
        "app_dipendenti_prima_20260914b",
        "app_dipendenti_prima_20260914c",
        "app_cedolini_prima_prova_20260930",
    )

    for tabella in tabelle:
        assert f"alter table hr.{tabella} enable row level security" in sql
        assert f"'{tabella}'" in sql

    assert "for all to hr_app using (true) with check (true)" in sql
    assert "to anon" not in sql
    assert "to authenticated" not in sql
