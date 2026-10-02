-- Unico catalogo Menu: Lotti replica qui la destinazione B&B della ricetta.
-- Default compatibile con l'eligibilita precedente; nessun backfill di prodotti.
alter table menu.menu_products
  add column if not exists menu_bb boolean not null default true;

comment on column menu.menu_products.menu_bb is
  'Visibilita nel catalogo B&B; per origine=lotti viene aggiornata dal ponte ricette.';

-- Stesso gateway, ordine delle colonne esistenti e permessi invariati.
create or replace view public.menu_products with (security_invoker = true) as
select id, category_id, subcategory_id, name, name_it, price,
       description, description_it, allergens, image, visible, origine,
       lotti_ref, menu_bb
from menu.menu_products;

notify pgrst, 'reload schema';
