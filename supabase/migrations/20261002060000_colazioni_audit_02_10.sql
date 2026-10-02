-- Colazioni B&B · correzioni dell'audit del 02/10/2026 (difetti 2-7, 9-13 e geolocalizzazione).
-- Idempotente: solo `create or replace`, `add column if not exists`, `drop function if exists`.
-- Nessuna tabella viene eliminata. Dopo l'applicazione PostgREST ricarica lo schema (notify in coda).
--
-- Decisioni del titolare recepite qui:
--  * annullo: l'albergatore rimborsa solo entro il soggiorno; dopo `data_fine` solo il titolare, con motivo;
--  * extra per giorno: `bb_vouchers.extra` e' una lista di {giorno, voci, totale}, l'incasso e' per giorno
--    (`extra_pagati_giorni`); il vecchio `extra_pagato` sparisce (dati migrati: tutto sul primo giorno).

-- ===================== colonne nuove e migrazione dei dati =====================
alter table public.bb_vouchers
  add column if not exists extra_pagati_giorni date[] not null default '{}',
  add column if not exists annullo_motivo text not null default '',
  add column if not exists annullato_da text,
  add column if not exists annullato_il timestamptz;
alter table public.bb_strutture
  add column if not exists disattivata_il timestamptz,
  add column if not exists disattivata_motivo text not null default '';
alter table public.bb_recensioni_posizioni
  add column if not exists distanza_m numeric(10,1),
  add column if not exists in_sede boolean;

-- extra per soggiorno -> extra per giorno: le voci gia' ordinate vanno sul primo giorno del soggiorno
update public.bb_vouchers
   set extra = jsonb_build_array(jsonb_build_object('giorno',data,'voci',extra,'totale',extra_totale))
 where jsonb_typeof(extra)='array' and jsonb_array_length(extra)>0 and not (extra->0 ? 'giorno');
do $$ begin
 if exists (select 1 from information_schema.columns where table_schema='public' and table_name='bb_vouchers' and column_name='extra_pagato') then
  update public.bb_vouchers set extra_pagati_giorni=array[data]
   where extra_pagato and jsonb_array_length(extra)>0 and not (data = any(extra_pagati_giorni));
  alter table public.bb_vouchers drop column extra_pagato;
 end if;
end $$;

insert into public.bb_config(k,v) values ('bar_lat',''),('bar_lon',''),('bar_raggio_m','300') on conflict (k) do nothing;

-- ===================== helper interni (mai chiamabili dal browser) =====================
-- IP del chiamante: PostgREST espone gli header; dietro un proxy che non scrive x-forwarded-for
-- restano x-real-ip o cf-connecting-ip. Senza nessuno dei tre e' '?' e la soglia per IP non si applica.
create or replace function public.bb_ip() returns text language sql stable set search_path=public as $$
 select coalesce(
  nullif(trim(split_part(coalesce(x.h->>'x-forwarded-for',''),',',1)),''),
  nullif(trim(coalesce(x.h->>'x-real-ip','')),''),
  nullif(trim(coalesce(x.h->>'cf-connecting-ip','')),''),
  '?')
 from (select nullif(current_setting('request.headers',true),'')::jsonb h) x $$;
revoke all on function public.bb_ip() from public, anon, authenticated;

