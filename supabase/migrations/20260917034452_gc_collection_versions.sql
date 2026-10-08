-- 17/09/2026 — cache incrementale del runtime (richiesta del titolare: "il sito
-- deve lasciare i dati scritti, non ricaricarli ogni volta da Supabase").
--
-- L'applicazione tiene in memoria la versione "leggera" di ogni collezione
-- (senza XML/PDF) e, prima di servirla, chiede a Supabase soltanto la firma
-- di ogni collezione (conteggio + ultimo updated_at): se la firma non e'
-- cambiata non legge nulla; se e' cambiata scarica solo i documenti
-- aggiornati dopo l'ultima lettura. Le tre parti che servono:
--   1. updated_at sempre aggiornato dal database, anche per scritture fatte
--      fuori dall'applicazione (trigger, idempotente);
--   2. indice (collection, updated_at) per firma e delta in tempo costante;
--   3. due RPC con lo stesso schema di sicurezza delle altre gc_*.

create or replace function gestionale.tg_documents_touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists documents_touch_updated_at on gestionale.documents;
create trigger documents_touch_updated_at
  before update on gestionale.documents
  for each row execute function gestionale.tg_documents_touch_updated_at();

create index if not exists documents_collection_updated_at_idx
  on gestionale.documents (collection, updated_at);

-- Firma per collezione: una sola RPC per tutte le collezioni.
create or replace function public.gc_collection_versions()
returns table(collection text, row_count bigint, max_updated_at timestamptz)
language plpgsql
security definer
set search_path to 'pg_catalog'
as $$
begin
  perform public.gc_assert_runtime_secret();
  return query
  select d.collection, count(*)::bigint, max(d.updated_at)
  from gestionale.documents d
  group by d.collection
  order by d.collection;
end;
$$;

-- Delta: solo i documenti modificati dopo p_since (paginato, senza payload).
create or replace function public.gc_fetch_collection_since(
  p_collection text,
  p_since timestamptz,
  p_offset integer default 0,
  p_limit integer default 500,
  p_exclude_fields text[] default array[]::text[]
)
returns jsonb
language plpgsql
security definer
set search_path to 'pg_catalog'
as $$
declare result jsonb;
begin
  perform public.gc_assert_runtime_secret();
  if coalesce(btrim(p_collection), '') = '' then
    raise invalid_parameter_value using message = 'collezione mancante';
  end if;
  if p_offset < 0 or p_limit < 1 or p_limit > 500 then
    raise invalid_parameter_value using message = 'paginazione non valida';
  end if;
  if coalesce(array_length(p_exclude_fields, 1), 0) > 32 then
    raise invalid_parameter_value using message = 'troppe esclusioni';
  end if;

  set local statement_timeout = 0;
  set local work_mem = '128MB';
  select coalesce(jsonb_agg(page.document order by page.updated_at, page.id), '[]'::jsonb)
  into result
  from (
    select d.id, d.updated_at,
           (d.data - coalesce(p_exclude_fields, array[]::text[]))
             || jsonb_build_object('_id', d.id) as document
    from gestionale.documents d
    where d.collection = p_collection
      and (p_since is null or d.updated_at > p_since)
    order by d.updated_at, d.id
    offset p_offset
    limit p_limit
  ) page;
  return result;
end;
$$;

grant execute on function public.gc_collection_versions() to anon, service_role;
grant execute on function public.gc_fetch_collection_since(text, timestamptz, integer, integer, text[]) to anon, service_role;
