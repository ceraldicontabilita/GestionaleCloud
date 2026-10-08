-- 17/09/2026 — La firma delle collezioni (gc_collection_versions) faceva
-- `group by collection` su tutta gestionale.documents (63 MB di heap, 1 GB
-- con i payload): con il disco saturo superava i 20 s di statement_timeout
-- e la cache tornava alla lettura completa proprio quando serviva di piu'.
-- Ora la firma vive in una tabella di 80 righe mantenuta dai trigger:
-- lettura in tempo costante, nessuna scansione.
set lock_timeout = '4s';

create table if not exists gestionale.collection_versions (
  collection text primary key,
  row_count bigint not null default 0,
  max_updated_at timestamptz
);

-- updated_at valorizzato anche in INSERT (prima solo in UPDATE).
create or replace function gestionale.tg_documents_touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  if tg_op = 'INSERT' then
    new.updated_at := coalesce(new.updated_at, now());
  else
    new.updated_at := now();
  end if;
  return new;
end;
$$;

drop trigger if exists documents_touch_updated_at on gestionale.documents;
create trigger documents_touch_updated_at
  before insert or update on gestionale.documents
  for each row execute function gestionale.tg_documents_touch_updated_at();

create or replace function gestionale.tg_documents_collection_versions()
returns trigger
language plpgsql
as $$
begin
  if tg_op = 'INSERT' then
    insert into gestionale.collection_versions as v (collection, row_count, max_updated_at)
    values (new.collection, 1, new.updated_at)
    on conflict (collection) do update
      set row_count = v.row_count + 1,
          max_updated_at = greatest(v.max_updated_at, excluded.max_updated_at);
    return new;
  elsif tg_op = 'UPDATE' then
    if new.collection is distinct from old.collection then
      update gestionale.collection_versions
         set row_count = greatest(row_count - 1, 0)
       where collection = old.collection;
      insert into gestionale.collection_versions as v (collection, row_count, max_updated_at)
      values (new.collection, 1, new.updated_at)
      on conflict (collection) do update
        set row_count = v.row_count + 1,
            max_updated_at = greatest(v.max_updated_at, excluded.max_updated_at);
    else
      update gestionale.collection_versions
         set max_updated_at = greatest(max_updated_at, new.updated_at)
       where collection = new.collection;
    end if;
    return new;
  else
    update gestionale.collection_versions
       set row_count = greatest(row_count - 1, 0),
           max_updated_at = greatest(max_updated_at, now())
     where collection = old.collection;
    return old;
  end if;
end;
$$;

drop trigger if exists documents_collection_versions on gestionale.documents;
create trigger documents_collection_versions
  after insert or update or delete on gestionale.documents
  for each row execute function gestionale.tg_documents_collection_versions();

-- Allineamento iniziale (una sola scansione, poi mai piu').
insert into gestionale.collection_versions (collection, row_count, max_updated_at)
select d.collection, count(*)::bigint, max(d.updated_at)
from gestionale.documents d
group by d.collection
on conflict (collection) do update
  set row_count = excluded.row_count,
      max_updated_at = excluded.max_updated_at;

create or replace function public.gc_collection_versions()
returns table(collection text, row_count bigint, max_updated_at timestamptz)
language plpgsql
security definer
set search_path to 'pg_catalog'
as $$
begin
  perform public.gc_assert_runtime_secret();
  return query
  select v.collection, v.row_count, v.max_updated_at
  from gestionale.collection_versions v
  where v.row_count > 0
  order by v.collection;
end;
$$;

grant execute on function public.gc_collection_versions() to anon, service_role;