-- chiave della soglia per IP: nulla se l'IP non e' noto (cosi' un proxy senza header non blocca tutti)
create or replace function public.bb_chiave_ip() returns text language sql stable set search_path=public as $$
 select case when public.bb_ip()<>'?' then 'ip:'||public.bb_ip() end $$;
revoke all on function public.bb_chiave_ip() from public, anon, authenticated;

-- pagina ospite: 60 letture in 10 minuti per IP, poi 15 minuti di blocco.
-- Il blocco si scrive alla 60ª richiesta (servita) e vale dalla successiva: un raise
-- annullerebbe la scrittura nella stessa transazione.
create or replace function public.bb_limite_ospite() returns void language plpgsql security definer set search_path=public as $$
declare k text := public.bb_chiave_ip(); r public.bb_tentativi; sec int;
begin
 if k is null then return; end if;
 k := 'ospite:'||substr(k,4);
 sec := public.bb_blocco(k);
 if sec>0 then raise exception 'Troppe richieste: riprova tra % minuti', ceil(sec/60.0)::int; end if;
 insert into public.bb_tentativi(chiave,n,primo) values (k,1,now())
 on conflict (chiave) do update set
   n = case when public.bb_tentativi.primo < now()-interval '10 minutes' then 1 else public.bb_tentativi.n+1 end,
   primo = case when public.bb_tentativi.primo < now()-interval '10 minutes' then now() else public.bb_tentativi.primo end,
   blocco = null
 returning * into r;
 if r.n >= 60 then update public.bb_tentativi set blocco=now()+interval '15 minutes' where chiave=k; end if;
end $$;
revoke all on function public.bb_limite_ospite() from public, anon, authenticated;

-- extra per giorno, con lo stato di incasso
create or replace function public.bb_extra_json(v public.bb_vouchers) returns jsonb language sql immutable as $$
 select coalesce((select jsonb_agg(jsonb_build_object(
   'giorno',e->>'giorno','voci',coalesce(e->'voci','[]'::jsonb),
   'totale',coalesce((e->>'totale')::numeric,0),
   'pagato',((e->>'giorno')::date = any(v.extra_pagati_giorni))) order by e->>'giorno')
  from jsonb_array_elements(coalesce(v.extra,'[]'::jsonb)) e where e ? 'giorno'),'[]'::jsonb) $$;
create or replace function public.bb_extra_da_pagare(v public.bb_vouchers) returns numeric language sql immutable as $$
 select coalesce((select sum(coalesce((e->>'totale')::numeric,0)) from jsonb_array_elements(coalesce(v.extra,'[]'::jsonb)) e
   where e ? 'giorno' and not ((e->>'giorno')::date = any(v.extra_pagati_giorni))),0) $$;
create or replace function public.bb_extra_del_giorno(v public.bb_vouchers, g date) returns jsonb language sql immutable as $$
 select (select jsonb_build_object('giorno',e->>'giorno','voci',coalesce(e->'voci','[]'::jsonb),'totale',coalesce((e->>'totale')::numeric,0),
   'pagato',(g = any(v.extra_pagati_giorni)))
  from jsonb_array_elements(coalesce(v.extra,'[]'::jsonb)) e where (e->>'giorno')::date=g limit 1) $$;
revoke all on function public.bb_extra_json(public.bb_vouchers), public.bb_extra_da_pagare(public.bb_vouchers), public.bb_extra_del_giorno(public.bb_vouchers,date) from public, anon, authenticated;

-- distanza sulla sfera (haversine), in metri
create or replace function public.bb_distanza_m(lat1 numeric, lon1 numeric, lat2 numeric, lon2 numeric) returns numeric language sql immutable as $$
 select (6371000.0 * 2 * asin(sqrt(
   power(sin(radians((lat2-lat1)::double precision)/2),2) +
   cos(radians(lat1::double precision))*cos(radians(lat2::double precision))*power(sin(radians((lon2-lon1)::double precision)/2),2))))::numeric $$;
revoke all on function public.bb_distanza_m(numeric,numeric,numeric,numeric) from public, anon, authenticated;

-- ===================== accesso albergatore: struttura disattivata, soglia per IP solo con IP noto =====================
create or replace function public.bb_check_alb(sid uuid, p text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 if exists(select 1 from public.bb_strutture where id=sid and disattivata_il is not null) then raise exception 'Struttura disattivata: contatta il bar'; end if;
 if not exists(select 1 from public.bb_strutture where id=sid and pin_hash is not null) then raise exception 'Accesso non ancora attivato'; end if;
 if not public.bb_sessione_ok(p,'alb',sid) then raise exception 'Sessione scaduta: rientra con il PIN'; end if;
end $$;
revoke all on function public.bb_check_alb(uuid,text) from public, anon, authenticated;

create or replace function public.bb_alb_login(paccesso text, ppin text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare s public.bb_strutture; k text; ki text; sec int; rest int;
begin
 select * into s from public.bb_strutture where accesso=lower(trim(coalesce(paccesso,'')));
 if found and s.disattivata_il is not null then return json_build_object('ok',false,'msg','Struttura disattivata: contatta il bar'); end if;
 if not found or s.pin_hash is null then return json_build_object('ok',false,'msg','Accesso non ancora attivato'); end if;
 k := 'alb:'||s.accesso; ki := public.bb_chiave_ip();
 sec := greatest(public.bb_blocco(k),coalesce(public.bb_blocco(ki),0));
 if sec>0 then return json_build_object('ok',false,'bloccato',sec,'msg','Troppi tentativi: riprova tra '||ceil(sec/60.0)::int||' minuti'); end if;
 if s.pin_hash = crypt(coalesce(ppin,''),s.pin_hash) then
  perform public.bb_tentativi_ok(k);
  return json_build_object('ok',true,'token',public.bb_sessione_nuova('alb',s.id,12),'sid',s.id,'nome',s.nome);
 end if;
 rest := public.bb_fallito(k,5);
 if ki is not null then perform public.bb_fallito(ki,25); end if;
 return json_build_object('ok',false,'restanti',rest,'msg',case when rest>0 then 'PIN errato: ti restano '||rest||' tentativi' else 'Troppi tentativi: riprova tra 15 minuti' end);
end $$;
revoke all on function public.bb_alb_login(text,text) from public;
grant execute on function public.bb_alb_login(text,text) to anon, authenticated;

create or replace function public.bb_alb_recupera(paccesso text, pcodice text, pnuovo text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare s public.bb_strutture; k text; ki text; sec int; rest int; rec text;
begin
 select * into s from public.bb_strutture where accesso=lower(trim(coalesce(paccesso,'')));
 if found and s.disattivata_il is not null then return json_build_object('ok',false,'msg','Struttura disattivata: contatta il bar'); end if;
 if not found or s.pin_hash is null then return json_build_object('ok',false,'msg','Accesso non ancora attivato'); end if;
 k := 'rec:'||s.accesso; ki := public.bb_chiave_ip();
 sec := greatest(public.bb_blocco(k),coalesce(public.bb_blocco(ki),0));
 if sec>0 then return json_build_object('ok',false,'bloccato',sec,'msg','Troppi tentativi: riprova tra '||ceil(sec/60.0)::int||' minuti'); end if;
 if coalesce(length(pnuovo),0)<4 or length(pnuovo)>20 then return json_build_object('ok',false,'msg','Il nuovo PIN deve avere almeno 4 caratteri'); end if;
 if s.recupero_hash is null then return json_build_object('ok',false,'msg','Per questo albergo non c''è un codice di recupero: chiedi un nuovo invito al bar','senza_codice',true); end if;
 if s.recupero_hash <> crypt(public.bb_norm_codice(pcodice),s.recupero_hash) then
  rest := public.bb_fallito(k,5);
  if ki is not null then perform public.bb_fallito(ki,25); end if;
  return json_build_object('ok',false,'restanti',rest,'msg',case when rest>0 then 'Codice errato: ti restano '||rest||' tentativi' else 'Troppi tentativi: riprova tra 15 minuti' end);
 end if;
 perform public.bb_tentativi_ok(k); perform public.bb_tentativi_ok('alb:'||s.accesso);
 rec := public.bb_codice_recupero();
 update public.bb_strutture set pin_hash=crypt(pnuovo,gen_salt('bf')), recupero_hash=crypt(public.bb_norm_codice(rec),gen_salt('bf')) where id=s.id;
 delete from public.bb_sessioni where struttura_id=s.id;
 update public.bb_richieste_pin set chiusa=true where struttura_id=s.id and not chiusa;
 return json_build_object('ok',true,'recupero',rec,'token',public.bb_sessione_nuova('alb',s.id,12),'sid',s.id,'nome',s.nome);
end $$;
revoke all on function public.bb_alb_recupera(text,text,text) from public;
grant execute on function public.bb_alb_recupera(text,text,text) to anon, authenticated;

create or replace function public.bb_hotel_info(codice text) returns json language sql security definer set search_path=public as $$
 select json_build_object('id',id,'nome',nome,'sfondo',sfondo,'benvenuto',benvenuto,
   'attivo',(pin_hash is not null and disattivata_il is null),'disattivata',(disattivata_il is not null),
   'pin_off',public.bb_pin_off(),'bar',public.bb_bar_pubblico())
 from public.bb_strutture where accesso=lower(trim(codice)) $$;
revoke all on function public.bb_hotel_info(text) from public;
grant execute on function public.bb_hotel_info(text) to anon, authenticated;

-- ===================== titolare: scheda struttura senza PIN, disattivazione, riattivazione con invito =====================
drop function if exists public.bb_tit_struttura_salva(text,uuid,text,text,text,int[]);
create or replace function public.bb_tit_struttura_salva(p text, sid uuid, pnome text, pindirizzo text, ptelefono text default null, pemail text default null) returns json
language plpgsql security definer set search_path=public,extensions as $$
begin
 perform public.bb_check_tit(p);
 if sid is null then raise exception 'Una struttura nuova nasce da un invito (bb_tit_invita)'; end if;
 update public.bb_strutture set
   nome=coalesce(nullif(left(trim(pnome),80),''),nome),
   indirizzo=coalesce(left(trim(pindirizzo),150),indirizzo),
   telefono=coalesce(left(trim(ptelefono),30),telefono),
   email=coalesce(left(trim(pemail),100),email)
  where id=sid;
 if not found then raise exception 'Struttura non trovata'; end if;
 return json_build_object('id',sid);
end $$;
revoke all on function public.bb_tit_struttura_salva(text,uuid,text,text,text,text) from public;
grant execute on function public.bb_tit_struttura_salva(text,uuid,text,text,text,text) to anon, authenticated;

create or replace function public.bb_tit_struttura_disattiva(p text, sid uuid, pmotivo text) returns json
language plpgsql security definer set search_path=public,extensions as $$
begin
 perform public.bb_check_tit(p);
 if coalesce(trim(pmotivo),'')='' then raise exception 'Scrivi il motivo della disattivazione'; end if;
 update public.bb_strutture set pin_hash=null, recupero_hash=null, invito_token=null,
   disattivata_il=now(), disattivata_motivo=left(trim(pmotivo),200) where id=sid;
 if not found then raise exception 'Struttura non trovata'; end if;
 delete from public.bb_sessioni where struttura_id=sid;
 update public.bb_recensioni_link set attivo=false, aggiornato=now() where struttura_id=sid;
 update public.bb_richieste_pin set chiusa=true where struttura_id=sid and not chiusa;
 return json_build_object('ok',true,'disattivata_il',now());
end $$;
revoke all on function public.bb_tit_struttura_disattiva(text,uuid,text) from public;
grant execute on function public.bb_tit_struttura_disattiva(text,uuid,text) to anon, authenticated;

-- un nuovo invito e' l'unica via per riattivare una struttura disattivata (il link recensioni resta spento:
-- si rigenera dalla sua pagina)
create or replace function public.bb_tit_invito_rigenera(p text, sid uuid) returns json language plpgsql security definer set search_path=public,extensions as $$
declare tok text;
begin
 perform public.bb_check_tit(p);
 tok := lower(encode(gen_random_bytes(12),'hex'));
 update public.bb_strutture set invito_token=tok, disattivata_il=null, disattivata_motivo='' where id=sid;
 if not found then raise exception 'Struttura non trovata'; end if;
 return json_build_object('invito',tok);
end $$;
revoke all on function public.bb_tit_invito_rigenera(text,uuid) from public;
grant execute on function public.bb_tit_invito_rigenera(text,uuid) to anon, authenticated;

-- ===================== impostazioni: coordinate del bar =====================
create or replace function public.bb_tit_config_set(p text, pk text, pv text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 perform public.bb_check_tit(p);
 pv := trim(coalesce(pv,''));
 if pk not in ('bar_nome','bar_indirizzo','bar_tel','bar_orari','bar_maps','bar_email','bar_whatsapp','ricarica_min','ricarica_max','anticipo_max_giorni','ordini_limite_ora','msg_ospite','msg_invito','sumup_merchant_code','supplemento_tavolo','bar_lat','bar_lon','bar_raggio_m') then raise exception 'Impostazione non valida'; end if;
 if pk='ricarica_min' and (pv !~ '^\d+$' or pv::int not between 1 and 1000) then raise exception 'Ricarica minima: numero tra 1 e 1000'; end if;
 if pk='ricarica_max' and (pv !~ '^\d+$' or pv::int not between 5 and 10000) then raise exception 'Ricarica massima: numero tra 5 e 10000'; end if;
 if pk='anticipo_max_giorni' and (pv !~ '^\d+$' or pv::int not between 1 and 365) then raise exception 'Giorni di anticipo: numero tra 1 e 365'; end if;
 if pk='ordini_limite_ora' and pv<>'' and pv !~ '^([01]\d|2[0-3]):[0-5]\d$' then raise exception 'Orario nel formato 20:00 (oppure vuoto)'; end if;
 if pk='supplemento_tavolo' then pv:=replace(pv,',','.'); if pv !~ '^\d{1,3}(\.\d{1,2})?$' then raise exception 'Supplemento: importo in euro, es. 1,50'; end if; end if;
 if pk='bar_maps' and pv<>'' and pv !~ '^https://' then raise exception 'Il link deve iniziare con https://'; end if;
 if pk in ('bar_lat','bar_lon') and pv<>'' then
  pv:=replace(pv,',','.');
  if pv !~ '^-?\d{1,3}(\.\d{1,8})?$' then raise exception 'Coordinata non valida: usa i gradi decimali, es. 40.842949'; end if;
  if pk='bar_lat' and abs(pv::numeric)>90 then raise exception 'Latitudine fuori intervallo'; end if;
  if pk='bar_lon' and abs(pv::numeric)>180 then raise exception 'Longitudine fuori intervallo'; end if;
 end if;
 if pk='bar_raggio_m' and (pv !~ '^\d+$' or pv::int not between 10 and 5000) then raise exception 'Raggio in metri: numero tra 10 e 5000'; end if;
 insert into public.bb_config values (pk,pv) on conflict (k) do update set v=excluded.v;
end $$;
revoke all on function public.bb_tit_config_set(text,text,text) from public;
grant execute on function public.bb_tit_config_set(text,text,text) to anon, authenticated;

-- ===================== codice voucher a 16 caratteri (i vecchi a 10 restano validi) =====================
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
  -- 16 caratteri esadecimali (64 bit di casualita' truncati a 16 cifre): un codice non si indovina
  vid:=upper(substr(encode(extensions.gen_random_bytes(12),'hex'),1,16));
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

-- ===================== annullo: albergatore entro il soggiorno, titolare con motivo =====================
drop function if exists public.bb_annulla(text);
create or replace function public.bb_annulla(vid text, pmotivo text, pda text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare v public.bb_vouchers; resto int;
begin
 select * into v from public.bb_vouchers where id=upper(trim(vid)) for update;
 if not found then raise exception 'Codice non trovato'; end if;
 if v.annullato then raise exception 'Già annullato'; end if;
 resto := v.qta-v.usate;
 if resto<=0 then raise exception 'Nulla da rimborsare: già ritirato'; end if;
 update public.bb_vouchers set annullato=true, annullo_motivo=left(coalesce(trim(pmotivo),''),200), annullato_da=pda, annullato_il=now() where id=v.id;
 insert into public.bb_movimenti(struttura_id,tipo,importo,nota) values (v.struttura_id,'rimborso',resto*v.fascia,'Annullo '||resto||'× €'||v.fascia||' · '||v.ospite||case when pda='titolare' then ' · '||left(coalesce(trim(pmotivo),''),80) else '' end);
 return json_build_object('rimborsato',resto*v.fascia);
end $$;
revoke all on function public.bb_annulla(text,text,text) from public, anon, authenticated;

create or replace function public.bb_alb_annulla(sid uuid,p text,vid text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare v public.bb_vouchers;
begin
 perform public.bb_check_alb(sid,p);
 select * into v from public.bb_vouchers where id=upper(trim(vid)) and struttura_id=sid;
 if not found then raise exception 'Codice non trovato'; end if;
 if v.data_fine<public.bb_oggi() then raise exception 'Soggiorno terminato: chiedi al bar'; end if;
 return public.bb_annulla(vid,'annullo dell''albergatore','albergatore');
end $$;
revoke all on function public.bb_alb_annulla(uuid,text,text) from public;
grant execute on function public.bb_alb_annulla(uuid,text,text) to anon, authenticated;

drop function if exists public.bb_tit_annulla(text,text);
create or replace function public.bb_tit_annulla(p text, vid text, pmotivo text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform public.bb_check_tit(p);
 if coalesce(trim(pmotivo),'')='' then raise exception 'Scrivi il motivo dell''annullo'; end if;
 return public.bb_annulla(vid,pmotivo,'titolare');
end $$;
revoke all on function public.bb_tit_annulla(text,text,text) from public;
grant execute on function public.bb_tit_annulla(text,text,text) to anon, authenticated;

-- ===================== pagina ospite: lettura limitata per IP, richieste validate, extra per giorno =====================
create or replace function public.bb_ospite_json(vid text) returns json
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
  'richieste',v.richieste,
  'extra',public.bb_extra_json(v),'extra_totale',v.extra_totale,'extra_da_pagare',public.bb_extra_da_pagare(v),
  'extra_pagati_giorni',to_jsonb(v.extra_pagati_giorni),
  'glutine',public.bb_glutine_pubblico(),
  'allergeni_elenco',public.bb_allergeni_elenco(),'bar',public.bb_bar_pubblico(),
  'oggi',public.bb_oggi())
 from public.bb_vouchers v
 join public.bb_strutture s on s.id=v.struttura_id
 where v.id=upper(trim(vid))
$$;
revoke all on function public.bb_ospite_json(text) from public, anon, authenticated;

create or replace function public.bb_ospite(vid text) returns json language plpgsql security definer set search_path=public as $$
begin
 perform public.bb_limite_ospite();
 return public.bb_ospite_json(vid);
end $$;
revoke all on function public.bb_ospite(text) from public, anon, authenticated;
grant execute on function public.bb_ospite(text) to anon, authenticated;

drop function if exists public.bb_ospite_salva(text,jsonb,jsonb);
create or replace function public.bb_ospite_salva(vid text, prichieste jsonb, pextra jsonb, pgiorno date default null) returns json
language plpgsql security definer set search_path=public as $$
declare v public.bb_vouchers; g date; ric jsonb; e jsonb; m jsonb; d jsonb; pr record; gl record; n int:=0;
 voci jsonb:='[]'; tot numeric:=0; nuovo jsonb:='[]'; alg jsonb:='[]'; mod jsonb:='[]'; nota text; tipo text;
begin
 perform public.bb_limite_ospite();
 select * into v from public.bb_vouchers where id=upper(trim(vid)) for update;
 -- codice sconosciuto: risposta e non eccezione, cosi' il conteggio per IP resta scritto
 if not found then return json_build_object('errore','Codice non trovato'); end if;
 if v.annullato then raise exception 'Questa colazione è stata annullata'; end if;
 if v.data_fine<public.bb_oggi() then raise exception 'Il soggiorno è terminato: non è più possibile modificare'; end if;
 g := coalesce(pgiorno, greatest(public.bb_oggi(), v.data));
 if g<v.data or g>v.data_fine then raise exception 'Il giorno scelto è fuori dal soggiorno (%–%)',to_char(v.data,'DD/MM'),to_char(v.data_fine,'DD/MM'); end if;
 if g<public.bb_oggi() then raise exception 'Non si ordinano extra per un giorno passato'; end if;

 -- richieste: solo chiavi note, con forma e lunghezza controllate
 prichieste := coalesce(prichieste,'{}'::jsonb);
 if jsonb_typeof(prichieste)<>'object' or length(prichieste::text)>6000 then raise exception 'Richiesta non valida o troppo lunga'; end if;
 if exists(select 1 from jsonb_object_keys(prichieste) k where k not in ('allergie','nota','modifiche')) then raise exception 'Richiesta con campi non ammessi'; end if;
 if prichieste ? 'allergie' then
  if jsonb_typeof(prichieste->'allergie')<>'array' then raise exception 'Allergie non valide'; end if;
  select coalesce(jsonb_agg(distinct x),'[]'::jsonb) into alg from jsonb_array_elements_text(prichieste->'allergie') x
   where exists(select 1 from menu.menu_allergens al where al.id=x);
 end if;
 if prichieste ? 'nota' and jsonb_typeof(prichieste->'nota') not in ('string','null') then raise exception 'Nota non valida'; end if;
 nota := left(coalesce(prichieste->>'nota',''),500);
 if prichieste ? 'modifiche' then
  if jsonb_typeof(prichieste->'modifiche')<>'array' or jsonb_array_length(prichieste->'modifiche')>30 then raise exception 'Modifiche non valide'; end if;
  for m in select * from jsonb_array_elements(prichieste->'modifiche') loop
   if jsonb_typeof(m)<>'object' then raise exception 'Modifica non valida'; end if;
   if exists(select 1 from jsonb_object_keys(m) k where k not in ('voce','tipo','testo','chi','variante','diff')) then raise exception 'Modifica con campi non ammessi'; end if;
   tipo := m->>'tipo';
   if tipo is null or tipo not in ('senza','senza_glutine','nota') then raise exception 'Tipo di modifica non valido'; end if;
   if coalesce(trim(m->>'voce'),'')='' then raise exception 'Modifica senza voce'; end if;
   d := jsonb_build_object('voce',left(m->>'voce',120),'tipo',tipo,'testo',left(coalesce(m->>'testo',''),120),'chi',left(coalesce(nullif(m->>'chi',''),'Tutti'),40));
   if tipo='senza_glutine' and coalesce(m->>'variante','') ~ '^[0-9a-fA-F-]{36}$' then
    select nome, differenza, id into gl from public.bb_senza_glutine where id=(m->>'variante')::uuid;
    if found then d := d || jsonb_build_object('variante',gl.id,'diff',gl.differenza,'testo',gl.nome); end if;
   end if;
   mod := mod || d;
  end loop;
 end if;
 ric := jsonb_build_object('allergie',alg,'nota',nota,'modifiche',mod);

 -- un giorno gia' incassato non cambia: solo le richieste
 if g = any(v.extra_pagati_giorni) then
  if jsonb_typeof(coalesce(pextra,'[]'::jsonb))='array' and jsonb_array_length(coalesce(pextra,'[]'::jsonb))>0 then
   raise exception 'Gli extra del % sono già stati incassati: per cambiarli rivolgiti al bar',to_char(g,'DD/MM');
  end if;
  update public.bb_vouchers set richieste=ric, richieste_agg=now() where id=v.id;
  return public.bb_ospite_json(v.id);
 end if;

 -- extra del giorno: prezzi sempre dal catalogo, mai dal browser
 if jsonb_typeof(coalesce(pextra,'[]'::jsonb))<>'array' then raise exception 'Ordine non valido'; end if;
 for e in select * from jsonb_array_elements(coalesce(pextra,'[]'::jsonb)) loop
  n := n+1; exit when n>40;
  if jsonb_typeof(e)<>'object' or coalesce(e->>'id','') !~ '^\d{1,9}$' or coalesce(e->>'qta','') !~ '^\d{1,2}$' then continue; end if;
  select p.id, p.nome, p.prezzo pz into pr from public.bb_prodotti p join public.bb_prod_cat c on c.id=p.cat_id
    where p.id=(e->>'id')::int and p.visibile and c.attivo and c.ospiti;
  if found and pr.pz>0 and (e->>'qta')::int between 1 and 20 then
   voci := voci || jsonb_build_object('id',pr.id,'nome',pr.nome,'qta',(e->>'qta')::int,'prezzo',pr.pz);
   tot := tot + pr.pz*(e->>'qta')::int;
  end if;
 end loop;
 for m in select * from jsonb_array_elements(mod) loop
  if m->>'tipo'='senza_glutine' and m ? 'variante' then
   voci := voci || jsonb_build_object('glutine',true,'nome','Senza glutine: '||(m->>'testo'),'qta',1,'prezzo',(m->>'diff')::numeric);
   tot := tot + (m->>'diff')::numeric;
  end if;
 end loop;
 select coalesce(jsonb_agg(ex order by ex->>'giorno'),'[]'::jsonb) into nuovo
   from jsonb_array_elements(coalesce(v.extra,'[]'::jsonb)) ex where ex ? 'giorno' and (ex->>'giorno')::date<>g;
 if jsonb_array_length(voci)>0 then nuovo := nuovo || jsonb_build_object('giorno',g,'voci',voci,'totale',tot); end if;
 update public.bb_vouchers set richieste=ric, extra=nuovo,
   extra_totale=(select coalesce(sum(coalesce((ex->>'totale')::numeric,0)),0) from jsonb_array_elements(nuovo) ex),
   richieste_agg=now() where id=v.id;
 return public.bb_ospite_json(v.id);
end $$;
revoke all on function public.bb_ospite_salva(text,jsonb,jsonb,date) from public;
grant execute on function public.bb_ospite_salva(text,jsonb,jsonb,date) to anon, authenticated;

-- incasso degli extra: per giorno (default oggi)
drop function if exists public.bb_tit_extra_incassato(text,text);
create or replace function public.bb_tit_extra_incassato(p text, vid text, pgiorno date default null) returns json
language plpgsql security definer set search_path=public,extensions as $$
declare v public.bb_vouchers; g date; imp numeric;
begin
 perform public.bb_check_tit(p);
 g := coalesce(pgiorno, public.bb_oggi());
 select * into v from public.bb_vouchers where id=upper(trim(vid)) for update;
 if not found then raise exception 'Codice non trovato'; end if;
 select coalesce((d->>'totale')::numeric,0) into imp from jsonb_array_elements(coalesce(v.extra,'[]'::jsonb)) d where (d->>'giorno')::date=g limit 1;
 if imp is null or imp<=0 then raise exception 'Nessun extra da incassare per il %',to_char(g,'DD/MM'); end if;
 if g = any(v.extra_pagati_giorni) then raise exception 'Extra del % già incassati',to_char(g,'DD/MM'); end if;
 update public.bb_vouchers set extra_pagati_giorni=array_append(extra_pagati_giorni,g) where id=v.id;
 return json_build_object('giorno',g,'incassato',imp);
end $$;
revoke all on function public.bb_tit_extra_incassato(text,text,date) from public;
grant execute on function public.bb_tit_extra_incassato(text,text,date) to anon, authenticated;

-- ===================== stati: albergatore, titolare, scanner =====================
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
   select x.id,x.fascia,x.qta,x.usate,x.data,x.data_fine,x.ospite,x.camera,x.ospiti,x.colazione_nome,x.creato,
    x.annullato,x.annullo_motivo,(x.richieste<>'{}'::jsonb) has_richieste,x.extra_totale,
    public.bb_extra_da_pagare(x) extra_da_pagare,x.servizio_tavolo,x.supplemento_tavolo
   from public.bb_vouchers x where x.struttura_id=sid) v));
end $$;
revoke all on function public.bb_alb_stato(uuid,text) from public, anon, authenticated;
grant execute on function public.bb_alb_stato(uuid,text) to anon, authenticated;

create or replace function public.bb_tit_stato(p text) returns json
language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_check_tit(p);
 return json_build_object(
  'oggi',public.bb_oggi(),'bar',public.bb_bar_pubblico(),'menu',public.bb_menu_pubblico(),
  'allergeni',public.bb_menu_allergeni(),'sumup',public.bb_sumup_attivo(),
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
    (pin_hash is not null and disattivata_il is null) attivo,disattivata_il,disattivata_motivo,
    public.bb_saldo(id) saldo from public.bb_strutture) x),
  'attesa',(select coalesce(json_agg(x order by x.t),'[]'::json) from (
   select m.id,m.t,m.importo,s.nome from public.bb_movimenti m
   join public.bb_strutture s on s.id=m.struttura_id
   where not m.confermato and m.sumup_id is null) x),
  'movimenti',(select coalesce(json_agg(x order by x.t desc),'[]'::json) from (
   select m.id,m.struttura_id,s.nome struttura,m.t,m.tipo,m.importo,m.nota,m.confermato
   from public.bb_movimenti m join public.bb_strutture s on s.id=m.struttura_id) x),
  'vouchers',(select coalesce(json_agg(x order by x.creato desc),'[]'::json) from (
   select v.id,v.struttura_id,s.nome struttura,v.fascia,v.qta,v.usate,v.data,v.data_fine,
    v.ospite,v.camera,v.ospiti,v.colazione_id,v.colazione_nome,v.creato,v.annullato,v.annullo_motivo,v.annullato_da,
    v.richieste,public.bb_extra_json(v) extra,v.extra_totale,public.bb_extra_da_pagare(v) extra_da_pagare,
    to_jsonb(v.extra_pagati_giorni) extra_pagati_giorni,v.servizio_tavolo,v.supplemento_tavolo,
    (select coalesce(json_agg((t at time zone 'Europe/Rome')::date),'[]'::json)
     from unnest(v.riscatti) t) riscatti
   from public.bb_vouchers v join public.bb_strutture s on s.id=v.struttura_id) x));
end $$;
revoke all on function public.bb_tit_stato(text) from public, anon, authenticated;
grant execute on function public.bb_tit_stato(text) to anon, authenticated;

create or replace function public.bb_tit_riscatta(p text,vid text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare v public.bb_vouchers; s text; msg text; ok boolean:=false; oggi_n int;
begin
 perform public.bb_check_tit(p);
 select * into v from public.bb_vouchers where id=upper(trim(vid)) for update;
 if not found then return json_build_object('ok',false,'msg','Codice non trovato'); end if;
 select count(*) into oggi_n from unnest(v.riscatti) t where (t at time zone 'Europe/Rome')::date=public.bb_oggi();
 if v.annullato then msg:='Voucher annullato';
 elsif v.usate>=v.qta then msg:='Già utilizzato interamente';
 elsif public.bb_oggi()>v.data_fine then msg:='Voucher scaduto ('||to_char(v.data_fine,'DD/MM')||')';
 elsif public.bb_oggi()<v.data then msg:='Valido dal '||to_char(v.data,'DD/MM');
 elsif oggi_n>=v.ospiti then msg:='Oggi le '||v.ospiti||' colazioni di questa camera sono già state consegnate';
 else update public.bb_vouchers set usate=usate+1, riscatti=riscatti||now() where id=v.id returning * into v; oggi_n:=oggi_n+1; ok:=true; msg:='Colazione consegnata ('||oggi_n||' di '||v.ospiti||' oggi)'; end if;
 select nome into s from public.bb_strutture where id=v.struttura_id;
 return json_build_object('ok',ok,'msg',msg,'voucher',json_build_object('id',v.id,'fascia',v.fascia,'qta',v.qta,'usate',v.usate,'ospite',v.ospite,'camera',v.camera,'ospiti',v.ospiti,'struttura',s,
   'data',v.data,'data_fine',v.data_fine,'colazione',v.colazione_nome,'tavolo',v.servizio_tavolo,
   'menu',coalesce((select descrizione from public.bb_colazioni where id=v.colazione_id),(select descrizione from public.bb_menu where fascia=v.fascia)),
   'voci',case when v.colazione_id is not null then public.bb_voci_col_json(v.colazione_id) else public.bb_voci_json(v.fascia::int) end,
   'richieste',v.richieste,'extra',public.bb_extra_json(v),'extra_oggi',public.bb_extra_del_giorno(v,public.bb_oggi()),
   'extra_totale',v.extra_totale,'extra_da_pagare',public.bb_extra_da_pagare(v)));
end $$;
revoke all on function public.bb_tit_riscatta(text,text) from public;
grant execute on function public.bb_tit_riscatta(text,text) to anon, authenticated;

-- ===================== recensioni: consenso solo con informativa, fonte della visita, posizione rispetto al bar =====================
create or replace function public.bb_recensioni_consenso(
 psessione uuid, pfinalita text, pacconsento boolean, pversione text, pclient text default '') returns json
language plpgsql security definer set search_path=public,extensions as $$
declare v public.bb_recensioni_visite;
begin
 select * into v from public.bb_recensioni_visite where sessione=psessione and scade>now();
 if not found then raise exception 'Sessione non valida o scaduta'; end if;
 if pfinalita not in ('geolocalizzazione','whatsapp') then raise exception 'Finalità non valida'; end if;
 if pversione<>v.informativa_versione then raise exception 'Informativa aggiornata: ricarica la pagina'; end if;
 -- senza informativa pubblicata un consenso non e' informato: si puo' solo non acconsentire
 if pacconsento and public.bb_cfg('recensioni_informativa_url','')='' then raise exception 'Informativa privacy non ancora pubblicata: non è possibile acconsentire'; end if;
 insert into public.bb_recensioni_consensi(visita_id,finalita,azione,informativa_versione,fonte,ip,client,dettagli)
 values(v.id,pfinalita,case when pacconsento then 'acconsentito' else 'negato' end,v.informativa_versione,v.fonte,public.bb_ip(),left(coalesce(pclient,''),300),jsonb_build_object('azione_esplicita',true));
 if pfinalita='whatsapp' and not pacconsento then
  update public.bb_recensioni_inviti set stato='annullato',aggiornato=now() where visita_id=v.id and stato in ('in_attesa','errore');
 end if;
 return json_build_object('salvato',true,'avvenuto',now());
end $$;
revoke all on function public.bb_recensioni_consenso(uuid,text,boolean,text,text) from public;
grant execute on function public.bb_recensioni_consenso(uuid,text,boolean,text,text) to anon,authenticated;

create or replace function public.bb_recensioni_revoca(psessione uuid, pfinalita text, pclient text default '') returns json
language plpgsql security definer set search_path=public,extensions as $$
declare v public.bb_recensioni_visite;
begin
 select * into v from public.bb_recensioni_visite where sessione=psessione and scade>now();
 if not found then raise exception 'Sessione non valida o scaduta'; end if;
 if pfinalita not in ('geolocalizzazione','whatsapp') then raise exception 'Finalita non valida'; end if;
 insert into public.bb_recensioni_consensi(visita_id,finalita,azione,informativa_versione,fonte,ip,client,dettagli)
 values(v.id,pfinalita,'revocato',v.informativa_versione,v.fonte,public.bb_ip(),left(coalesce(pclient,''),300),jsonb_build_object('azione_esplicita',true));
 if pfinalita='whatsapp' then
  update public.bb_recensioni_inviti set stato='annullato',aggiornato=now() where visita_id=v.id and stato in ('in_attesa','errore');
  update public.bb_recensioni_visite set telefono=null where id=v.id;
 else
  delete from public.bb_recensioni_posizioni where visita_id=v.id;
 end if;
 return json_build_object('revocato',true,'avvenuto',now());
end $$;
revoke all on function public.bb_recensioni_revoca(uuid,text,text) from public,anon,authenticated;
grant execute on function public.bb_recensioni_revoca(uuid,text,text) to anon,authenticated;

-- distanza dal bar e «in sede» (null se le coordinate del bar non sono configurate): solo informazione, nessun blocco
drop function if exists public.bb_recensioni_posizione(uuid,numeric,numeric,numeric);
create or replace function public.bb_recensioni_posizione(psessione uuid, plat numeric, plon numeric, paccuratezza numeric default null) returns json
language plpgsql security definer set search_path=public,extensions as $$
declare v public.bb_recensioni_visite; lat numeric; lon numeric; rag numeric; dist numeric; ins boolean;
begin
 select * into v from public.bb_recensioni_visite where sessione=psessione and scade>now();
 if not found then raise exception 'Sessione non valida o scaduta'; end if;
 if not public.bb_recensioni_consenso_attivo(v.id,'geolocalizzazione') then raise exception 'Consenso geolocalizzazione assente'; end if;
 if plat is null or plon is null or plat not between -90 and 90 or plon not between -180 and 180 then raise exception 'Coordinate non valide'; end if;
 begin
  lat := nullif(public.bb_cfg('bar_lat',''),'')::numeric; lon := nullif(public.bb_cfg('bar_lon',''),'')::numeric;
  rag := coalesce(nullif(public.bb_cfg('bar_raggio_m','300'),'')::numeric,300);
 exception when others then lat := null; lon := null; rag := 300; end;
 if lat is not null and lon is not null then
  dist := round(public.bb_distanza_m(lat,lon,plat,plon),1); ins := dist<=rag;
 end if;
 insert into public.bb_recensioni_posizioni(visita_id,latitudine,longitudine,accuratezza_m,distanza_m,in_sede,rilevato) values(v.id,plat,plon,paccuratezza,dist,ins,clock_timestamp());
 return json_build_object('salvato',true,'distanza_m',dist,'in_sede',ins);
end $$;
revoke all on function public.bb_recensioni_posizione(uuid,numeric,numeric,numeric) from public;
grant execute on function public.bb_recensioni_posizione(uuid,numeric,numeric,numeric) to anon,authenticated;

create or replace function public.bb_tit_recensioni_stato(p text, sid uuid) returns json
language plpgsql security definer set search_path=public,extensions as $$
declare l public.bb_recensioni_link;
begin
 perform public.bb_check_tit(p);
 if not exists(select 1 from public.bb_strutture where id=sid) then raise exception 'Struttura non trovata'; end if;
 insert into public.bb_recensioni_link(struttura_id) values(sid) on conflict(struttura_id) do nothing;
 select * into l from public.bb_recensioni_link where struttura_id=sid;
 return json_build_object(
  'token',l.token,'attivo',l.attivo,
  'config',json_build_object('google_url',public.bb_cfg('recensioni_google_url',''),'tripadvisor_url',public.bb_cfg('recensioni_tripadvisor_url',''),'informativa_versione',public.bb_cfg('recensioni_informativa_versione','2026-10-01-v1'),'informativa_url',public.bb_cfg('recensioni_informativa_url',''),'ritardo_minuti',public.bb_cfg('recensioni_ritardo_minuti','180')::int,
    'bar_lat',public.bb_cfg('bar_lat',''),'bar_lon',public.bb_cfg('bar_lon',''),'bar_raggio_m',public.bb_cfg('bar_raggio_m','300')),
  'visite',(select count(*) from public.bb_recensioni_visite where struttura_id=sid),
  'optin_whatsapp',(select count(*) from public.bb_recensioni_visite v where v.struttura_id=sid and public.bb_recensioni_consenso_attivo(v.id,'whatsapp')),
  'inviti_inviati',(select count(*) from public.bb_recensioni_inviti i join public.bb_recensioni_visite v on v.id=i.visita_id where v.struttura_id=sid and i.stato='inviato'),
  'click_google',(select count(*) from public.bb_recensioni_click c join public.bb_recensioni_visite v on v.id=c.visita_id where v.struttura_id=sid and c.destinazione='google'),
  'click_tripadvisor',(select count(*) from public.bb_recensioni_click c join public.bb_recensioni_visite v on v.id=c.visita_id where v.struttura_id=sid and c.destinazione='tripadvisor'),
  'posizioni',(select json_build_object(
     'in_sede',count(*) filter (where ps.in_sede),
     'fuori_sede',count(*) filter (where ps.in_sede=false),
     'non_nota',count(*) filter (where ps.in_sede is null))
    from public.bb_recensioni_visite v left join lateral (select in_sede from public.bb_recensioni_posizioni q where q.visita_id=v.id order by q.rilevato desc limit 1) ps on true
    where v.struttura_id=sid),
  'visite_recenti',(select coalesce(json_agg(json_build_object(
     'creato',v.creato,'fonte',v.fonte,'completato',v.completato,
     'geo',public.bb_recensioni_consenso_attivo(v.id,'geolocalizzazione'),
     'whatsapp',public.bb_recensioni_consenso_attivo(v.id,'whatsapp'),
     'posizione',case when ps.in_sede then 'in_sede' when ps.in_sede=false then 'fuori_sede' else 'non_nota' end,
     'distanza_m',ps.distanza_m) order by v.creato desc),'[]'::json)
    from (select * from public.bb_recensioni_visite where struttura_id=sid order by creato desc limit 30) v
    left join lateral (select in_sede,distanza_m from public.bb_recensioni_posizioni q where q.visita_id=v.id order by q.rilevato desc limit 1) ps on true));
end $$;
revoke all on function public.bb_tit_recensioni_stato(text,uuid) from public;
grant execute on function public.bb_tit_recensioni_stato(text,uuid) to anon,authenticated;

-- ===================== funzioni legacy con grant ad anon: nessun chiamante in JS ne' in Python (verifica del 02/10/2026) =====================
drop function if exists public.bb_alb_crea_voucher(uuid,text,int,int,date,text);
drop function if exists public.bb_alb_crea_batch(uuid,text,int,int,date,jsonb);
drop function if exists public.bb_tit_menu_set(text,int,text);
drop function if exists public.bb_tit_menu_import(text,jsonb);
drop function if exists public.bb_tit_menu_elimina(text,int);
drop function if exists public.bb_tit_bar_set(text,text,text);
drop function if exists public.bb_tit_voci_salva(text,int,jsonb);
drop function if exists public.bb_pin_stato();
drop function if exists public.bb_tit_tavolo_set(text,uuid,boolean);

notify pgrst, 'reload schema';
