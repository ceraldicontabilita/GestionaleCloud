-- Un solo catalogo per Menu pubblico, listini hotel e carrello dell'ospite.
-- Qui si salvano esclusivamente l'abilitazione e il prezzo specifico della
-- struttura: nome, foto, descrizione, allergeni e sezioni restano in menu.*.

create table if not exists public.bb_struttura_menu_prodotti (
  struttura_id uuid not null references public.bb_strutture(id) on delete cascade,
  prodotto_id int not null references menu.menu_products(id) on delete cascade,
  prezzo numeric(8,2) not null check (prezzo > 0 and prezzo <= 9999),
  ordine int not null default 0,
  aggiornato timestamptz not null default now(),
  primary key (struttura_id, prodotto_id)
);
create index if not exists bb_struttura_menu_prodotti_ordine
  on public.bb_struttura_menu_prodotti(struttura_id, ordine, prodotto_id);
create index if not exists bb_struttura_menu_prodotti_prodotto
  on public.bb_struttura_menu_prodotti(prodotto_id);
alter table public.bb_struttura_menu_prodotti enable row level security;
revoke all on public.bb_struttura_menu_prodotti from public, anon, authenticated;

create or replace function public.bb_menu_prodotti_struttura_json(sid uuid) returns json
language sql stable security definer set search_path='' as $$
 select coalesce(json_agg(json_build_object(
   'prodotto_id',mp.id,'chiave','menu:'||mp.id,'origine','menu',
   'nome',mp.name_it,'descrizione',coalesce(mp.description_it,''),
   'allergeni',coalesce(mp.allergens,'{}'::text[]),'immagine',mp.image,
   'prezzo',sp.prezzo,'categoria',c.name_it,'sezione',s.name_it,
   'lotti_ref',mp.lotti_ref
 ) order by sp.ordine,c.name_it,s.name_it,mp.name_it),'[]'::json)
 from public.bb_struttura_menu_prodotti sp
 join menu.menu_products mp on mp.id=sp.prodotto_id
 join menu.menu_categories c on c.id=mp.category_id
 join menu.menu_subcategories s on s.id=mp.subcategory_id
 where sp.struttura_id=sid and mp.visible is not false
$$;
revoke all on function public.bb_menu_prodotti_struttura_json(uuid) from public,anon,authenticated;

create or replace function public.bb_tit_menu_prodotti_struttura(p text,sid uuid) returns json
language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_check_tit(p);
 if not exists(select 1 from public.bb_strutture where id=sid) then raise exception 'Struttura non trovata';end if;
 return public.bb_menu_prodotti_struttura_json(sid);
end $$;
revoke all on function public.bb_tit_menu_prodotti_struttura(text,uuid) from public,anon,authenticated;
grant execute on function public.bb_tit_menu_prodotti_struttura(text,uuid) to anon,authenticated;

create or replace function public.bb_tit_menu_prodotti_salva(p text,sid uuid,righe jsonb) returns json
language plpgsql security definer set search_path='' as $$
declare r jsonb;i int:=0;pid int;pr numeric;keep int[]:='{}';
begin
 perform public.bb_check_tit(p);
 if not exists(select 1 from public.bb_strutture where id=sid) then raise exception 'Struttura non trovata';end if;
 if jsonb_typeof(righe)<>'array' or jsonb_array_length(righe)>1000 then raise exception 'Elenco prodotti non valido (massimo 1000)';end if;
 for r in select * from jsonb_array_elements(righe) loop
  i:=i+1;pid:=nullif(r->>'prodotto_id','')::int;pr:=nullif(r->>'prezzo','')::numeric;
  if pid is null or not exists(select 1 from menu.menu_products where id=pid and visible is not false) then raise exception 'Prodotto Menu non disponibile: %',pid;end if;
  if pr is null or pr<=0 or pr>9999 then raise exception 'Inserisci un prezzo hotel valido';end if;
  if pid=any(keep) then raise exception 'Prodotto Menu duplicato: %',pid;end if;
  keep:=array_append(keep,pid);
  insert into public.bb_struttura_menu_prodotti(struttura_id,prodotto_id,prezzo,ordine,aggiornato)
  values(sid,pid,pr,i,now()) on conflict(struttura_id,prodotto_id) do update set
   prezzo=excluded.prezzo,ordine=excluded.ordine,aggiornato=now();
 end loop;
 delete from public.bb_struttura_menu_prodotti x where x.struttura_id=sid and not (x.prodotto_id=any(keep));
 return public.bb_menu_prodotti_struttura_json(sid);
