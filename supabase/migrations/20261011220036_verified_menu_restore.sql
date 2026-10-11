-- Ripristino Menu autenticato: tutte le tabelle o nessuna, senza perdere i
-- collegamenti B&B. La simulazione valida il contenuto senza modificarlo.
create or replace function public.gc_restore_menu_backup(p_tables jsonb, p_dry_run boolean default true)
returns jsonb language plpgsql security definer set search_path = pg_catalog
as $function$
declare
  allowed constant text[] := array['menu_categories','menu_subcategories','menu_products',
    'menu_allergens','menu_qrcode_config','menu_orders','menu_warehouse_items',
    'menu_warehouse_movements','menu_allergeni_esclusioni','menu_sale'];
  tab text;
  n integer;
  pk text;
  updates text;
  equality text;
  counts jsonb := '{}'::jsonb;
begin
  perform public.gc_assert_runtime_secret();
  if jsonb_typeof(p_tables) is distinct from 'object'
    or (select count(*) from jsonb_object_keys(p_tables))<>cardinality(allowed)
    or exists(select 1 from jsonb_object_keys(p_tables) k where not(k=any(allowed))) then
    raise invalid_parameter_value using message='Backup Menu incompleto';
  end if;
  foreach tab in array allowed loop
    if jsonb_typeof(p_tables->tab) is distinct from 'array'
      or exists(select 1 from jsonb_array_elements(p_tables->tab) r where jsonb_typeof(r)<>'object') then
      raise invalid_parameter_value using message='Tabella backup non valida';
    end if;
    -- Verifica conversione di tutti i campi prima di qualunque mutazione.
    execute format('select count(*) from jsonb_populate_recordset(null::menu.%I,$1)',tab)
      using p_tables->tab;
    counts:=counts||jsonb_build_object(tab,jsonb_array_length(p_tables->tab));
  end loop;
  if exists(select 1 from public.bb_struttura_menu_prodotti b
    where not exists(select 1 from jsonb_populate_recordset(null::menu.menu_products,p_tables->'menu_products') p where p.id=b.prodotto_id)) then
    raise foreign_key_violation using message='Il backup eliminerebbe prodotti collegati agli hotel';
  end if;
  if p_dry_run is null or p_dry_run then
    return jsonb_build_object('dry_run',true,'tables',counts);
  end if;
  -- Ordine unico di lock, anche quando due ripristini arrivano insieme.
  foreach tab in array allowed loop
    execute format('lock table menu.%I in share row exclusive mode',tab);
  end loop;
  lock table public.bb_struttura_menu_prodotti in share row exclusive mode;
  -- Ripete il controllo sotto lock: un hotel può essersi collegato durante la verifica.
  if exists(select 1 from public.bb_struttura_menu_prodotti b
    where not exists(select 1 from jsonb_populate_recordset(null::menu.menu_products,p_tables->'menu_products') p where p.id=b.prodotto_id)) then
    raise foreign_key_violation using message='Collegamenti hotel modificati durante il ripristino';
  end if;
  foreach tab in array allowed loop
    select string_agg(format('%I',a.attname),',' order by u.ordinality) into pk
      from pg_index i cross join lateral unnest(i.indkey) with ordinality u(attnum,ordinality)
      join pg_attribute a on a.attrelid=i.indrelid and a.attnum=u.attnum
      where i.indisprimary and i.indrelid=format('menu.%I',tab)::regclass;
    select string_agg(format('%I=excluded.%I',a.attname,a.attname),',' order by a.attnum) into updates
      from pg_attribute a where a.attrelid=format('menu.%I',tab)::regclass
      and a.attnum>0 and not a.attisdropped
      and not exists(select 1 from pg_index i where i.indrelid=a.attrelid and i.indisprimary and a.attnum=any(i.indkey));
    execute format('insert into menu.%I select * from jsonb_populate_recordset(null::menu.%I,$1) on conflict (%s) do update set %s',tab,tab,pk,updates)
      using p_tables->tab;
  end loop;
  -- Figli prima dei genitori. Upsert evita le cancellazioni CASCADE dei
  -- prodotti che esistono sia nel backup sia nel catalogo operativo.
  for n in reverse cardinality(allowed)..1 loop
    tab:=allowed[n];
    select string_agg(format('s.%I=d.%I',a.attname,a.attname),' and ' order by u.ordinality) into equality
      from pg_index i cross join lateral unnest(i.indkey) with ordinality u(attnum,ordinality)
      join pg_attribute a on a.attrelid=i.indrelid and a.attnum=u.attnum
      where i.indisprimary and i.indrelid=format('menu.%I',tab)::regclass;
    execute format('delete from menu.%I d where not exists(select 1 from jsonb_populate_recordset(null::menu.%I,$1) s where %s)',tab,tab,equality)
      using p_tables->tab;
  end loop;
  return jsonb_build_object('dry_run',false,'tables',counts);
end;
$function$;
revoke all on function public.gc_restore_menu_backup(jsonb,boolean) from public,authenticated;
grant execute on function public.gc_restore_menu_backup(jsonb,boolean) to anon;
