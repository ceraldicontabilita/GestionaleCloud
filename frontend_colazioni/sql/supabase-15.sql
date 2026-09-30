-- v15: supplemento automatico per il servizio al tavolo
insert into bb_config values ('supplemento_tavolo','1.50') on conflict (k) do nothing;
create or replace function bb_supp_tavolo(sid uuid) returns numeric language sql stable security definer set search_path=public as $$
 select case when servizio_tavolo then coalesce(nullif(bb_cfg('supplemento_tavolo','1.5'),'')::numeric,0) else 0 end from bb_strutture where id=sid $$;

create or replace function bb_tit_config_set(p text,pk text,pv text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit(p);
 pv := trim(coalesce(pv,''));
 if pk not in ('bar_nome','bar_indirizzo','bar_tel','bar_orari','bar_maps','bar_email','bar_whatsapp','ricarica_min','ricarica_max','anticipo_max_giorni','ordini_limite_ora','msg_ospite','msg_invito','sumup_merchant_code','supplemento_tavolo') then raise exception 'Impostazione non valida'; end if;
 if pk='ricarica_min' and (pv !~ '^\d+$' or pv::int not between 1 and 1000) then raise exception 'Ricarica minima: numero tra 1 e 1000'; end if;
 if pk='ricarica_max' and (pv !~ '^\d+$' or pv::int not between 5 and 10000) then raise exception 'Ricarica massima: numero tra 5 e 10000'; end if;
 if pk='anticipo_max_giorni' and (pv !~ '^\d+$' or pv::int not between 1 and 365) then raise exception 'Giorni di anticipo: numero tra 1 e 365'; end if;
 if pk='ordini_limite_ora' and pv<>'' and pv !~ '^([01]\d|2[0-3]):[0-5]\d$' then raise exception 'Orario nel formato 20:00 (oppure vuoto)'; end if;
 if pk='supplemento_tavolo' then pv:=replace(pv,',','.'); if pv !~ '^\d{1,3}(\.\d{1,2})?$' then raise exception 'Supplemento: importo in euro, es. 1,50'; end if; end if;
 if pk='bar_maps' and pv<>'' and pv !~ '^https://' then raise exception 'Il link deve iniziare con https://'; end if;
 insert into bb_config values (pk,pv) on conflict (k) do update set v=excluded.v;
end $$;

create or replace function bb_alb_crea_soggiorni(sid uuid,p text,righe jsonb) returns json language plpgsql security definer set search_path=public,extensions as $$
declare s bb_strutture; r jsonb; vid text; oc int; cam text; dal date; al date; gg int; c bb_colazioni; tot numeric:=0; pu numeric; supp numeric; ids jsonb:='[]'; lim text; ora_lim timestamptz; mx int;
begin
 perform bb_check_alb(sid,p);
 select * into s from bb_strutture where id=sid for update;
 supp := bb_supp_tavolo(sid);
 if jsonb_typeof(righe)<>'array' or jsonb_array_length(righe)=0 or jsonb_array_length(righe)>150 then raise exception 'Seleziona almeno una camera'; end if;
 lim := bb_cfg('ordini_limite_ora',''); mx := bb_cfg('anticipo_max_giorni','60')::int;
 for r in select * from jsonb_array_elements(righe) loop
  oc := coalesce((r->>'ospiti')::int,1);
  if oc<1 or oc>10 then raise exception 'Ospiti per camera: da 1 a 10'; end if;
  dal := (r->>'dal')::date; al := coalesce((r->>'al')::date,dal);
  if dal<bb_oggi() then raise exception 'La data di arrivo è nel passato'; end if;
  if al<dal then raise exception 'La data di partenza è prima dell''arrivo'; end if;
  gg := al-dal+1;
  if gg>31 then raise exception 'Soggiorno massimo 31 giorni'; end if;
  if al>bb_oggi()+mx then raise exception 'Puoi prenotare al massimo % giorni prima',mx; end if;
  if lim<>'' then
   ora_lim := ((dal-1)::text||' '||lim)::timestamp at time zone 'Europe/Rome';
   if now()>ora_lim then raise exception 'Le colazioni dal % vanno ordinate entro le % del giorno prima',to_char(dal,'DD/MM'),lim; end if;
  end if;
  select * into c from bb_colazioni where id=nullif(r->>'colazione_id','')::uuid and struttura_id=sid and attiva;
  if not found then raise exception 'Scegli una colazione disponibile per ogni camera'; end if;
  tot := tot + (c.prezzo+supp)*oc*gg;
 end loop;
 if bb_saldo(sid)<tot then raise exception 'Saldo insufficiente: servono % €, disponibili % €',tot,bb_saldo(sid); end if;
 for r in select * from jsonb_array_elements(righe) loop
  oc := (r->>'ospiti')::int; dal := (r->>'dal')::date; al := coalesce((r->>'al')::date,dal); gg := al-dal+1;
  select * into c from bb_colazioni where id=(r->>'colazione_id')::uuid;
  cam := left(trim(coalesce(r->>'camera','')),40);
  vid := upper(substr(encode(gen_random_bytes(8),'hex'),1,10));
  insert into bb_vouchers(id,struttura_id,fascia,qta,data,data_fine,ospite,camera,ospiti,colazione_id,colazione_nome)
   values (vid,sid,c.prezzo+supp,oc*gg,dal,al,coalesce(nullif(cam,''),'Ospite'),cam,oc,c.id,c.nome);
  insert into bb_movimenti(struttura_id,tipo,importo,nota) values (sid,'prenotazione',-(c.prezzo+supp)*oc*gg,
   coalesce(nullif(cam,'')||' · ','')||oc||' ospiti × '||gg||' giorni · '||c.nome||case when supp>0 then ' (tavolo +'||supp||' €)' else '' end);
  ids := ids || jsonb_build_object('id',vid,'camera',cam,'nome',coalesce(nullif(cam,''),'Ospite'));
 end loop;
 return json_build_object('creati',ids,'totale',tot);
end $$;

create or replace function bb_alb_stato(sid uuid,p text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_alb(sid,p);
 perform bb_sumup_verifica(sid);
 return json_build_object(
  'struttura',(select json_build_object('id',id,'nome',nome,'indirizzo',indirizzo,'telefono',telefono,'benvenuto',benvenuto,'accesso',accesso,'saldo',bb_saldo(id),'tavolo',servizio_tavolo,'supp_tavolo',bb_supp_tavolo(id)) from bb_strutture where id=sid),
  'oggi',bb_oggi(),'bar',bb_bar_pubblico(),'sumup',bb_sumup_attivo(),
  'config',json_build_object('ricarica_min',bb_cfg('ricarica_min','5')::numeric,'ricarica_max',bb_cfg('ricarica_max','2000')::numeric,'anticipo',bb_cfg('anticipo_max_giorni','60')::int,'limite_ora',bb_cfg('ordini_limite_ora',''),'msg',bb_cfg('msg_ospite','{link}')),
  'colazioni',bb_colazioni_json(sid,true),
  'camere',(select coalesce(json_agg(json_build_object('id',c.id,'nome',c.nome,'ospiti',c.ospiti) order by c.ordine),'[]'::json) from bb_camere c where c.struttura_id=sid),
  'movimenti',(select coalesce(json_agg(m order by m.t desc),'[]'::json) from (select id,t,tipo,importo,nota,confermato,sumup_url from bb_movimenti where struttura_id=sid) m),
  'vouchers',(select coalesce(json_agg(v order by v.creato desc),'[]'::json) from (select id,fascia,qta,usate,data,data_fine,ospite,camera,ospiti,colazione_nome,creato,annullato,(richieste<>'{}'::jsonb) has_richieste,extra_totale,extra_pagato from bb_vouchers where struttura_id=sid) v));
end $$;
