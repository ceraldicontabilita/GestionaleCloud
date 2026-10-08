-- Email del bar (Impostazioni › Dati del bar) per l'avviso degli ordini prodotti. Gia' pubblica in bb_hotel_info: nessun dato nuovo esposto.
create or replace function public.bb_ordini_contatti_bar() returns json
language sql stable security definer set search_path='' as $$
 select json_build_object('email', coalesce((select trim(v) from public.bb_config where k='bar_email'),''))
$$;
revoke all on function public.bb_ordini_contatti_bar() from public;
grant execute on function public.bb_ordini_contatti_bar() to anon, authenticated;
