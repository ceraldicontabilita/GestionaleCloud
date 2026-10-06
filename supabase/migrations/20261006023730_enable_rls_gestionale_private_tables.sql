-- 06/10/2026 — Protegge tutte le tabelle private dello schema gestionale.
-- Le API applicative continuano a passare dalle RPC SECURITY DEFINER.

alter table gestionale.runtime_api_keys enable row level security;
alter table gestionale.documents enable row level security;
alter table gestionale.collection_versions enable row level security;
alter table gestionale.protocollo_drive enable row level security;
alter table gestionale.protocollo_impronte enable row level security;
alter table gestionale.protocollo_drive_giri enable row level security;
alter table gestionale.documents_rimossi_20260914 enable row level security;
alter table gestionale.corrispettivi_iva_prima_20260914 enable row level security;
alter table gestionale.documents_menu_rimossi_20260915 enable row level security;
alter table gestionale.fatture_pre2026_rimosse_20260920 enable row level security;
alter table gestionale.documents_prima_prova_20260930 enable row level security;

create policy hr_app_internal_access
on gestionale.protocollo_drive
for all
to hr_app
using (true)
with check (true);

create policy hr_app_internal_access
on gestionale.protocollo_impronte
for all
to hr_app
using (true)
with check (true);

create policy hr_app_internal_access
on gestionale.protocollo_drive_giri
for all
to hr_app
using (true)
with check (true);
