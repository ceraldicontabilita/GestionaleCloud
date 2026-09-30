-- Colazioni B&B · schema Supabase
-- Tabelle chiuse da RLS (nessuna policy): tutto l'accesso passa dalle funzioni bb_* (security definer),
-- che verificano il PIN di albergatore o titolare. Il saldo è sempre calcolato dai movimenti.

create extension if not exists pgcrypto with schema extensions;

create table if not exists bb_config (k text primary key, v text not null);
create table if not exists bb_menu (fascia int primary key, descrizione text not null);
create table if not exists bb_strutture (
  id uuid primary key default gen_random_uuid(),
  nome text not null, indirizzo text not null default '',
  pin_hash text not null,
  fasce int[] not null default '{3,5,10,12}',
  creato timestamptz not null default now());
create table if not exists bb_movimenti (
  id uuid primary key default gen_random_uuid(),
  struttura_id uuid not null references bb_strutture(id) on delete cascade,
  t timestamptz not null default now(),
  tipo text not null check (tipo in ('ricarica','prenotazione','rimborso')),
  importo numeric(10,2) not null,
  nota text not null default '',
  confermato boolean not null default true);
create table if not exists bb_vouchers (
  id text primary key,
  struttura_id uuid not null references bb_strutture(id) on delete cascade,
  fascia int not null, qta int not null check (qta between 1 and 50),
  usate int not null default 0,
  data date not null, ospite text not null default 'Ospite',
  creato timestamptz not null default now(),
  riscatti timestamptz[] not null default '{}');
create index if not exists bb_vouchers_data on bb_vouchers(data);
create index if not exists bb_movimenti_s on bb_movimenti(struttura_id);

alter table bb_config enable row level security;
alter table bb_menu enable row level security;
alter table bb_strutture enable row level security;
alter table bb_movimenti enable row level security;
alter table bb_vouchers enable row level security;
revoke all on bb_config, bb_menu, bb_strutture, bb_movimenti, bb_vouchers from anon, authenticated;

insert into bb_menu values
 (3,'Dolce + bevanda calda'),(4,'Dolce + bevanda calda + acqua'),(5,'Dolce + salato + bevanda calda'),
 (6,'Dolce + salato + bevanda calda + succo'),(7,'2 dolci + bevanda calda + succo'),
 (8,'Dolce + salato + cappuccino + spremuta'),(9,'Colazione completa dolce e salato'),
 (10,'Pizzetta + bibita'),(11,'Pizzetta + dolce + bibita'),(12,'Full English breakfast'),
 (15,'Full English breakfast + spremuta + dolce')
on conflict do nothing;
insert into bb_config values ('tit_pin', extensions.crypt('CAMBIAMI', extensions.gen_salt('bf'))) on conflict do nothing;

