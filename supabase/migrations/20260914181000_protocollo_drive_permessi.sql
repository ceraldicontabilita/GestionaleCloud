-- Permessi minimi per il ruolo applicativo hr_app sul protocollo Drive.
--
-- Il gestionale apre Postgres con lo stesso DSN del modulo HR (ruolo hr_app),
-- che ha accesso allo schema hr ma NON a gestionale: senza questi grant il
-- giro del protocollo fallirebbe al primo INSERT. I permessi sono limitati
-- alle tre tabelle del protocollo; l'archivio documentale gestionale.documents
-- NON viene aperto in lettura a hr_app: le impronte delle fatture passano da
-- una funzione SECURITY DEFINER che espone solo (id, md5).

grant usage on schema gestionale to hr_app;
grant select, insert, update on gestionale.protocollo_drive       to hr_app;
grant select, insert, update on gestionale.protocollo_impronte    to hr_app;
grant select, insert, update on gestionale.protocollo_drive_giri  to hr_app;
grant usage, select on sequence gestionale.protocollo_drive_giri_id_seq to hr_app;
grant execute on function gestionale.md5_base64_sicuro(text) to hr_app;

-- (id, md5 dell'allegato) delle sole fatture: niente altro dell'archivio.
create or replace function gestionale.impronte_fatture()
returns table (doc_id text, md5 text)
language sql
security definer
stable
set search_path to pg_catalog
as $$
  select d.id, gestionale.md5_base64_sicuro(d.data->>'fattura_allegata')
    from gestionale.documents d
   where d.collection = 'invoices';
$$;
revoke all on function gestionale.impronte_fatture() from public;
grant execute on function gestionale.impronte_fatture() to hr_app;
