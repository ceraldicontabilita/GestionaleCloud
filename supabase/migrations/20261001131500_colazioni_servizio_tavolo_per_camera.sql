-- Il servizio al tavolo diventa una scelta per camera/prenotazione.
-- Le camere esistenti ereditano l'impostazione della struttura, per non
-- cambiare il prezzo dei flussi gia' configurati.

alter table public.bb_camere
  add column if not exists servizio_tavolo boolean not null default false;
alter table public.bb_vouchers
  add column if not exists servizio_tavolo boolean not null default false,
  add column if not exists supplemento_tavolo numeric(8,2) not null default 0
    check (supplemento_tavolo >= 0);

update public.bb_camere c
set servizio_tavolo=true
from public.bb_strutture s
where s.id=c.struttura_id and s.servizio_tavolo and not c.servizio_tavolo;

create or replace function public.bb_supplemento_tavolo() returns numeric
language sql stable security definer set search_path='' as $$
 select coalesce(nullif(public.bb_cfg('supplemento_tavolo','1.5'),'')::numeric,0)
$$;
revoke all on function public.bb_supplemento_tavolo() from public, anon, authenticated;

create or replace function public.bb_camere_set(sid uuid, camere jsonb) returns void
language plpgsql security definer set search_path='' as $$
declare c jsonb; i int:=0;
begin
 if jsonb_typeof(camere)<>'array' or jsonb_array_length(camere)>150 then
  raise exception 'Elenco camere non valido (max 150)';
 end if;
 delete from public.bb_camere where struttura_id=sid;
 for c in select * from jsonb_array_elements(camere) loop
  if coalesce(trim(c->>'nome'),'')='' then continue; end if;
  i:=i+1;
  insert into public.bb_camere(struttura_id,nome,ospiti,ordine,servizio_tavolo)
  values (
   sid,left(trim(c->>'nome'),40),
   least(10,greatest(1,coalesce((c->>'ospiti')::int,2))),i,
   coalesce((c->>'servizio_tavolo')::boolean,false));
 end loop;
end $$;
revoke all on function public.bb_camere_set(uuid,jsonb) from public, anon, authenticated;

create or replace function public.bb_alb_crea_soggiorni(sid uuid,p text,righe jsonb) returns json
language plpgsql security definer set search_path='' as $$
declare s public.bb_strutture; r jsonb; vid text; oc int; cam text; dal date; al date;
 gg int; c public.bb_colazioni; tot numeric:=0; supp numeric; tav boolean; ids jsonb:='[]';
 lim text; ora_lim timestamptz; mx int;
begin
 perform public.bb_check_alb(sid,p);
 select * into s from public.bb_strutture where id=sid for update;
 if jsonb_typeof(righe)<>'array' or jsonb_array_length(righe)=0 or jsonb_array_length(righe)>150 then
  raise exception 'Seleziona almeno una camera';
 end if;
 lim:=public.bb_cfg('ordini_limite_ora','');
 mx:=public.bb_cfg('anticipo_max_giorni','60')::int;
 for r in select * from jsonb_array_elements(righe) loop
  oc:=coalesce((r->>'ospiti')::int,1);
  if oc<1 or oc>10 then raise exception 'Ospiti per camera: da 1 a 10'; end if;
  dal:=(r->>'dal')::date; al:=coalesce((r->>'al')::date,dal);
  if dal<public.bb_oggi() then raise exception 'La data di arrivo è nel passato'; end if;
  if al<dal then raise exception 'La data di partenza è prima dell''arrivo'; end if;
  gg:=al-dal+1;
  if gg>31 then raise exception 'Soggiorno massimo 31 giorni'; end if;
  if al>public.bb_oggi()+mx then raise exception 'Puoi prenotare al massimo % giorni prima',mx; end if;
  if lim<>'' then
   ora_lim:=((dal-1)::text||' '||lim)::timestamp at time zone 'Europe/Rome';
   if now()>ora_lim then
    raise exception 'Le colazioni dal % vanno ordinate entro le % del giorno prima',to_char(dal,'DD/MM'),lim;
   end if;
  end if;
  select * into c from public.bb_colazioni
   where id=nullif(r->>'colazione_id','')::uuid and struttura_id=sid and attiva;
  if not found then raise exception 'Scegli una colazione disponibile per ogni camera'; end if;
  tav:=coalesce((r->>'servizio_tavolo')::boolean,false);
  supp:=case when tav then public.bb_supplemento_tavolo() else 0 end;
  tot:=tot+(c.prezzo+supp)*oc*gg;
 end loop;
 if public.bb_saldo(sid)<tot then
  raise exception 'Saldo insufficiente: servono % €, disponibili % €',tot,public.bb_saldo(sid);
 end if;
 for r in select * from jsonb_array_elements(righe) loop
  oc:=(r->>'ospiti')::int; dal:=(r->>'dal')::date; al:=coalesce((r->>'al')::date,dal); gg:=al-dal+1;
  select * into c from public.bb_colazioni where id=(r->>'colazione_id')::uuid and struttura_id=sid;
  tav:=coalesce((r->>'servizio_tavolo')::boolean,false);
  supp:=case when tav then public.bb_supplemento_tavolo() else 0 end;
  cam:=left(trim(coalesce(r->>'camera','')),40);
  vid:=upper(substr(encode(extensions.gen_random_bytes(8),'hex'),1,10));
  insert into public.bb_vouchers(
   id,struttura_id,fascia,qta,data,data_fine,ospite,camera,ospiti,colazione_id,
   colazione_nome,servizio_tavolo,supplemento_tavolo)
  values (
   vid,sid,c.prezzo+supp,oc*gg,dal,al,coalesce(nullif(cam,''),'Ospite'),cam,oc,c.id,
   c.nome,tav,supp);
  insert into public.bb_movimenti(struttura_id,tipo,importo,nota)
  values (
   sid,'prenotazione',-(c.prezzo+supp)*oc*gg,
   coalesce(nullif(cam,'')||' · ','')||oc||' ospiti × '||gg||' giorni · '||c.nome||
   case when tav then ' (tavolo +'||supp||' €)' else ' (banco)' end);
  ids:=ids||jsonb_build_object('id',vid,'camera',cam,'nome',coalesce(nullif(cam,''),'Ospite'));
 end loop;
 return json_build_object('creati',ids,'totale',tot);
