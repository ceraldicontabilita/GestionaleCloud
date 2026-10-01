insert into bb_config values
 ('bar_email',''),('bar_whatsapp',''),('ricarica_min','5'),('ricarica_max','2000'),('anticipo_max_giorni','60'),('ordini_limite_ora',''),
 ('msg_ospite','Ciao {ospite}! Ecco la tua colazione da {bar}: {link}')
on conflict do nothing;

create or replace function bb_cfg(pk text,def text) returns text language sql stable security definer set search_path=public as
$$ select coalesce(nullif((select v from bb_config where k=pk),''),def) $$;
revoke execute on function bb_cfg(text,text) from public,anon,authenticated;

create or replace function bb_tit_config_set(p text,pk text,pv text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit(p);
 pv := trim(coalesce(pv,''));
 if pk not in ('bar_nome','bar_indirizzo','bar_tel','bar_orari','bar_maps','bar_email','bar_whatsapp','ricarica_min','ricarica_max','anticipo_max_giorni','ordini_limite_ora','msg_ospite','sumup_merchant_code') then raise exception 'Impostazione non valida'; end if;
 if pk='ricarica_min' and (pv !~ '^\d+$' or pv::int not between 1 and 1000) then raise exception 'Ricarica minima: numero tra 1 e 1000'; end if;
 if pk='ricarica_max' and (pv !~ '^\d+$' or pv::int not between 5 and 10000) then raise exception 'Ricarica massima: numero tra 5 e 10000'; end if;
 if pk='anticipo_max_giorni' and (pv !~ '^\d+$' or pv::int not between 1 and 365) then raise exception 'Giorni di anticipo: numero tra 1 e 365'; end if;
 if pk='ordini_limite_ora' and pv<>'' and pv !~ '^([01]\d|2[0-3]):[0-5]\d$' then raise exception 'Orario nel formato 20:00 (oppure vuoto)'; end if;
 if pk='bar_maps' and pv<>'' and pv !~ '^https://' then raise exception 'Il link deve iniziare con https://'; end if;
 insert into bb_config values (pk,pv) on conflict (k) do update set v=excluded.v;
end $$;
revoke all on function bb_tit_config_set(text,text,text) from public;
grant execute on function bb_tit_config_set(text,text,text) to anon;

create or replace function bb_alb_crea_voucher(sid uuid,p text,pfascia int,pqta int,pdata date,pospite text) returns json
language plpgsql security definer set search_path=public,extensions as $$
declare s bb_strutture; vid text; tot numeric; lim text; ora_lim timestamptz;
begin
 perform bb_check_alb(sid,p);
 select * into s from bb_strutture where id=sid for update;
 if not (pfascia = any(s.fasce)) then raise exception 'Menu non attivo per questa struttura'; end if;
 if pqta<1 or pqta>50 then raise exception 'Quantità non valida'; end if;
 if pdata<bb_oggi() then raise exception 'Data nel passato'; end if;
 if pdata>bb_oggi()+bb_cfg('anticipo_max_giorni','60')::int then raise exception 'Puoi prenotare al massimo %  giorni prima',bb_cfg('anticipo_max_giorni','60'); end if;
 lim := bb_cfg('ordini_limite_ora','');
 if lim<>'' then
  ora_lim := ((pdata-1)::text||' '||lim)::timestamp at time zone 'Europe/Rome';
  if now()>ora_lim then raise exception 'Le colazioni per il % vanno ordinate entro le % del giorno prima',to_char(pdata,'DD/MM'),lim; end if;
 end if;
 tot := pfascia*pqta;
 if bb_saldo(sid)<tot then raise exception 'Saldo insufficiente'; end if;
 vid := upper(substr(encode(gen_random_bytes(8),'hex'),1,10));
 insert into bb_vouchers(id,struttura_id,fascia,qta,data,ospite) values (vid,sid,pfascia,pqta,pdata,coalesce(nullif(trim(pospite),''),'Ospite'));
 insert into bb_movimenti(struttura_id,tipo,importo,nota) values (sid,'prenotazione',-tot,pqta||'× €'||pfascia||' · '||coalesce(nullif(trim(pospite),''),'Ospite'));
 return json_build_object('id',vid);
end $$;

create or replace function bb_alb_ricarica(sid uuid,p text,imp numeric) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_alb(sid,p);
 if imp<bb_cfg('ricarica_min','5')::numeric or imp>bb_cfg('ricarica_max','2000')::numeric then raise exception 'Importo non valido (da % a % €)',bb_cfg('ricarica_min','5'),bb_cfg('ricarica_max','2000'); end if;
 insert into bb_movimenti(struttura_id,tipo,importo,nota,confermato) values (sid,'ricarica',imp,'Ricarica richiesta (in attesa di conferma)',false);
end $$;

create or replace function bb_alb_ricarica_sumup(sid uuid,p text,imp numeric,ret text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare mid uuid; r extensions.http_response; j jsonb; s bb_strutture;
begin
 perform bb_check_alb(sid,p);
 if not bb_sumup_attivo() then raise exception 'Pagamento online non ancora attivo'; end if;
 if imp<bb_cfg('ricarica_min','5')::numeric or imp>bb_cfg('ricarica_max','2000')::numeric then raise exception 'Importo non valido (da % a % €)',bb_cfg('ricarica_min','5'),bb_cfg('ricarica_max','2000'); end if;
 if ret is null or ret !~ '^https://' then raise exception 'Indirizzo di ritorno non valido'; end if;
 select * into s from bb_strutture where id=sid;
 insert into bb_movimenti(struttura_id,tipo,importo,nota,confermato) values (sid,'ricarica',imp,'Ricarica SumUp (in attesa di pagamento)',false) returning id into mid;
 begin
  perform http_set_curlopt('CURLOPT_TIMEOUT','15');
  r := http(('POST','https://api.sumup.com/v0.1/checkouts',array[http_header('Authorization','Bearer '||bb_sumup_key())],'application/json',
    jsonb_build_object('checkout_reference',mid::text,'amount',imp,'currency','EUR','merchant_code',bb_sumup_merchant(),
      'description','Ricarica borsellino colazioni · '||s.nome,'redirect_url',ret,'hosted_checkout',jsonb_build_object('enabled',true))::text)::http_request);
  j := r.content::jsonb;
  if r.status not between 200 and 299 or j->>'hosted_checkout_url' is null then raise exception 'SumUp: % %',r.status,left(r.content,200); end if;
  update bb_movimenti set sumup_id=j->>'id', sumup_url=j->>'hosted_checkout_url' where id=mid;
  return json_build_object('url',j->>'hosted_checkout_url');
 exception when others then
  delete from bb_movimenti where id=mid;
  raise exception 'Pagamento non disponibile al momento. Riprova o ricarica dal bar. (%)',left(sqlerrm,120);
 end;
end $$;

create or replace function bb_alb_stato(sid uuid,p text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_alb(sid,p);
 perform bb_sumup_verifica(sid);
 return json_build_object(
  'struttura',(select json_build_object('id',id,'nome',nome,'indirizzo',indirizzo,'fasce',fasce,'saldo',bb_saldo(id)) from bb_strutture where id=sid),
  'oggi',bb_oggi(),'bar',bb_bar_pubblico(),'menu',bb_menu_pubblico(),'sumup',bb_sumup_attivo(),
  'config',json_build_object('ricarica_min',bb_cfg('ricarica_min','5')::numeric,'ricarica_max',bb_cfg('ricarica_max','2000')::numeric,'anticipo',bb_cfg('anticipo_max_giorni','60')::int,'limite_ora',bb_cfg('ordini_limite_ora',''),'msg',bb_cfg('msg_ospite','{link}')),
  'movimenti',(select coalesce(json_agg(m order by m.t desc),'[]'::json) from (select id,t,tipo,importo,nota,confermato,sumup_url from bb_movimenti where struttura_id=sid) m),
  'vouchers',(select coalesce(json_agg(v order by v.creato desc),'[]'::json) from (select id,fascia,qta,usate,data,ospite,creato,annullato from bb_vouchers where struttura_id=sid) v));
end $$;

create or replace function bb_tit_stato(p text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit(p);
 return json_build_object(
  'oggi',bb_oggi(),'bar',bb_bar_pubblico(),'menu',bb_menu_pubblico(),'allergeni',bb_menu_allergeni(),'sumup',bb_sumup_attivo(),
  'config',(select coalesce(json_object_agg(k,v),'{}'::json) from bb_config where k<>'tit_pin'),
  'strutture',(select coalesce(json_agg(x order by x.nome),'[]'::json) from (select id,nome,indirizzo,telefono,demo,fasce,bb_saldo(id) saldo from bb_strutture) x),
  'attesa',(select coalesce(json_agg(x order by x.t),'[]'::json) from (select m.id,m.t,m.importo,s.nome from bb_movimenti m join bb_strutture s on s.id=m.struttura_id where not m.confermato and m.sumup_id is null) x),
  'movimenti',(select coalesce(json_agg(x order by x.t desc),'[]'::json) from (select m.id,m.struttura_id,s.nome struttura,m.t,m.tipo,m.importo,m.nota,m.confermato from bb_movimenti m join bb_strutture s on s.id=m.struttura_id) x),
  'vouchers',(select coalesce(json_agg(x order by x.creato desc),'[]'::json) from (select v.id,v.struttura_id,s.nome struttura,v.fascia,v.qta,v.usate,v.data,v.ospite,v.creato,v.annullato from bb_vouchers v join bb_strutture s on s.id=v.struttura_id) x));
end $$;

create or replace function bb_tit_diagnostica(p text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare r extensions.http_response; sumup jsonb;
begin
 perform bb_check_tit(p);
 perform bb_aggiorna_esterni();
 if bb_sumup_attivo() then
  begin
   r := http(('GET','https://api.sumup.com/v0.1/me',array[http_header('Authorization','Bearer '||bb_sumup_key())],null,null)::http_request);
   sumup := jsonb_build_object('ok',r.status=200,'stato',r.status,'merchant',r.content::jsonb->'merchant_profile'->>'merchant_code','nome',r.content::jsonb->'merchant_profile'->>'company_name');
  exception when others then sumup := jsonb_build_object('ok',false,'errore',left(sqlerrm,150)); end;
 else sumup := jsonb_build_object('ok',false,'errore','Chiave non configurata'); end if;
 return json_build_object('sumup',sumup,
  'navi',(select json_build_object('ok',errore is null and aggiornato is not null,'aggiornato',aggiornato,'errore',errore,'n',jsonb_array_length(coalesce(dati->'arrivi','[]'))) from bb_esterni where k='navi'),
  'scioperi',(select json_build_object('ok',errore is null and aggiornato is not null,'aggiornato',aggiornato,'errore',errore,'n',jsonb_array_length(coalesce(dati->'elenco','[]'))) from bb_esterni where k='scioperi'),
  'database',json_build_object('ok',true,'strutture',(select count(*) from bb_strutture),'ordini',(select count(*) from bb_vouchers)));
end $$;
revoke all on function bb_tit_diagnostica(text) from public;
grant execute on function bb_tit_diagnostica(text) to anon;

