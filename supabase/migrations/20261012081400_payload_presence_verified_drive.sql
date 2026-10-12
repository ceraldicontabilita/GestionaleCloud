-- La presenza del PDF segue anche il riferimento Drive con impronta registrata.
-- Nessun documento, stato di pagamento o permesso viene modificato.
create or replace function public.gc_payload_stato(p_data jsonb, p_fields text[])
returns jsonb language sql immutable set search_path to pg_catalog
as $function$
  select coalesce(jsonb_object_agg(f, case
      when nullif(btrim(p_data #>> array['_drive_payloads', f, 'drive_file_id']), '') is not null
        and (p_data #>> array['_drive_payloads', f, 'md5']) ~* '^[0-9a-f]{32}$'
        then 'pieno'
      when p_data is null or not (p_data ? f) then 'assente'
      when jsonb_typeof(p_data -> f) = 'null' then 'nullo'
      when jsonb_typeof(p_data -> f) = 'string' then
        case when (p_data ->> f) = '' then 'vuoto' else 'pieno' end
      when jsonb_typeof(p_data -> f) = 'array' then
        case when jsonb_array_length(p_data -> f) = 0 then 'vuoto' else 'pieno' end
      when jsonb_typeof(p_data -> f) = 'object' then
        case when (p_data -> f) = '{}'::jsonb then 'vuoto' else 'pieno' end
      else 'pieno' end), '{}'::jsonb)
  from unnest(coalesce(p_fields, array[]::text[])) as f;
$function$;