end $$;
revoke all on function public.bb_alb_crea_soggiorni(uuid,text,jsonb) from public, anon, authenticated;
grant execute on function public.bb_alb_crea_soggiorni(uuid,text,jsonb) to anon, authenticated;

create or replace function public.bb_alb_stato(sid uuid,p text) returns json
language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_check_alb(sid,p);
 perform public.bb_sumup_verifica(sid);
 return json_build_object(
  'struttura',(select json_build_object(
   'id',id,'nome',nome,'indirizzo',indirizzo,'telefono',telefono,'benvenuto',benvenuto,
   'accesso',accesso,'saldo',public.bb_saldo(id),'tavolo',servizio_tavolo,
   'supp_tavolo',public.bb_supplemento_tavolo())
   from public.bb_strutture where id=sid),
  'fiscali',(select public.bb_fiscali_json(s) from public.bb_strutture s where s.id=sid),
  'fatture',(select coalesce(json_agg(f order by f.pagata_il desc),'[]'::json) from (
   select id,importo,pagata_il,stato,numero,data_emissione
   from public.bb_fatture_da_emettere where struttura_id=sid order by pagata_il desc limit 50) f),
  'oggi',public.bb_oggi(),'bar',public.bb_bar_pubblico(),'sumup',public.bb_sumup_attivo(),
  'config',json_build_object(
   'ricarica_min',public.bb_cfg('ricarica_min','5')::numeric,
   'ricarica_max',public.bb_cfg('ricarica_max','2000')::numeric,
   'anticipo',public.bb_cfg('anticipo_max_giorni','60')::int,
   'limite_ora',public.bb_cfg('ordini_limite_ora',''),
   'msg',public.bb_cfg('msg_ospite','{link}')),
  'colazioni',public.bb_colazioni_json(sid,true),
  'camere',(select coalesce(json_agg(json_build_object(
   'id',c.id,'nome',c.nome,'ospiti',c.ospiti,'servizio_tavolo',c.servizio_tavolo)
   order by c.ordine),'[]'::json) from public.bb_camere c where c.struttura_id=sid),
  'movimenti',(select coalesce(json_agg(m order by m.t desc),'[]'::json) from (
   select id,t,tipo,importo,nota,confermato,sumup_url
   from public.bb_movimenti where struttura_id=sid) m),
  'vouchers',(select coalesce(json_agg(v order by v.creato desc),'[]'::json) from (
   select id,fascia,qta,usate,data,data_fine,ospite,camera,ospiti,colazione_nome,creato,
    annullato,(richieste<>'{}'::jsonb) has_richieste,extra_totale,extra_pagato,
    servizio_tavolo,supplemento_tavolo
   from public.bb_vouchers where struttura_id=sid) v));
end $$;
revoke all on function public.bb_alb_stato(uuid,text) from public, anon, authenticated;
grant execute on function public.bb_alb_stato(uuid,text) to anon, authenticated;

