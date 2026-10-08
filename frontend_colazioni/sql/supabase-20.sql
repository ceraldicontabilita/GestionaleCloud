-- v20: sessioni con token, PIN degli albergatori con blocco dei tentativi, recupero PIN,
-- accesso del titolare con la sessione del gestionale (PIN unico del gruppo).
-- Fase 1 (additiva): il vecchio PIN in chiaro funziona ancora; la fase 2 (supabase-21.sql) lo toglie.

alter table bb_strutture add column if not exists recupero_hash text;

create table if not exists bb_sessioni (
  token_hash text primary key,
  ruolo text not null check (ruolo in ('tit','alb')),
  struttura_id uuid references bb_strutture(id) on delete cascade,
  scade timestamptz not null,
  creato timestamptz not null default now());
create index if not exists bb_sessioni_scade on bb_sessioni(scade);
alter table bb_sessioni enable row level security;

create table if not exists bb_tentativi (
  chiave text primary key,
  n int not null default 0,
  primo timestamptz not null default now(),
  blocco timestamptz);
alter table bb_tentativi enable row level security;

create table if not exists bb_richieste_pin (
  id uuid primary key default gen_random_uuid(),
  struttura_id uuid not null references bb_strutture(id) on delete cascade,
  nota text not null default '',
  creato timestamptz not null default now(),
  chiusa boolean not null default false);
alter table bb_richieste_pin enable row level security;

