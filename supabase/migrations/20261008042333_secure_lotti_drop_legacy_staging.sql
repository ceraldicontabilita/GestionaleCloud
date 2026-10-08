-- 08/10/2026 — Lotti resta accessibile esclusivamente tramite le RPC
-- SECURITY DEFINER protette dal segreto applicativo. Le tabelle di staging
-- legacy sono vuote e non fanno piu' parte del prodotto: rimuoverle elimina
-- sia la superficie Data API sia qualsiasi memoria di vecchie importazioni.

alter table lotti.lotti_documents enable row level security;
alter table lotti.lotti_store_config enable row level security;

drop schema if exists legacy_staging cascade;
