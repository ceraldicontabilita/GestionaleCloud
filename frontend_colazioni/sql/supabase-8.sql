-- Colazioni B&B · migrazione 8: inviti ai nuovi B&B, accesso personale con schermata di benvenuto,
-- modalità prova senza PIN (a tempo) e dati veri del bar.

alter table bb_strutture alter column pin_hash drop not null;
alter table bb_strutture add column if not exists accesso text;
alter table bb_strutture add column if not exists invito_token text;
alter table bb_strutture add column if not exists sfondo text not null default '';
alter table bb_strutture add column if not exists benvenuto text not null default '';
alter table bb_strutture add column if not exists email text not null default '';
create unique index if not exists bb_strutture_accesso on bb_strutture(accesso);
create unique index if not exists bb_strutture_invito on bb_strutture(invito_token) where invito_token is not null;

update bb_strutture set accesso = case nome when 'B&B Vesuvio (DEMO)' then 'vesuvio' when 'Hotel Partenope (DEMO)' then 'partenope' when 'Casa Mergellina (DEMO)' then 'mergellina'
  else lower(substr(encode(gen_random_bytes(6),'hex'),1,8)) end where accesso is null;

insert into bb_config values ('msg_invito','Ciao! {bar} ti invita a usare l''app per le colazioni dei tuoi ospiti. Attiva il tuo accesso da qui: {link}') on conflict do nothing;
update bb_config set v='Piazza Carità 14, 80134 Napoli' where k='bar_indirizzo' and v='';
update bb_config set v='+39 081 552 3488' where k='bar_tel' and v='';

-- ===== controllo PIN, con modalità prova a tempo =====
create or replace function bb_pin_off() returns boolean language sql stable security definer set search_path=public as
$$ select coalesce((select v::timestamptz>now() from bb_config where k='pin_off_until' and v<>''),false) $$;
revoke execute on function bb_pin_off() from public,anon,authenticated;

create or replace function bb_pin_stato() returns json language sql security definer set search_path=public as
$$ select json_build_object('attivo',bb_pin_off(),'fino',(select v from bb_config where k='pin_off_until' and bb_pin_off())) $$;
revoke all on function bb_pin_stato() from public; grant execute on function bb_pin_stato() to anon;

