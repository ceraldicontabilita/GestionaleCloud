-- Guardia del segreto di runtime, letta dal database con pg_get_functiondef il 02/10/2026:
-- era applicata in produzione ma mancava dal registro (la chiamano le RPC gc_* e le bb_tit_* v20/v23).
-- Il chiamante manda la chiave in chiaro nell'header x-gc-api-key; qui si confronta lo SHA-256
-- con gestionale.runtime_api_keys (solo chiavi attive). Idempotente: create or replace.
CREATE OR REPLACE FUNCTION public.gc_assert_runtime_secret()
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog'
AS $function$
declare
  supplied text;
  supplied_hash text;
begin
  supplied := coalesce(
    current_setting('request.headers', true),
    '{}'
  )::jsonb ->> 'x-gc-api-key';

  if supplied is null or length(supplied) < 32 then
    raise insufficient_privilege using message = 'accesso negato';
  end if;

  supplied_hash := encode(extensions.digest(supplied, 'sha256'), 'hex');
  if not exists (
    select 1
    from gestionale.runtime_api_keys k
    where k.key_hash = supplied_hash and k.active
  ) then
    raise insufficient_privilege using message = 'accesso negato';
  end if;
end;
$function$;
