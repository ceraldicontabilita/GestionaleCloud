-- Una sola snapshot SQL per tutte le tabelle: nessun limite PostgREST a 1000
-- righe e nessun catalogo spezzato durante modifiche concorrenti.
create or replace function public.gc_export_menu_backup()
returns jsonb language plpgsql stable security definer set search_path=pg_catalog
as $function$
declare
  tables constant text[]:=array['menu_categories','menu_subcategories','menu_products',
    'menu_allergens','menu_qrcode_config','menu_orders','menu_warehouse_items',
    'menu_warehouse_movements','menu_allergeni_esclusioni','menu_sale'];
  tab text;
  rows jsonb;
  result jsonb:='{}'::jsonb;
begin
  perform public.gc_assert_runtime_secret();
  foreach tab in array tables loop
    execute format('select coalesce(jsonb_agg(to_jsonb(t)),''[]''::jsonb) from menu.%I t',tab) into rows;
    result:=result||jsonb_build_object(tab,rows);
  end loop;
  return result;
end;
$function$;
revoke all on function public.gc_export_menu_backup() from public,authenticated;
grant execute on function public.gc_export_menu_backup() to anon;