create or replace function bb_check_tit_strict(p text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin if not exists(select 1 from bb_config where k='tit_pin' and v=crypt(p,v)) then raise exception 'PIN errato'; end if; end $$;
create or replace function bb_check_tit(p text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin if bb_pin_off() then return; end if; perform bb_check_tit_strict(p); end $$;
create or replace function bb_check_alb(sid uuid,p text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 if not exists(select 1 from bb_strutture where id=sid and pin_hash is not null) then raise exception 'Accesso non ancora attivato'; end if;
 if bb_pin_off() then return; end if;
 if not exists(select 1 from bb_strutture where id=sid and pin_hash=crypt(p,pin_hash)) then raise exception 'PIN errato'; end if;
end $$;
revoke execute on function bb_check_tit_strict(text) from public,anon,authenticated;

create or replace function bb_tit_pin_off(p text,ore int) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit_strict(p);
 if coalesce(ore,0)<=0 then delete from bb_config where k='pin_off_until';
 else insert into bb_config values ('pin_off_until',(now()+make_interval(hours=>least(ore,72)))::text) on conflict (k) do update set v=excluded.v; end if;
end $$;
revoke all on function bb_tit_pin_off(text,int) from public; grant execute on function bb_tit_pin_off(text,int) to anon;

-- operazioni sensibili: richiedono sempre il PIN vero, anche in modalità prova
create or replace function bb_tit_pin_cambia(p text,nuovo text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit_strict(p);
 if coalesce(length(nuovo),0)<6 then raise exception 'PIN titolare: minimo 6 cifre'; end if;
 update bb_config set v=crypt(nuovo,gen_salt('bf')) where k='tit_pin';
end $$;
create or replace function bb_tit_elimina_demo(p text) returns int language plpgsql security definer set search_path=public,extensions as $$
declare n int;
begin perform bb_check_tit_strict(p); delete from bb_strutture where demo; get diagnostics n=row_count; return n; end $$;
create or replace function bb_tit_sumup_rimuovi(p text) returns void language plpgsql security definer set search_path=public,extensions,vault as $$
begin
 perform bb_check_tit_strict(p);
 delete from vault.secrets where name='sumup_api_key';
 delete from bb_config where k='sumup_merchant_code';
end $$;
create or replace function bb_tit_sumup_configura(p text,chiave text) returns json language plpgsql security definer set search_path=public,extensions,vault as $$
declare r extensions.http_response; j jsonb; m text; sid uuid;
begin
 perform bb_check_tit_strict(p);
 chiave := trim(coalesce(chiave,''));
 if length(chiave)<20 or chiave ~ '\s' then raise exception 'La chiave non sembra valida: controlla di averla copiata tutta'; end if;
 perform http_set_curlopt('CURLOPT_TIMEOUT','15');
 r := http(('GET','https://api.sumup.com/v0.1/me',array[http_header('Authorization','Bearer '||chiave)],null,null)::http_request);
 if r.status<>200 then raise exception 'SumUp non accetta questa chiave (errore %)',r.status; end if;
 j := r.content::jsonb;
 m := j->'merchant_profile'->>'merchant_code';
 if m is null then raise exception 'Chiave valida ma senza codice esercente: serve la chiave del conto commerciante'; end if;
 select id into sid from vault.secrets where name='sumup_api_key';
 if sid is null then perform vault.create_secret(chiave,'sumup_api_key','Chiave API SumUp per ricariche colazioni B&B');
 else perform vault.update_secret(sid,chiave); end if;
 insert into bb_config values ('sumup_merchant_code',m) on conflict (k) do update set v=excluded.v;
 return json_build_object('ok',true,'merchant',m,'nome',coalesce(j->'merchant_profile'->>'company_name',j->'merchant_profile'->>'doing_business_as'));
end $$;

-- configurazione: aggiungo il testo dell'invito
create or replace function bb_tit_config_set(p text,pk text,pv text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit(p);
 pv := trim(coalesce(pv,''));
 if pk not in ('bar_nome','bar_indirizzo','bar_tel','bar_orari','bar_maps','bar_email','bar_whatsapp','ricarica_min','ricarica_max','anticipo_max_giorni','ordini_limite_ora','msg_ospite','msg_invito','sumup_merchant_code') then raise exception 'Impostazione non valida'; end if;
 if pk='ricarica_min' and (pv !~ '^\d+$' or pv::int not between 1 and 1000) then raise exception 'Ricarica minima: numero tra 1 e 1000'; end if;
 if pk='ricarica_max' and (pv !~ '^\d+$' or pv::int not between 5 and 10000) then raise exception 'Ricarica massima: numero tra 5 e 10000'; end if;
 if pk='anticipo_max_giorni' and (pv !~ '^\d+$' or pv::int not between 1 and 365) then raise exception 'Giorni di anticipo: numero tra 1 e 365'; end if;
 if pk='ordini_limite_ora' and pv<>'' and pv !~ '^([01]\d|2[0-3]):[0-5]\d$' then raise exception 'Orario nel formato 20:00 (oppure vuoto)'; end if;
 if pk='bar_maps' and pv<>'' and pv !~ '^https://' then raise exception 'Il link deve iniziare con https://'; end if;
 insert into bb_config values (pk,pv) on conflict (k) do update set v=excluded.v;
end $$;

-- ===== accesso personale dell'albergatore e inviti =====
drop function if exists bb_strutture_pubbliche();

create or replace function bb_hotel_info(codice text) returns json language sql security definer set search_path=public as
$$ select json_build_object('id',id,'nome',nome,'sfondo',sfondo,'benvenuto',benvenuto,'attivo',pin_hash is not null,'pin_off',bb_pin_off(),'bar',bb_bar_pubblico())
   from bb_strutture where accesso=lower(trim(codice)) $$;
revoke all on function bb_hotel_info(text) from public; grant execute on function bb_hotel_info(text) to anon;

create or replace function bb_invito_info(token text) returns json language sql security definer set search_path=public as
$$ select json_build_object('nome',nome,'sfondo',sfondo,'benvenuto',benvenuto,'indirizzo',indirizzo,'telefono',telefono,'email',email,'bar',bb_bar_pubblico())
   from bb_strutture where invito_token=lower(trim(token)) $$;
revoke all on function bb_invito_info(text) from public; grant execute on function bb_invito_info(text) to anon;

create or replace function bb_invito_accetta(token text,ppin text,pindirizzo text,ptelefono text,pemail text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare s bb_strutture;
begin
 select * into s from bb_strutture where invito_token=lower(trim(token)) for update;
 if not found then raise exception 'Invito non valido o già utilizzato'; end if;
 if coalesce(length(ppin),0)<4 or length(ppin)>20 then raise exception 'Il PIN deve avere almeno 4 caratteri'; end if;
 update bb_strutture set pin_hash=crypt(ppin,gen_salt('bf')), invito_token=null,
   indirizzo=coalesce(nullif(left(trim(coalesce(pindirizzo,'')),150),''),indirizzo), telefono=coalesce(nullif(left(trim(coalesce(ptelefono,'')),30),''),telefono), email=coalesce(nullif(left(trim(coalesce(pemail,'')),100),''),email)
   where id=s.id;
 return json_build_object('id',s.id,'accesso',s.accesso,'nome',s.nome);
end $$;
revoke all on function bb_invito_accetta(text,text,text,text,text) from public; grant execute on function bb_invito_accetta(text,text,text,text,text) to anon;

create or replace function bb_tit_invita(p text,pnome text,pindirizzo text,ptelefono text,pemail text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare nid uuid; tok text; acc text;
begin
 perform bb_check_tit(p);
 if coalesce(trim(pnome),'')='' then raise exception 'Scrivi il nome della struttura'; end if;
 acc := lower(substr(encode(gen_random_bytes(6),'hex'),1,8)); tok := lower(encode(gen_random_bytes(12),'hex'));
 insert into bb_strutture(nome,indirizzo,telefono,email,pin_hash,accesso,invito_token) values (left(trim(pnome),80),left(coalesce(trim(pindirizzo),''),150),left(coalesce(trim(ptelefono),''),30),left(coalesce(trim(pemail),''),100),null,acc,tok) returning id into nid;
 return json_build_object('id',nid,'accesso',acc,'invito',tok);
end $$;
create or replace function bb_tit_invito_rigenera(p text,sid uuid) returns json language plpgsql security definer set search_path=public,extensions as $$
declare tok text;
begin
 perform bb_check_tit(p);
 tok := lower(encode(gen_random_bytes(12),'hex'));
 update bb_strutture set invito_token=tok where id=sid;
 if not found then raise exception 'Struttura non trovata'; end if;
 return json_build_object('invito',tok);
end $$;
revoke all on function bb_tit_invita(text,text,text,text,text), bb_tit_invito_rigenera(text,uuid) from public;
grant execute on function bb_tit_invita(text,text,text,text,text), bb_tit_invito_rigenera(text,uuid) to anon;

create or replace function bb_alb_profilo_salva(sid uuid,p text,pbenvenuto text,psfondo text,pindirizzo text,ptelefono text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_alb(sid,p);
 if psfondo is not null and psfondo<>'' and (length(psfondo)>450000 or psfondo !~ '^data:image/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$') then raise exception 'Immagine non valida o troppo pesante'; end if;
 update bb_strutture set benvenuto=left(coalesce(pbenvenuto,''),200), sfondo=coalesce(psfondo,sfondo),
   indirizzo=coalesce(nullif(left(trim(coalesce(pindirizzo,'')),150),''),indirizzo), telefono=coalesce(left(trim(ptelefono),30),telefono) where id=sid;
end $$;
revoke all on function bb_alb_profilo_salva(uuid,text,text,text,text,text) from public; grant execute on function bb_alb_profilo_salva(uuid,text,text,text,text,text) to anon;

-- ===== stati: accesso, profilo, sfondo per l'ospite =====
create or replace function bb_ospite(vid text) returns json language sql security definer set search_path=public as
$$ select json_build_object('id',v.id,'qta',v.qta,'usate',v.usate,'data',v.data,'ospite',v.ospite,'camera',v.camera,'ospiti',v.ospiti,'annullato',v.annullato,
   'struttura',s.nome,'indirizzo',s.indirizzo,'sfondo',s.sfondo,'benvenuto',s.benvenuto,'menu',(select descrizione from bb_menu where fascia=v.fascia),'voci',bb_voci_json(v.fascia),
   'richieste',v.richieste,'extra',v.extra,'extra_totale',v.extra_totale,'extra_pagato',v.extra_pagato,
   'allergeni_elenco',bb_allergeni_elenco(),'bar',bb_bar_pubblico(),'oggi',bb_oggi())
   from bb_vouchers v join bb_strutture s on s.id=v.struttura_id where v.id=upper(trim(vid)) $$;

create or replace function bb_alb_stato(sid uuid,p text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_alb(sid,p);
 perform bb_sumup_verifica(sid);
 return json_build_object(
  'struttura',(select json_build_object('id',id,'nome',nome,'indirizzo',indirizzo,'telefono',telefono,'benvenuto',benvenuto,'sfondo',sfondo,'accesso',accesso,'fasce',fasce,'saldo',bb_saldo(id)) from bb_strutture where id=sid),
  'oggi',bb_oggi(),'bar',bb_bar_pubblico(),'menu',bb_menu_pubblico(),'sumup',bb_sumup_attivo(),
  'config',json_build_object('ricarica_min',bb_cfg('ricarica_min','5')::numeric,'ricarica_max',bb_cfg('ricarica_max','2000')::numeric,'anticipo',bb_cfg('anticipo_max_giorni','60')::int,'limite_ora',bb_cfg('ordini_limite_ora',''),'msg',bb_cfg('msg_ospite','{link}')),
  'camere',(select coalesce(json_agg(json_build_object('id',c.id,'nome',c.nome,'ospiti',c.ospiti) order by c.ordine),'[]'::json) from bb_camere c where c.struttura_id=sid),
  'movimenti',(select coalesce(json_agg(m order by m.t desc),'[]'::json) from (select id,t,tipo,importo,nota,confermato,sumup_url from bb_movimenti where struttura_id=sid) m),
  'vouchers',(select coalesce(json_agg(v order by v.creato desc),'[]'::json) from (select id,fascia,qta,usate,data,ospite,camera,ospiti,creato,annullato,(richieste<>'{}'::jsonb) has_richieste,extra_totale,extra_pagato from bb_vouchers where struttura_id=sid) v));
end $$;

create or replace function bb_tit_stato(p text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit(p);
 return json_build_object(
  'oggi',bb_oggi(),'bar',bb_bar_pubblico(),'menu',bb_menu_pubblico(),'allergeni',bb_menu_allergeni(),'sumup',bb_sumup_attivo(),'pin_off',bb_pin_stato(),
  'config',(select coalesce(json_object_agg(k,v),'{}'::json) from bb_config where k<>'tit_pin'),
  'voci',(select coalesce(json_object_agg(fascia::text,bb_voci_json(fascia)),'{}'::json) from bb_menu),
  'allergeni_elenco',bb_allergeni_elenco(),
  'camere',(select coalesce(json_object_agg(sid::text,cj),'{}'::json) from (select c.struttura_id sid, json_agg(json_build_object('nome',c.nome,'ospiti',c.ospiti) order by c.ordine) cj from bb_camere c group by c.struttura_id) x),
  'strutture',(select coalesce(json_agg(x order by x.nome),'[]'::json) from (select id,nome,indirizzo,telefono,email,demo,fasce,accesso,invito_token,(pin_hash is not null) attivo,bb_saldo(id) saldo from bb_strutture) x),
  'attesa',(select coalesce(json_agg(x order by x.t),'[]'::json) from (select m.id,m.t,m.importo,s.nome from bb_movimenti m join bb_strutture s on s.id=m.struttura_id where not m.confermato and m.sumup_id is null) x),
  'movimenti',(select coalesce(json_agg(x order by x.t desc),'[]'::json) from (select m.id,m.struttura_id,s.nome struttura,m.t,m.tipo,m.importo,m.nota,m.confermato from bb_movimenti m join bb_strutture s on s.id=m.struttura_id) x),
  'vouchers',(select coalesce(json_agg(x order by x.creato desc),'[]'::json) from (select v.id,v.struttura_id,s.nome struttura,v.fascia,v.qta,v.usate,v.data,v.ospite,v.camera,v.ospiti,v.creato,v.annullato,v.richieste,v.extra,v.extra_totale,v.extra_pagato from bb_vouchers v join bb_strutture s on s.id=v.struttura_id) x));
end $$;