end $$;
revoke all on function public.bb_tit_menu_prodotti_salva(text,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.bb_tit_menu_prodotti_salva(text,uuid,jsonb) to anon,authenticated;

-- L'area albergatore continua a usare lo stesso nome RPC, ma ora legge il Menu.
create or replace function public.bb_alb_prodotti(sid uuid,p text) returns json
language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_check_alb(sid,p);
 return public.bb_menu_prodotti_struttura_json(sid);
end $$;
revoke all on function public.bb_alb_prodotti(uuid,text) from public,anon,authenticated;
grant execute on function public.bb_alb_prodotti(uuid,text) to anon,authenticated;

create or replace function public.bb_menu_ospite(vid text,pgiorno date) returns json
language plpgsql security definer set search_path='' as $$
declare v public.bb_vouchers;s text;
begin
 perform public.bb_limite_ospite();
 select * into v from public.bb_vouchers where id=upper(trim(vid));
 if not found then return json_build_object('errore','Codice non trovato');end if;
 if v.annullato then return json_build_object('errore','Questa colazione e stata annullata');end if;
 if pgiorno<v.data or pgiorno>v.data_fine or pgiorno<public.bb_oggi() then return json_build_object('errore','Giorno non valido per questo soggiorno');end if;
 select nome into s from public.bb_strutture where id=v.struttura_id;
 return json_build_object('struttura',s,'giorno',pgiorno,'prodotti',public.bb_menu_prodotti_struttura_json(v.struttura_id));
end $$;
revoke all on function public.bb_menu_ospite(text,date) from public,anon,authenticated;
grant execute on function public.bb_menu_ospite(text,date) to anon,authenticated;

create or replace function public.bb_ospite_menu_salva(vid text,pgiorno date,righe jsonb) returns json
language plpgsql security definer set search_path='' as $$
declare v public.bb_vouchers;r jsonb;pid int;q int;pr record;voci jsonb:='[]'::jsonb;nuovo jsonb:='[]'::jsonb;tot numeric:=0;n int:=0;
begin
 perform public.bb_limite_ospite();
 select * into v from public.bb_vouchers where id=upper(trim(vid)) for update;
 if not found then return json_build_object('errore','Codice non trovato');end if;
 if v.annullato then return json_build_object('errore','Questa colazione e stata annullata');end if;
 if pgiorno<v.data or pgiorno>v.data_fine or pgiorno<public.bb_oggi() then return json_build_object('errore','Giorno non valido per questo soggiorno');end if;
 if pgiorno=any(v.extra_pagati_giorni) then return json_build_object('errore','Gli extra di questo giorno sono gia stati incassati');end if;
 if jsonb_typeof(righe)<>'array' or jsonb_array_length(righe)>40 then return json_build_object('errore','Carrello non valido');end if;
 for r in select * from jsonb_array_elements(righe) loop
  n:=n+1;pid:=nullif(r->>'prodotto_id','')::int;q:=nullif(r->>'quantita','')::int;
  if q is null or q<1 or q>20 then return json_build_object('errore','Quantita non valida');end if;
  select mp.id,mp.name_it nome,sp.prezzo into pr
  from public.bb_struttura_menu_prodotti sp join menu.menu_products mp on mp.id=sp.prodotto_id
  where sp.struttura_id=v.struttura_id and sp.prodotto_id=pid and mp.visible is not false;
  if not found then return json_build_object('errore','Prodotto non disponibile per questa struttura');end if;
  voci:=voci||jsonb_build_object('id',pr.id,'nome',pr.nome,'qta',q,'prezzo',pr.prezzo);
  tot:=tot+pr.prezzo*q;
 end loop;
 select coalesce(jsonb_agg(ex order by ex->>'giorno'),'[]'::jsonb) into nuovo
 from jsonb_array_elements(coalesce(v.extra,'[]'::jsonb)) ex where ex?'giorno' and (ex->>'giorno')::date<>pgiorno;
 if jsonb_array_length(voci)>0 then nuovo:=nuovo||jsonb_build_object('giorno',pgiorno,'voci',voci,'totale',tot);end if;
 update public.bb_vouchers set extra=nuovo,
  extra_totale=(select coalesce(sum(coalesce((ex->>'totale')::numeric,0)),0) from jsonb_array_elements(nuovo) ex),
  richieste_agg=now() where id=v.id;
 return json_build_object('ok',true,'giorno',pgiorno,'voci',voci,'totale',tot);
end $$;
revoke all on function public.bb_ospite_menu_salva(text,date,jsonb) from public,anon,authenticated;
grant execute on function public.bb_ospite_menu_salva(text,date,jsonb) to anon,authenticated;