create or replace function public.bb_ospite(vid text) returns json
language sql security definer set search_path='' as $$
 select json_build_object(
  'id',v.id,'qta',v.qta,'usate',v.usate,'data',v.data,'data_fine',v.data_fine,
  'ospite',v.ospite,'camera',v.camera,'ospiti',v.ospiti,'annullato',v.annullato,
  'struttura',s.nome,'indirizzo',s.indirizzo,'sfondo',s.sfondo,'benvenuto',s.benvenuto,
  'tavolo',v.servizio_tavolo,'colazione',v.colazione_nome,
  'menu',coalesce(
   (select descrizione from public.bb_colazioni where id=v.colazione_id),
   (select descrizione from public.bb_menu where fascia=v.fascia)),
  'voci',case when v.colazione_id is not null
   then public.bb_voci_col_json(v.colazione_id)
   else public.bb_voci_json(v.fascia::int) end,
  'richieste',v.richieste,'extra',v.extra,'extra_totale',v.extra_totale,
  'extra_pagato',v.extra_pagato,'glutine',public.bb_glutine_pubblico(),
  'allergeni_elenco',public.bb_allergeni_elenco(),'bar',public.bb_bar_pubblico(),
  'oggi',public.bb_oggi())
 from public.bb_vouchers v
 join public.bb_strutture s on s.id=v.struttura_id
 where v.id=upper(trim(vid))
$$;
revoke all on function public.bb_ospite(text) from public, anon, authenticated;
grant execute on function public.bb_ospite(text) to anon, authenticated;

create or replace function public.bb_tit_stato(p text) returns json
language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_check_tit(p);
 return json_build_object(
  'oggi',public.bb_oggi(),'bar',public.bb_bar_pubblico(),'menu',public.bb_menu_pubblico(),
  'allergeni',public.bb_menu_allergeni(),'sumup',public.bb_sumup_attivo(),'pin_off',public.bb_pin_stato(),
  'config',(select coalesce(json_object_agg(k,v),'{}'::json) from public.bb_config where k<>'tit_pin'),
  'voci',(select coalesce(json_object_agg(fascia::text,public.bb_voci_json(fascia)),'{}'::json) from public.bb_menu),
  'standard',public.bb_colazioni_json(null,false),
  'colazioni',(select coalesce(json_object_agg(id::text,public.bb_colazioni_json(id,false)),'{}'::json) from public.bb_strutture),
  'allergeni_elenco',public.bb_allergeni_elenco(),
  'camere',(select coalesce(json_object_agg(sid::text,cj),'{}'::json) from (
   select c.struttura_id sid,json_agg(json_build_object(
    'nome',c.nome,'ospiti',c.ospiti,'servizio_tavolo',c.servizio_tavolo) order by c.ordine) cj
   from public.bb_camere c group by c.struttura_id) x),
  'strutture',(select coalesce(json_agg(x order by x.nome),'[]'::json) from (
   select id,nome,indirizzo,telefono,email,demo,servizio_tavolo,accesso,invito_token,
    (pin_hash is not null) attivo,public.bb_saldo(id) saldo from public.bb_strutture) x),
  'attesa',(select coalesce(json_agg(x order by x.t),'[]'::json) from (
   select m.id,m.t,m.importo,s.nome from public.bb_movimenti m
   join public.bb_strutture s on s.id=m.struttura_id
   where not m.confermato and m.sumup_id is null) x),
  'movimenti',(select coalesce(json_agg(x order by x.t desc),'[]'::json) from (
   select m.id,m.struttura_id,s.nome struttura,m.t,m.tipo,m.importo,m.nota,m.confermato
   from public.bb_movimenti m join public.bb_strutture s on s.id=m.struttura_id) x),
  'vouchers',(select coalesce(json_agg(x order by x.creato desc),'[]'::json) from (
   select v.id,v.struttura_id,s.nome struttura,v.fascia,v.qta,v.usate,v.data,v.data_fine,
    v.ospite,v.camera,v.ospiti,v.colazione_id,v.colazione_nome,v.creato,v.annullato,
    v.richieste,v.extra,v.extra_totale,v.extra_pagato,v.servizio_tavolo,v.supplemento_tavolo,
    (select coalesce(json_agg((t at time zone 'Europe/Rome')::date),'[]'::json)
     from unnest(v.riscatti) t) riscatti
   from public.bb_vouchers v join public.bb_strutture s on s.id=v.struttura_id) x));
end $$;
revoke all on function public.bb_tit_stato(text) from public, anon, authenticated;
grant execute on function public.bb_tit_stato(text) to anon, authenticated;
