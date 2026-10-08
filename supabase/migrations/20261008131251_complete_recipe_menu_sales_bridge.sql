-- Completa esclusivamente la scheda vendita usata dal ponte canonico.
-- Nessun archivio parallelo, prezzo inventato o modifica delle policy RLS.
alter table menu.menu_products
  add column if not exists prezzo_banco numeric(10,2),
  add column if not exists vendita_sala boolean not null default true,
  add column if not exists vendita_delivery boolean not null default true,
  add column if not exists disponibile boolean not null default true,
  add column if not exists aggiunte jsonb not null default '[]'::jsonb,
  add column if not exists rimozioni jsonb not null default '[]'::jsonb;

create or replace view public.menu_products with (security_invoker = true)
as select * from menu.menu_products;
notify pgrst, 'reload schema';
