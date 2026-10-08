-- Struttura recuperata dal registro Supabase (20261004013531) il 08/10/2026.
-- Escluse copie di prodotti, instradamenti/stampanti legacy e orari applicativi.
-- Conservate soltanto configurazioni strutturali; nessun dato operativo storico.
create schema if not exists catalogo;
create table catalogo.orari (
  id            bigint generated always as identity primary key,
  ambito        text not null check (ambito in ('tutti','menu','bb')),
  struttura_id  uuid references public.bb_strutture(id) on delete cascade,
  livello       text not null check (livello in ('categoria','sottocategoria','prodotto')),
  riferimento_id integer not null,
  giorni        smallint[] check (giorni is null or giorni <@ array[1,2,3,4,5,6,7]::smallint[]),  -- 1=lunedì … 7=domenica; null = tutti
  dalle         time not null,
  alle          time not null,
  attivo        boolean not null default true,
  nota          text,
  aggiornato_il timestamptz not null default now(),
  aggiornato_da text,
  constraint orari_struttura_solo_bb check (struttura_id is null or ambito = 'bb')
);
comment on table catalogo.orari is 'Fasce orarie in cui una categoria, sottocategoria o prodotto è ordinabile. Senza righe attive = sempre disponibile. Più righe sullo stesso riferimento = unione delle fasce. Una riga con struttura_id vale solo per quella struttura e sostituisce le righe generali sullo stesso riferimento.';
create index orari_rif on catalogo.orari (livello, riferimento_id) where attivo;
create index orari_struttura on catalogo.orari (struttura_id) where struttura_id is not null;
create table catalogo.esauriti (
  prodotto_id   integer primary key,
  esaurito      boolean not null default true,
  dal           timestamptz not null default now(),
  fino_a        timestamptz,            -- null = finché non viene tolta la spunta; altrimenti torna disponibile da solo
  motivo        text,
  aggiornato_il timestamptz not null default now(),
  aggiornato_da text
);
comment on table catalogo.esauriti is 'Prodotti finiti: spunta "non disponibile" valida su tutti i canali (menù pubblico, B&B, cassa). fino_a permette la riattivazione automatica (es. domani alle 6).';
create table catalogo.log (
  id          bigint generated always as identity primary key,
  quando      timestamptz not null default now(),
  tabella     text not null,
  operazione  text not null,
  chiave      text not null,
  prima       jsonb,
  dopo        jsonb,
  utente      text
);
comment on table catalogo.log is 'Audit: solo inserimenti, mai modifiche. Ogni cambio a orari ed esauriti finisce qui.';
create or replace function catalogo.log_trigger() returns trigger language plpgsql as $$
declare k text; u text;
begin
  if tg_table_name = 'orari' then k := coalesce(new.id, old.id)::text; else k := coalesce(new.prodotto_id, old.prodotto_id)::text; end if;
  u := coalesce(new.aggiornato_da, old.aggiornato_da, current_setting('request.jwt.claim.email', true), session_user::text);
  insert into catalogo.log(tabella, operazione, chiave, prima, dopo, utente)
  values (tg_table_name, tg_op, k, case when tg_op <> 'INSERT' then to_jsonb(old) end, case when tg_op <> 'DELETE' then to_jsonb(new) end, u);
  return coalesce(new, old);
end $$;
create trigger orari_log after insert or update or delete on catalogo.orari for each row execute function catalogo.log_trigger();
create trigger esauriti_log after insert or update or delete on catalogo.esauriti for each row execute function catalogo.log_trigger();
create or replace function catalogo.touch() returns trigger language plpgsql as $$
begin new.aggiornato_il := now(); return new; end $$;
create trigger orari_touch before update on catalogo.orari for each row execute function catalogo.touch();
create trigger esauriti_touch before update on catalogo.esauriti for each row execute function catalogo.touch();
create or replace function catalogo.ora_locale(p_at timestamptz default now()) returns timestamp
language sql immutable as $$ select p_at at time zone 'Europe/Rome' $$;
create or replace function catalogo.in_orario(p_livello text, p_rif integer, p_ambito text, p_struttura uuid, p_at timestamptz default now())
returns boolean language plpgsql stable as $$
declare
  t  timestamp := catalogo.ora_locale(p_at);
  h  time := t::time;
  g  smallint := extract(isodow from t)::smallint;
  righe catalogo.orari[];
