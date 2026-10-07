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


def test_outbox_fatture_pubblica_l_id_applicativo_non_quello_di_riga():
    """07/10/2026: 69 eventi invoice.project falliti perche' il trigger
    pubblicava l'id di riga (new.id) e il worker cerca data->>'id'."""
    sql = (MIGRATIONS / "20261007093926_outbox_fattura_id_applicativo.sql").read_text(
        encoding="utf-8"
    ).lower()

    assert "create or replace function gestionale.tg_invoice_projection_outbox()" in sql
    assert "coalesce(nullif(new.data->>'id', ''), new.id::text)" in sql
    assert "'invoice.project', 'invoice', v_fattura_id, v_source_version" in sql
    assert "'source_id', v_fattura_id" in sql
    # riallineamento una tantum degli eventi gia' in coda, senza doppioni
    assert "set aggregate_id = d.data->>'id'" in sql
    assert "status = 'pending', attempts = 0" in sql
    assert "not exists" in sql
