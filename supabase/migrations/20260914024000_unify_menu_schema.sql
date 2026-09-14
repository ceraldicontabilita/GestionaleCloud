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
