-- ID prodotto unico (PRD-000123): lo stesso codice in Menu, B&B e Lotti.
-- Registro che non si cancella mai: la sync Qromo cancella e reinserisce i prodotti
-- (stesso id Qromo) e Lotti ricrea la riga Menu di una ricetta; il codice resta.
create table if not exists menu.prodotti_codici (
  seq             bigint generated always as identity primary key,
  menu_product_id integer unique,
  lotti_ref       text unique,
  creato_il       timestamptz not null default now()
);
alter table menu.prodotti_codici enable row level security;  -- nessuna policy: lo usa solo il trigger
revoke all on menu.prodotti_codici from anon, authenticated;

alter table menu.menu_products add column if not exists codice_prodotto text;

create or replace function menu.codice_da_seq(p_seq bigint) returns text
language sql immutable as $$ select 'PRD-' || lpad(p_seq::text, 6, '0') $$;

create or replace function menu.assegna_codice_prodotto() returns trigger
language plpgsql security definer set search_path = menu, pg_temp as $$
declare v_seq bigint;
begin
  if new.lotti_ref is not null then
    -- una ricetta tiene il suo codice anche se la riga Menu viene ricreata (mai per id: un id si puo' riusare)
    select seq into v_seq from menu.prodotti_codici where lotti_ref = new.lotti_ref;
    if v_seq is null then
      update menu.prodotti_codici set menu_product_id = null where menu_product_id = new.id;
      insert into menu.prodotti_codici (menu_product_id, lotti_ref) values (new.id, new.lotti_ref) returning seq into v_seq;
    else
      update menu.prodotti_codici set menu_product_id = null where menu_product_id = new.id and seq <> v_seq;
      update menu.prodotti_codici set menu_product_id = new.id where seq = v_seq;
    end if;
  else
    -- prodotto Qromo: l'id Qromo e' stabile fra una sync e l'altra
    select seq into v_seq from menu.prodotti_codici where menu_product_id = new.id and lotti_ref is null;
    if v_seq is null then
      insert into menu.prodotti_codici (menu_product_id) values (new.id)
        on conflict (menu_product_id) do update set menu_product_id = excluded.menu_product_id
        returning seq into v_seq;
    end if;
  end if;
  new.codice_prodotto := menu.codice_da_seq(v_seq);
  return new;
end $$;

drop trigger if exists trg_codice_prodotto on menu.menu_products;
create trigger trg_codice_prodotto before insert on menu.menu_products
  for each row execute function menu.assegna_codice_prodotto();

-- arretrato: Lotti prima (ordine per id), poi Qromo; un solo passaggio, idempotente
insert into menu.prodotti_codici (menu_product_id, lotti_ref)
  select id, lotti_ref from menu.menu_products
  where codice_prodotto is null order by (origine is null), id
  on conflict do nothing;
update menu.menu_products p set codice_prodotto = menu.codice_da_seq(c.seq)
  from menu.prodotti_codici c
  where p.codice_prodotto is null
    and ((p.lotti_ref is not null and c.lotti_ref = p.lotti_ref) or (p.lotti_ref is null and c.menu_product_id = p.id and c.lotti_ref is null));

create unique index if not exists menu_products_codice_uidx on menu.menu_products(codice_prodotto) where codice_prodotto is not null;

-- il codice non si cambia dall'esterno (anche via PostgREST)
create or replace function menu.blocca_cambio_codice_prodotto() returns trigger
language plpgsql as $$ begin new.codice_prodotto := old.codice_prodotto; return new; end $$;
drop trigger if exists trg_codice_prodotto_fisso on menu.menu_products;
create trigger trg_codice_prodotto_fisso before update on menu.menu_products
  for each row execute function menu.blocca_cambio_codice_prodotto();

-- Scheda vendita del prodotto (la scrive il ponte Lotti dalla ricetta; i prodotti Qromo tengono i valori di partenza):
-- canali sala/delivery, disponibilita' (esaurito si decide in Lotti), aggiunte con prezzo e rimozioni di ingredienti.
alter table menu.menu_products
  add column if not exists vendita_sala     boolean not null default true,
  add column if not exists vendita_delivery boolean not null default true,
  add column if not exists disponibile      boolean not null default true,
  add column if not exists aggiunte         jsonb   not null default '[]'::jsonb,
  add column if not exists rimozioni        jsonb   not null default '[]'::jsonb;

-- il gateway pubblico e' una vista `select *` espansa alla creazione: va rifatta per vedere la colonna nuova
create or replace view public.menu_products with (security_invoker = true) as select * from menu.menu_products;
