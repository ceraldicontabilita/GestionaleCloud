-- Collegamento protocollo Drive <-> documenti F24/quietanze per drive_file_id.
-- Stessa regola della migrazione 20261001175416 (collega_quietanze_f24_drive),
-- resa richiamabile dal runtime: il ruolo applicativo hr_app non legge
-- gestionale.documents, quindi passa da una funzione SECURITY DEFINER che
-- scrive solo le righe del protocollo ancora senza collegamento. Idempotente:
-- il secondo giro torna 0. La chiamano il giro della cartella unica (dopo ogni
-- svuotamento con file elaborati) e il protocollo incrementale.
create or replace function gestionale.collega_protocollo_per_drive_file_id()
returns integer
language sql
security definer
volatile
set search_path to pg_catalog
as $$
  with aggiornate as (
    update gestionale.protocollo_drive p
       set collegamento_tipo = d.collection,
           collegamento_id = d.id,
           aggiornato_il = now()
      from gestionale.documents d
     where d.collection in ('f24_unificato', 'quietanze_f24')
       and d.data->>'drive_file_id' = p.drive_id
       and p.stato = 'attivo'
       and p.collegamento_id is null
     returning 1
  )
  select count(*)::integer from aggiornate;
$$;
revoke all on function gestionale.collega_protocollo_per_drive_file_id() from public;
grant execute on function gestionale.collega_protocollo_per_drive_file_id() to hr_app;