begin
  if p_struttura is not null then
    select array_agg(o) into righe from catalogo.orari o
     where o.attivo and o.livello = p_livello and o.riferimento_id = p_rif and o.struttura_id = p_struttura;
  end if;
  if righe is null or cardinality(righe) = 0 then
    select array_agg(o) into righe from catalogo.orari o
     where o.attivo and o.livello = p_livello and o.riferimento_id = p_rif and o.struttura_id is null
       and o.ambito in ('tutti', p_ambito);
  end if;
  if righe is null or cardinality(righe) = 0 then return true; end if;
  return exists (
    select 1 from unnest(righe) o
    where (o.giorni is null or g = any(o.giorni))
      and case when o.dalle <= o.alle then h >= o.dalle and h < o.alle      -- fascia nella giornata
               else h >= o.dalle or h < o.alle end                          -- fascia a cavallo di mezzanotte
  );
end $$;
create or replace function catalogo.esaurito(p_prodotto integer, p_at timestamptz default now()) returns boolean
language sql stable as $$
  select coalesce((select e.esaurito and (e.fino_a is null or e.fino_a > p_at) from catalogo.esauriti e where e.prodotto_id = p_prodotto), false)
$$;
create or replace function catalogo.disponibile(p_prodotto integer, p_categoria integer, p_sottocategoria integer, p_ambito text, p_struttura uuid default null, p_at timestamptz default now())
returns boolean language sql stable as $$
  select not catalogo.esaurito(p_prodotto, p_at)
     and catalogo.in_orario('prodotto', p_prodotto, p_ambito, p_struttura, p_at)
     and (p_sottocategoria is null or catalogo.in_orario('sottocategoria', p_sottocategoria, p_ambito, p_struttura, p_at))
     and (p_categoria is null or catalogo.in_orario('categoria', p_categoria, p_ambito, p_struttura, p_at))
$$;
create or replace view menu.menu_products_disponibili as
  select p.* from menu.menu_products p
  where p.visible and catalogo.disponibile(p.id, p.category_id, p.subcategory_id, 'menu', null, now());
comment on view menu.menu_products_disponibili is 'Menù pubblico: prodotti visibili, non esauriti e in fascia oraria adesso (ora di Napoli).';
create or replace function public.bb_prodotti_disponibili(p_struttura uuid, p_at timestamptz default now())
returns setof public.bb_prodotti language sql stable as $$
  select b.* from public.bb_prodotti b
  where b.visibile and catalogo.disponibile(b.id, b.cat_id, b.sub_id, 'bb', p_struttura, p_at)
$$;
comment on function public.bb_prodotti_disponibili is 'B&B: prodotti ordinabili adesso per gli ospiti di quella struttura (orari della struttura, altrimenti orari generali).';
grant usage on schema catalogo to service_role, authenticated, anon;
grant select, insert, update, delete on all tables in schema catalogo to service_role;
grant select on catalogo.orari, catalogo.esauriti to authenticated, anon;
grant usage, select on all sequences in schema catalogo to service_role;
grant execute on all functions in schema catalogo to service_role, authenticated, anon;
grant select on menu.menu_products_disponibili to service_role, authenticated, anon;
grant execute on function public.bb_prodotti_disponibili(uuid, timestamptz) to service_role;
alter table catalogo.orari enable row level security;
alter table catalogo.esauriti enable row level security;
alter table catalogo.log enable row level security;
create policy orari_lettura on catalogo.orari for select using (true);
create policy esauriti_lettura on catalogo.esauriti for select using (true);
