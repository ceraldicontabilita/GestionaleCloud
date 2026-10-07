-- Outbox fatture → Lotti: l'evento porta l'id applicativo della fattura.
--
-- 07/10/2026: tutti i 69 eventi invoice.project nati dalla ricostruzione
-- dell'archivio fallivano dieci volte con «Fattura sorgente non trovata nel
-- GestionaleCloud». Il trigger pubblicava new.id, cioe' l'id di riga di
-- gestionale.documents (il vecchio _id), mentre l'applicazione identifica
-- la fattura con data->>'id' (quello usato da Prima Nota, pagamenti
-- dichiarati, Lotti). Nelle righe scritte dal runtime i due id non
-- coincidono: il worker cercava per id applicativo e non trovava niente.
--
-- Il trigger pubblica ora data->>'id' (ripiego su new.id solo se manca) e
-- gli eventi gia' in coda con l'id di riga vengono riallineati e rimessi
-- in coda una volta sola: stesso evento, stessa versione, nessun doppione.

create or replace function gestionale.tg_invoice_projection_outbox()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, gestionale, extensions
as $$
declare
  v_source_version text;
  v_fattura_id text;
begin
  if new.collection <> 'invoices'
     or coalesce(new.data->>'entity_status', '') = 'deleted'
     or lower(coalesce(new.data->>'status', '')) in ('archived', 'deleted')
     or lower(coalesce(new.data->>'stato_import', '')) = 'archivio_storico'
     or lower(coalesce(new.data->>'duplicate_review_required', 'false')) = 'true' then
    return new;
  end if;

  v_source_version := coalesce(
    nullif(new.data->>'content_hash', ''),
    encode(extensions.digest(convert_to(new.data::text, 'UTF8'), 'sha256'), 'hex')
  );
  -- L'identita' della fattura e' quella applicativa (data->>'id'): e' la
  -- chiave con cui il worker la rilegge. L'id di riga serve solo se manca.
  v_fattura_id := coalesce(nullif(new.data->>'id', ''), new.id::text);

  insert into gestionale.domain_outbox (
    event_type, aggregate_type, aggregate_id, source_version, payload
  ) values (
    'invoice.project', 'invoice', v_fattura_id, v_source_version,
    jsonb_build_object(
      'source_id', v_fattura_id,
      'content_hash', v_source_version,
      'updated_at', new.updated_at
    )
  )
  on conflict (event_type, aggregate_type, aggregate_id, source_version) do nothing;
  return new;
end;
$$;

-- Eventi gia' in coda con l'id di riga: riallineati all'id applicativo e
-- rimessi in coda. Chi ha gia' un evento equivalente con l'id giusto resta
-- com'e' (il vincolo unico lo impedirebbe comunque).
update gestionale.domain_outbox o
   set aggregate_id = d.data->>'id',
       payload = o.payload || jsonb_build_object('source_id', d.data->>'id'),
       status = 'pending', attempts = 0, available_at = now(),
       locked_at = null, lock_token = null, last_error = null, updated_at = now()
  from gestionale.documents d
 where d.collection = 'invoices'
   and d.id::text = o.aggregate_id
   and nullif(d.data->>'id', '') is not null
   and d.data->>'id' <> o.aggregate_id
   and o.event_type = 'invoice.project'
   and o.status <> 'completed'
   and not exists (
     select 1 from gestionale.domain_outbox x
      where x.event_type = o.event_type and x.aggregate_type = o.aggregate_type
        and x.aggregate_id = d.data->>'id' and x.source_version = o.source_version
   );
