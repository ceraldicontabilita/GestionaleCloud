-- Schema ridotto esclusivamente per un database PostgreSQL locale usa e getta.
-- La migrazione sottoposta a prova rimane il file di produzione, senza copie.
create schema extensions;
create extension pgcrypto with schema extensions;
create schema menu;
do $$ begin
 if not exists(select 1 from pg_roles where rolname='anon') then create role anon; end if;
 if not exists(select 1 from pg_roles where rolname='authenticated') then create role authenticated; end if;
end $$;

create table public.bb_strutture (
 id uuid primary key default extensions.gen_random_uuid(),
 nome text not null,
 disattivata_il timestamptz
);
create table public.bb_movimenti (
 id uuid primary key default extensions.gen_random_uuid(),
 struttura_id uuid not null references public.bb_strutture(id),
 tipo text not null check (tipo in ('ricarica','prenotazione','rimborso')),
 importo numeric(10,2) not null,
 nota text not null default '',
 confermato boolean not null default true,
 riferimento_esterno text unique,
 t timestamptz not null default now()
);
create table public.bb_vouchers (
 id text primary key,
 struttura_id uuid not null references public.bb_strutture(id),
 fascia numeric(10,2) not null,
 qta integer not null,
 usate integer not null default 0,
 data date not null,
 data_fine date not null,
 ospite text not null default 'Ospite',
 camera text not null default '',
 ospiti integer not null default 1,
 colazione_nome text,
 annullato boolean not null default false,
 riscatti timestamptz[] not null default '{}',
 creato timestamptz not null default now(),
 richieste_agg timestamptz
);
alter table public.bb_strutture enable row level security;
alter table public.bb_movimenti enable row level security;
alter table public.bb_vouchers enable row level security;
revoke all on public.bb_strutture,public.bb_movimenti,public.bb_vouchers from public,anon,authenticated;
create table menu.menu_products (id integer primary key,name_it text not null,visible boolean not null default true);

-- Solo il saldo canonico viene esercitato: somme dei movimenti confermati.
create function public.bb_saldo(sid uuid) returns numeric language sql stable security definer as $$
 select coalesce(sum(importo),0) from public.bb_movimenti where struttura_id=sid and confermato
$$;
create function public.bb_oggi() returns date language sql stable as $$
 select (now() at time zone 'Europe/Rome')::date
$$;
create function public.bb_check_tit(p text) returns void language plpgsql as $$
begin if p is distinct from 'tk:bar-test' then raise exception 'Sessione titolare non valida'; end if; end $$;
create function public.bb_check_alb(sid uuid,p text) returns void language plpgsql as $$
begin
 if p is distinct from 'tk:'||sid::text or not exists(select 1 from public.bb_strutture where id=sid and disattivata_il is null)
 then raise exception 'Sessione albergatore non valida'; end if;
end $$;
create table public.qa_ospite_limite (id boolean primary key default true,n integer not null default 0);
insert into public.qa_ospite_limite(id) values(true);
create function public.bb_limite_ospite() returns void language plpgsql as $$
declare richieste integer;
begin
 update public.qa_ospite_limite set n=n+1 where id returning n into richieste;
 if richieste>60 then raise exception 'Limite ospite raggiunto'; end if;
end $$;
create function public.bb_bar_pubblico() returns json language sql as $$ select '{"nome":"Bar test"}'::json $$;

-- Gli ingressi soggiorno preesistenti sono sentinelle: attestano soltanto
-- la delega dei casi estranei ai pacchetti, non il loro collaudo completo.
create function public.bb_tit_riscatta(p text,vid text) returns json language sql as $$
 select json_build_object('legacy','riscatta','id',vid)
$$;
create function public.bb_annulla(vid text,pmotivo text,pda text) returns json language sql as $$
 select json_build_object('legacy','annulla','id',vid)
$$;
create function public.bb_ospite_json(vid text) returns json language sql as $$
 select json_build_object('legacy','ospite','id',vid)
$$;
create function public.bb_ospite(vid text) returns json language plpgsql as $$
begin
 perform public.bb_limite_ospite();
 return public.bb_ospite_json(vid);
end
$$;
create function public.bb_ospite_salva(vid text,prichieste jsonb,pextra jsonb,pgiorno date default null)
 returns json language sql as $$ select json_build_object('legacy','ospite_salva','id',vid) $$;
create function public.bb_ospite_menu_salva(vid text,pgiorno date,righe jsonb)
 returns json language sql as $$ select json_build_object('legacy','menu_salva','id',vid) $$;
-- Una proiezione soggiorno non deve nemmeno valutare una riga pacchetto:
-- intercetta filtri applicati solo dopo avere aggregato tutti i voucher.
create function public.qa_soggiorno_json(vid text) returns json language plpgsql as $$
begin
 if exists(select 1 from public.bb_vouchers where id=vid and pacchetto_id is not null) then
  raise exception 'Voucher pacchetto valutato dalla proiezione soggiorni';
 end if;
 return json_build_object('id',vid);
end $$;
create function public.bb_alb_stato(sid uuid,p text) returns json language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_check_alb(sid,p);
 return json_build_object('legacy','stato_alb','vouchers',coalesce((
  select json_agg(public.qa_soggiorno_json(x.id)) from public.bb_vouchers x where x.struttura_id=sid),'[]'::json));
end $$;
create function public.bb_tit_stato(p text) returns json language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_check_tit(p);
 return json_build_object('legacy','stato_tit','vouchers',coalesce((
  select json_agg(public.qa_soggiorno_json(v.id)) from public.bb_vouchers v join public.bb_strutture s on s.id=v.struttura_id),'[]'::json));
end $$;
create table public.qa_notifiche(voucher_id text not null);
create function public.bb_accoda_notifica_voucher() returns trigger language plpgsql as $$
begin insert into public.qa_notifiche values(new.id); return new; end $$;
create trigger bb_vouchers_notifica_prenotazione after insert on public.bb_vouchers
 for each row execute function public.bb_accoda_notifica_voucher();

insert into menu.menu_products(id,name_it) values
 (152788,'Croissant vuoto'),(153797,'Cornetto crema'),(153800,'Cornetto cioccolato'),(153801,'Brioche'),
 (153867,'Sfogliatella frolla'),(153868,'Sfogliatella riccia'),
 (153883,'Focaccia Margherita'),(153887,'Rustico ricotta'),(153886,'Parigina'),
 (153756,'Caffè espresso'),(153754,'Cappuccino'),(639287,'Tè caldo'),(153822,'Cioccolata calda'),
 (153895,'Acqua 33 cl'),(153898,'Coca-Cola'),(153901,'Aranciata'),
 (153914,'Tè pesca'),(153915,'Tè limone'),(153918,'Succo pera'),
 (153928,'Succo pesca'),(153924,'Succo albicocca'),(153925,'Succo ananas');