-- ---------- helper (non chiamabili dall'esterno) ----------
create or replace function bb_tok_hash(t text) returns text language sql immutable set search_path=public,extensions as
$$ select encode(digest(coalesce(t,''),'sha256'),'hex') $$;

create or replace function bb_sessione_nuova(prole text, psid uuid, pore int) returns text language plpgsql security definer set search_path=public,extensions as $$
declare t text;
begin
 delete from bb_sessioni where scade<now();
 t := 'tk:'||encode(gen_random_bytes(24),'hex');
 insert into bb_sessioni(token_hash,ruolo,struttura_id,scade) values (bb_tok_hash(t),prole,psid,now()+make_interval(hours=>least(48,greatest(1,pore))));
 return t;
end $$;

create or replace function bb_sessione_ok(p text, prole text, psid uuid default null) returns boolean language sql stable security definer set search_path=public,extensions as $$
 select coalesce(p,'') like 'tk:%' and exists(select 1 from bb_sessioni s where s.token_hash=bb_tok_hash(p) and s.ruolo=prole and s.scade>now() and (psid is null or s.struttura_id=psid)) $$;

create or replace function bb_blocco(pchiave text) returns int language sql stable security definer set search_path=public as $$
 select coalesce((select greatest(0,ceil(extract(epoch from (blocco-now())))::int) from bb_tentativi where chiave=pchiave and blocco>now()),0) $$;

create or replace function bb_fallito(pchiave text, psoglia int default 5) returns int language plpgsql security definer set search_path=public as $$
declare r bb_tentativi;
begin
 insert into bb_tentativi(chiave,n,primo) values (pchiave,1,now())
 on conflict (chiave) do update set
   n = case when bb_tentativi.primo < now()-interval '15 minutes' then 1 else bb_tentativi.n+1 end,
   primo = case when bb_tentativi.primo < now()-interval '15 minutes' then now() else bb_tentativi.primo end,
   blocco = null
 returning * into r;
 if r.n >= psoglia then update bb_tentativi set blocco=now()+interval '15 minutes' where chiave=pchiave; end if;
 return greatest(0,psoglia-r.n);
end $$;

create or replace function bb_tentativi_ok(pchiave text) returns void language sql security definer set search_path=public as
$$ delete from bb_tentativi where chiave=pchiave $$;

create or replace function bb_ip() returns text language sql stable set search_path=public as $$
 select coalesce(nullif(trim(split_part(coalesce((nullif(current_setting('request.headers',true),'')::jsonb)->>'x-forwarded-for',''),',',1)),''),'?') $$;

create or replace function bb_codice_recupero() returns text language plpgsql volatile set search_path=public,extensions as $$
declare al text:='ABCDEFGHJKMNPQRSTUVWXYZ23456789'; b bytea:=gen_random_bytes(8); s text:=''; i int;
begin
 for i in 0..7 loop s := s||substr(al,(get_byte(b,i)%31)+1,1); end loop;
 return substr(s,1,4)||'-'||substr(s,5,4);
end $$;

create or replace function bb_norm_codice(c text) returns text language sql immutable as
$$ select upper(regexp_replace(coalesce(c,''),'[^A-Za-z0-9]','','g')) $$;

revoke all on function bb_tok_hash(text), bb_sessione_nuova(text,uuid,int), bb_sessione_ok(text,text,uuid), bb_blocco(text), bb_fallito(text,int), bb_tentativi_ok(text), bb_ip(), bb_codice_recupero(), bb_norm_codice(text) from public, anon, authenticated;

-- ---------- controlli (fase 1: token oppure vecchio PIN) ----------
create or replace function bb_check_tit(p text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 if bb_sessione_ok(p,'tit') then return; end if;
 if bb_pin_off() then return; end if;
 perform bb_check_tit_strict(p);
end $$;

create or replace function bb_check_tit_strict(p text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 if bb_sessione_ok(p,'tit') then return; end if;
 if not exists(select 1 from bb_config where k='tit_pin' and v=crypt(p,v)) then raise exception 'Sessione scaduta: rientra con il PIN'; end if;
end $$;

create or replace function bb_check_alb(sid uuid, p text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 if not exists(select 1 from bb_strutture where id=sid and pin_hash is not null) then raise exception 'Accesso non ancora attivato'; end if;
 if bb_sessione_ok(p,'alb',sid) then return; end if;
 if bb_pin_off() then return; end if;
 if not exists(select 1 from bb_strutture where id=sid and pin_hash=crypt(p,pin_hash)) then raise exception 'Sessione scaduta: rientra con il PIN'; end if;
end $$;

-- ---------- titolare: sessione aperta dal backend del gestionale ----------
create or replace function bb_tit_sessione_apri(pore int default 12) returns json language plpgsql security definer set search_path=public,extensions as $$
declare t text;
begin
 perform public.gc_assert_runtime_secret();
 t := bb_sessione_nuova('tit',null,pore);
 return json_build_object('token',t,'scade',now()+make_interval(hours=>least(48,greatest(1,pore))));
end $$;
revoke all on function bb_tit_sessione_apri(int) from public;
grant execute on function bb_tit_sessione_apri(int) to anon, authenticated;

-- ---------- albergatore: accesso con PIN e blocco dei tentativi ----------
create or replace function bb_alb_login(paccesso text, ppin text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare s bb_strutture; k text; ki text; sec int; rest int;
begin
 select * into s from bb_strutture where accesso=lower(trim(coalesce(paccesso,'')));
 if not found or s.pin_hash is null then return json_build_object('ok',false,'msg','Accesso non ancora attivato'); end if;
 k := 'alb:'||s.accesso; ki := 'ip:'||bb_ip();
 sec := greatest(bb_blocco(k),bb_blocco(ki));
 if sec>0 then return json_build_object('ok',false,'bloccato',sec,'msg','Troppi tentativi: riprova tra '||ceil(sec/60.0)::int||' minuti'); end if;
 if s.pin_hash = crypt(coalesce(ppin,''),s.pin_hash) then
  perform bb_tentativi_ok(k);
  return json_build_object('ok',true,'token',bb_sessione_nuova('alb',s.id,12),'sid',s.id,'nome',s.nome);
 end if;
 rest := bb_fallito(k,5); perform bb_fallito(ki,25);
 return json_build_object('ok',false,'restanti',rest,'msg',case when rest>0 then 'PIN errato: ti restano '||rest||' tentativi' else 'Troppi tentativi: riprova tra 15 minuti' end);
end $$;
grant execute on function bb_alb_login(text,text) to anon, authenticated;

create or replace function bb_alb_logout(p text) returns void language sql security definer set search_path=public,extensions as
$$ delete from bb_sessioni where token_hash=bb_tok_hash(p) $$;
grant execute on function bb_alb_logout(text) to anon, authenticated;

-- ---------- registrazione: sceglie il PIN e riceve il codice di recupero ----------
create or replace function bb_invito_accetta(token text, ppin text, pindirizzo text, ptelefono text, pemail text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare s bb_strutture; rec text;
begin
 select * into s from bb_strutture where invito_token=lower(trim(token)) for update;
 if not found then raise exception 'Invito non valido o già utilizzato'; end if;
 if coalesce(length(ppin),0)<4 or length(ppin)>20 then raise exception 'Il PIN deve avere almeno 4 caratteri'; end if;
 rec := bb_codice_recupero();
 update bb_strutture set pin_hash=crypt(ppin,gen_salt('bf')), recupero_hash=crypt(bb_norm_codice(rec),gen_salt('bf')), invito_token=null,
   indirizzo=coalesce(nullif(left(trim(coalesce(pindirizzo,'')),150),''),indirizzo), telefono=coalesce(nullif(left(trim(coalesce(ptelefono,'')),30),''),telefono), email=coalesce(nullif(left(trim(coalesce(pemail,'')),100),''),email)
   where id=s.id;
 update bb_richieste_pin set chiusa=true where struttura_id=s.id and not chiusa;
 delete from bb_sessioni where struttura_id=s.id;
 return json_build_object('id',s.id,'accesso',s.accesso,'nome',s.nome,'recupero',rec,'token',bb_sessione_nuova('alb',s.id,12));
end $$;

-- ---------- recupero del PIN con il codice ----------
create or replace function bb_alb_recupera(paccesso text, pcodice text, pnuovo text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare s bb_strutture; k text; ki text; sec int; rest int; rec text;
begin
 select * into s from bb_strutture where accesso=lower(trim(coalesce(paccesso,'')));
 if not found or s.pin_hash is null then return json_build_object('ok',false,'msg','Accesso non ancora attivato'); end if;
 k := 'rec:'||s.accesso; ki := 'ip:'||bb_ip();
 sec := greatest(bb_blocco(k),bb_blocco(ki));
 if sec>0 then return json_build_object('ok',false,'bloccato',sec,'msg','Troppi tentativi: riprova tra '||ceil(sec/60.0)::int||' minuti'); end if;
 if coalesce(length(pnuovo),0)<4 or length(pnuovo)>20 then return json_build_object('ok',false,'msg','Il nuovo PIN deve avere almeno 4 caratteri'); end if;
 if s.recupero_hash is null then return json_build_object('ok',false,'msg','Per questo albergo non c''è un codice di recupero: chiedi un nuovo invito al bar','senza_codice',true); end if;
 if s.recupero_hash <> crypt(bb_norm_codice(pcodice),s.recupero_hash) then
  rest := bb_fallito(k,5); perform bb_fallito(ki,25);
  return json_build_object('ok',false,'restanti',rest,'msg',case when rest>0 then 'Codice errato: ti restano '||rest||' tentativi' else 'Troppi tentativi: riprova tra 15 minuti' end);
 end if;
 perform bb_tentativi_ok(k); perform bb_tentativi_ok('alb:'||s.accesso);
 rec := bb_codice_recupero();
 update bb_strutture set pin_hash=crypt(pnuovo,gen_salt('bf')), recupero_hash=crypt(bb_norm_codice(rec),gen_salt('bf')) where id=s.id;
 delete from bb_sessioni where struttura_id=s.id;
 update bb_richieste_pin set chiusa=true where struttura_id=s.id and not chiusa;
 return json_build_object('ok',true,'recupero',rec,'token',bb_sessione_nuova('alb',s.id,12),'sid',s.id,'nome',s.nome);
end $$;
grant execute on function bb_alb_recupera(text,text,text) to anon, authenticated;

-- ---------- se ha perso anche il codice: richiesta al bar ----------
create or replace function bb_alb_richiedi_aiuto(paccesso text, pnota text) returns json language plpgsql security definer set search_path=public as $$
declare s bb_strutture;
begin
 select * into s from bb_strutture where accesso=lower(trim(coalesce(paccesso,'')));
 if found and not exists(select 1 from bb_richieste_pin where struttura_id=s.id and not chiusa and creato>now()-interval '10 minutes') then
  insert into bb_richieste_pin(struttura_id,nota) values (s.id,left(trim(coalesce(pnota,'')),200));
 end if;
 return json_build_object('ok',true);
end $$;
grant execute on function bb_alb_richiedi_aiuto(text,text) to anon, authenticated;

-- ---------- dal profilo: cambia PIN e rigenera il codice ----------
create or replace function bb_alb_pin_cambia(sid uuid, p text, pvecchio text, pnuovo text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare s bb_strutture; k text; sec int; rest int;
begin
 perform bb_check_alb(sid,p);
 select * into s from bb_strutture where id=sid;
 k := 'alb:'||s.accesso; sec := bb_blocco(k);
 if sec>0 then return json_build_object('ok',false,'msg','Troppi tentativi: riprova tra '||ceil(sec/60.0)::int||' minuti'); end if;
 if s.pin_hash <> crypt(coalesce(pvecchio,''),s.pin_hash) then
  rest := bb_fallito(k,5);
  return json_build_object('ok',false,'msg','Il PIN attuale non è corretto');
 end if;
 if coalesce(length(pnuovo),0)<4 or length(pnuovo)>20 then return json_build_object('ok',false,'msg','Il nuovo PIN deve avere almeno 4 caratteri'); end if;
 perform bb_tentativi_ok(k);
 update bb_strutture set pin_hash=crypt(pnuovo,gen_salt('bf')) where id=sid;
 delete from bb_sessioni where struttura_id=sid and token_hash<>bb_tok_hash(p);
 return json_build_object('ok',true);
end $$;
grant execute on function bb_alb_pin_cambia(uuid,text,text,text) to anon, authenticated;

create or replace function bb_alb_recupero_nuovo(sid uuid, p text, ppin text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare s bb_strutture; k text; sec int; rec text;
begin
 perform bb_check_alb(sid,p);
 select * into s from bb_strutture where id=sid;
 k := 'alb:'||s.accesso; sec := bb_blocco(k);
 if sec>0 then return json_build_object('ok',false,'msg','Troppi tentativi: riprova tra '||ceil(sec/60.0)::int||' minuti'); end if;
 if s.pin_hash <> crypt(coalesce(ppin,''),s.pin_hash) then perform bb_fallito(k,5); return json_build_object('ok',false,'msg','Il PIN non è corretto'); end if;
 perform bb_tentativi_ok(k);
 rec := bb_codice_recupero();
 update bb_strutture set recupero_hash=crypt(bb_norm_codice(rec),gen_salt('bf')) where id=sid;
 return json_build_object('ok',true,'recupero',rec);
end $$;
grant execute on function bb_alb_recupero_nuovo(uuid,text,text) to anon, authenticated;

-- ---------- titolare: richieste di aiuto dei B&B ----------
create or replace function bb_tit_richiesta_chiudi(p text, pid uuid) returns void language plpgsql security definer set search_path=public,extensions as $$
begin perform bb_check_tit(p); update bb_richieste_pin set chiusa=true where id=pid; end $$;
grant execute on function bb_tit_richiesta_chiudi(text,uuid) to anon, authenticated;

create or replace function bb_tit_richieste_pin(p text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit(p);
 return (select coalesce(json_agg(json_build_object('id',r.id,'struttura_id',s.id,'struttura',s.nome,'telefono',s.telefono,'nota',r.nota,'creato',r.creato) order by r.creato desc),'[]'::json)
   from bb_richieste_pin r join bb_strutture s on s.id=r.struttura_id where not r.chiusa);
end $$;
grant execute on function bb_tit_richieste_pin(text) to anon, authenticated;
