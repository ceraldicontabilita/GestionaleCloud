create schema if not exists menu;

create table if not exists menu.menu_categories (
  id integer primary key, name text not null, name_it text not null,
  image text, origine text
);
create table if not exists menu.menu_subcategories (
  id integer primary key, category_id integer not null references menu.menu_categories(id),
  name text not null, name_it text not null, image text, origine text
);
create table if not exists menu.menu_products (
  id integer primary key,
  category_id integer not null references menu.menu_categories(id),
  subcategory_id integer not null references menu.menu_subcategories(id),
  name text not null, name_it text not null, price text not null,
  description text, description_it text, allergens text[] not null default '{}',
  image text, visible boolean not null default true, origine text, lotti_ref text
);
create table if not exists menu.menu_allergens (
  id text primary key, name text not null, name_it text not null,
  icon text, description_it text, description_en text
);
create table if not exists menu.menu_qrcode_config (
  id text primary key default 'qrcode_config', menu_url text, wifi jsonb,
  updated_at timestamptz default now(), updated_by text default 'admin'
);
create table if not exists menu.menu_orders (
  id text primary key, items jsonb not null default '[]', table_name text,
  customer_name text, note text, source text not null default 'cliente',
  status text not null default 'nuovo', paid boolean not null default false,
  payment_method text, total numeric not null default 0,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  sala_id text, sala_nome text, numero_coperti integer, totale_coperto numeric not null default 0
);
create table if not exists menu.menu_warehouse_items (
  id text primary key, name text not null, unit text not null default 'pz',
  quantity numeric not null default 0, min_threshold numeric, category text,
  note text, updated_at timestamptz not null default now()
);
create table if not exists menu.menu_warehouse_movements (
  id text primary key, item_id text not null, item_name text, type text not null,
  quantity numeric not null, resulting_quantity numeric, note text,
  created_at timestamptz not null default now()
);
create table if not exists menu.menu_sale (
  id text primary key, nome text not null, ordini_abilitati boolean not null default true,
  coperto_attivo boolean not null default false, coperto_importo numeric not null default 0,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  disabilita_contanti_qr boolean not null default false
);

grant usage on schema menu to anon, authenticated, service_role;
grant select, insert, update, delete on all tables in schema menu to anon, authenticated, service_role;
alter default privileges in schema menu grant select, insert, update, delete on tables to anon, authenticated, service_role;

do $$
declare t text;
begin
  foreach t in array array['menu_categories','menu_subcategories','menu_products','menu_allergens','menu_qrcode_config','menu_orders','menu_warehouse_items','menu_warehouse_movements','menu_sale'] loop
    execute format('alter table menu.%I enable row level security', t);
    execute format('drop policy if exists "menu app full access" on menu.%I', t);
    execute format('create policy "menu app full access" on menu.%I for all to anon using (true) with check (true)', t);
  end loop;
end $$;

create unique index if not exists menu_products_lotti_ref_uidx
  on menu.menu_products(lotti_ref) where lotti_ref is not null;

-- Gateway di compatibilita per il client Menu esistente. I dati restano nello
-- schema menu; le viste semplici sono aggiornabili e security_invoker conserva
-- i controlli RLS delle tabelle sottostanti senza esporre un nuovo schema API.
create or replace view public.menu_categories with (security_invoker = true) as select * from menu.menu_categories;
create or replace view public.menu_subcategories with (security_invoker = true) as select * from menu.menu_subcategories;
create or replace view public.menu_products with (security_invoker = true) as select * from menu.menu_products;
create or replace view public.menu_allergens with (security_invoker = true) as select * from menu.menu_allergens;
create or replace view public.menu_qrcode_config with (security_invoker = true) as select * from menu.menu_qrcode_config;
create or replace view public.menu_orders with (security_invoker = true) as select * from menu.menu_orders;
create or replace view public.menu_warehouse_items with (security_invoker = true) as select * from menu.menu_warehouse_items;
create or replace view public.menu_warehouse_movements with (security_invoker = true) as select * from menu.menu_warehouse_movements;
create or replace view public.menu_sale with (security_invoker = true) as select * from menu.menu_sale;

grant select, insert, update, delete on
  public.menu_categories, public.menu_subcategories, public.menu_products,
  public.menu_allergens, public.menu_qrcode_config, public.menu_orders,
  public.menu_warehouse_items, public.menu_warehouse_movements, public.menu_sale
to anon, authenticated, service_role;