-- ===== helper interni =====
create or replace function bb_oggi() returns date language sql stable as $$ select (now() at time zone 'Europe/Rome')::date $$;
create or replace function bb_saldo(sid uuid) returns numeric language sql stable as
$$ select coalesce(sum(importo),0) from bb_movimenti where struttura_id=sid and confermato $$;
create or replace function bb_check_tit(p text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin if not exists(select 1 from bb_config where k='tit_pin' and v=crypt(p,v)) then raise exception 'PIN errato'; end if; end $$;
create or replace function bb_check_alb(sid uuid,p text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin if not exists(select 1 from bb_strutture where id=sid and pin_hash=crypt(p,pin_hash)) then raise exception 'PIN errato'; end if; end $$;
revoke execute on function bb_oggi(), bb_saldo(uuid), bb_check_tit(text), bb_check_alb(uuid,text) from public, anon, authenticated;

-- ===== pubbliche =====
create or replace function bb_strutture_pubbliche() returns json language sql security definer set search_path=public as
$$ select coalesce(json_agg(json_build_object('id',id,'nome',nome) order by nome),'[]'::json) from bb_strutture $$;

create or replace function bb_menu_pubblico() returns json language sql security definer set search_path=public as
$$ select coalesce(json_object_agg(fascia::text,descrizione),'{}'::json) from bb_menu $$;

create or replace function bb_ospite(vid text) returns json language sql security definer set search_path=public as
$$ select json_build_object('id',v.id,'fascia',v.fascia,'qta',v.qta,'usate',v.usate,'data',v.data,'ospite',v.ospite,
   'struttura',s.nome,'indirizzo',s.indirizzo,'menu',(select descrizione from bb_menu where fascia=v.fascia))
   from bb_vouchers v join bb_strutture s on s.id=v.struttura_id where v.id=upper(trim(vid)) $$;

-- ===== albergatore =====
create or replace function bb_alb_stato(sid uuid,p text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_alb(sid,p);
 return json_build_object(
  'struttura',(select json_build_object('id',id,'nome',nome,'indirizzo',indirizzo,'fasce',fasce,'saldo',bb_saldo(id)) from bb_strutture where id=sid),
  'movimenti',(select coalesce(json_agg(m order by m.t desc),'[]'::json) from (select id,t,tipo,importo,nota,confermato from bb_movimenti where struttura_id=sid) m),
  'vouchers',(select coalesce(json_agg(v order by v.creato desc),'[]'::json) from (select id,fascia,qta,usate,data,ospite,creato from bb_vouchers where struttura_id=sid) v));
end $$;

create or replace function bb_alb_crea_voucher(sid uuid,p text,pfascia int,pqta int,pdata date,pospite text) returns json
language plpgsql security definer set search_path=public,extensions as $$
declare s bb_strutture; vid text; tot numeric;
begin
 perform bb_check_alb(sid,p);
 select * into s from bb_strutture where id=sid for update;
 if not (pfascia = any(s.fasce)) then raise exception 'Menu non attivo per questa struttura'; end if;
 if pqta<1 or pqta>50 then raise exception 'Quantità non valida'; end if;
 if pdata<bb_oggi() then raise exception 'Data nel passato'; end if;
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
 if imp<5 or imp>2000 then raise exception 'Importo non valido'; end if;
 insert into bb_movimenti(struttura_id,tipo,importo,nota,confermato) values (sid,'ricarica',imp,'Ricarica richiesta (in attesa di conferma)',false);
end $$;

-- ===== titolare =====
create or replace function bb_tit_stato(p text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit(p);
 return json_build_object(
  'oggi',bb_oggi(),
  'strutture',(select coalesce(json_agg(x order by x.nome),'[]'::json) from (select id,nome,indirizzo,fasce,bb_saldo(id) saldo from bb_strutture) x),
  'attesa',(select coalesce(json_agg(x order by x.t),'[]'::json) from (select m.id,m.t,m.importo,s.nome from bb_movimenti m join bb_strutture s on s.id=m.struttura_id where not m.confermato) x),
  'vouchers',(select coalesce(json_agg(x order by x.creato desc),'[]'::json) from (select v.id,v.struttura_id,s.nome struttura,v.fascia,v.qta,v.usate,v.data,v.ospite,v.creato from bb_vouchers v join bb_strutture s on s.id=v.struttura_id) x),
  'menu',bb_menu_pubblico());
end $$;

create or replace function bb_tit_riscatta(p text,vid text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare v bb_vouchers; s text; msg text; ok boolean:=false;
begin
 perform bb_check_tit(p);
 select * into v from bb_vouchers where id=upper(trim(vid)) for update;
 if not found then return json_build_object('ok',false,'msg','Codice non trovato'); end if;
 if v.usate>=v.qta then msg:='Già utilizzato interamente';
 elsif v.data<bb_oggi() then msg:='Voucher scaduto ('||v.data||')';
 elsif v.data>bb_oggi() then msg:='Valido dal '||v.data;
 else update bb_vouchers set usate=usate+1, riscatti=riscatti||now() where id=v.id returning * into v; ok:=true; msg:='Colazione consegnata'; end if;
 select nome into s from bb_strutture where id=v.struttura_id;
 return json_build_object('ok',ok,'msg',msg,'voucher',json_build_object('id',v.id,'fascia',v.fascia,'qta',v.qta,'usate',v.usate,'ospite',v.ospite,'struttura',s,
   'menu',(select descrizione from bb_menu where fascia=v.fascia)));
end $$;

create or replace function bb_tit_conferma_ricarica(p text,mid uuid) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit(p);
 update bb_movimenti set confermato=true, nota='Ricarica confermata dal bar' where id=mid and tipo='ricarica' and not confermato;
end $$;

create or replace function bb_tit_ricarica_manuale(p text,sid uuid,imp numeric) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit(p);
 if imp<=0 then raise exception 'Importo non valido'; end if;
 insert into bb_movimenti(struttura_id,tipo,importo,nota) values (sid,'ricarica',imp,'Ricarica registrata dal bar');
end $$;

create or replace function bb_tit_menu_set(p text,pfascia int,pdesc text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit(p);
 update bb_menu set descrizione=pdesc where fascia=pfascia;
end $$;

create or replace function bb_tit_struttura_salva(p text,sid uuid,pnome text,pindirizzo text,ppin text,pfasce int[]) returns json
language plpgsql security definer set search_path=public,extensions as $$
declare nid uuid:=sid;
begin
 perform bb_check_tit(p);
 if sid is null then
  if coalesce(length(ppin),0)<4 then raise exception 'PIN minimo 4 cifre'; end if;
  insert into bb_strutture(nome,indirizzo,pin_hash,fasce) values (pnome,coalesce(pindirizzo,''),crypt(ppin,gen_salt('bf')),coalesce(pfasce,'{3,5,10,12}')) returning id into nid;
 else
  update bb_strutture set nome=coalesce(pnome,nome), indirizzo=coalesce(pindirizzo,indirizzo), fasce=coalesce(pfasce,fasce),
    pin_hash=case when ppin is null or ppin='' then pin_hash else crypt(ppin,gen_salt('bf')) end where id=sid;
 end if;
 return json_build_object('id',nid);
end $$;

-- solo le funzioni "pubbliche" sono chiamabili dal browser
do $$ declare f record; begin
 for f in select p.oid::regprocedure as sig from pg_proc p join pg_namespace n on n.oid=p.pronamespace
          where n.nspname='public' and p.proname in ('bb_strutture_pubbliche','bb_menu_pubblico','bb_ospite','bb_alb_stato','bb_alb_crea_voucher','bb_alb_ricarica',
          'bb_tit_stato','bb_tit_riscatta','bb_tit_conferma_ricarica','bb_tit_ricarica_manuale','bb_tit_menu_set','bb_tit_struttura_salva')
 loop execute format('revoke all on function %s from public',f.sig); execute format('grant execute on function %s to anon',f.sig); end loop; end $$;
