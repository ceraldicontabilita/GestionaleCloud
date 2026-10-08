-- 08/10/2026 — PostgreSQL non crea automaticamente indici sulle colonne FK.
-- Indicizziamo tutte le FK dei domini applicativi: join, controlli di
-- integrita' e cancellazioni della riga padre non devono scandire la tabella
-- figlia. Auth e Storage restano gestiti dalle migrazioni Supabase.

do $$
declare
  fk record;
  index_name text;
begin
  for fk in
    select
      ns.nspname as schema_name,
      rel.relname as table_name,
      con.conname,
      string_agg(format('%I', att.attname), ', ' order by key.ord) as columns_sql,
      string_agg(att.attname, '_' order by key.ord) as columns_name
    from pg_constraint con
    join pg_class rel on rel.oid = con.conrelid
    join pg_namespace ns on ns.oid = rel.relnamespace
    cross join lateral unnest(con.conkey) with ordinality key(attnum, ord)
    join pg_attribute att on att.attrelid = rel.oid and att.attnum = key.attnum
    where con.contype = 'f'
      and (
        ns.nspname in ('cassa', 'catalogo', 'gestionale', 'hr', 'lotti', 'menu', 'verifica')
        or (ns.nspname = 'public' and rel.relname like 'bb\_%' escape '\')
      )
      and not exists (
        select 1
        from pg_index idx
        where idx.indrelid = con.conrelid
          and con.conkey <@ idx.indkey::smallint[]
      )
    group by ns.nspname, rel.relname, con.conname, con.conkey
  loop
    index_name := left(fk.table_name || '_' || fk.columns_name || '_fk_idx', 63);
    execute format(
      'create index if not exists %I on %I.%I (%s)',
      index_name, fk.schema_name, fk.table_name, fk.columns_sql
    );
  end loop;
end $$;
