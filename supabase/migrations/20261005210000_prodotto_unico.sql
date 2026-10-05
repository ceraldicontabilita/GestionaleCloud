-- Prodotto unico (titolare, 05/10/2026): Menu, B&B e Cassa leggono lo stesso prodotto, `menu.menu_products`.
-- Prima il B&B teneva una copia propria (`public.bb_prodotti`, 439 righe, 323 in comune con il Menu) e la Cassa
-- puntava a quella copia. Ora:
--   * il prezzo del Menu resta il prezzo AL TAVOLO (`price`), il prezzo AL BANCO e' una colonna nuova (`prezzo_banco`),
--     la stessa regola delle ricette (due prezzi);
--   * cio' che e' solo del B&B (visibilita' per gli hotel, ordine, etichette, varianti, testi lunghi) sta in
--     `menu.prodotti_bb`, una riga per prodotto;
--   * `public.bb_prodotti` diventa una VISTA con le stesse colonne di prima: le funzioni bb_* e cassa.* non cambiano;
--   * le quattro chiavi della Cassa (`cassa.righe|movimenti|prezzi|prodotti`) puntano al prodotto unico.
-- Gli ID non cambiano. I 116 prodotti che esistevano solo nel B&B entrano nel Menu (visibili, tranne «Comunicazioni», che
-- non e' un prodotto). Gli allergeni sono l'UNIONE dei due elenchi. La vecchia tabella resta come
-- `bb_prodotti_prima_unificazione` finche' il titolare non ha verificato (poi si toglie).
-- Richiede la migrazione 20261005150000_menu_codice_prodotto (codice PRD assegnato dal database).

-- 1) prezzo al banco e lettore dei prezzi in formato Menu («2.50€»)
alter table menu.menu_products add column if not exists prezzo_banco numeric(10,2);

create or replace function menu.prezzo_numero(p text) returns numeric
language sql immutable as $$
  select case when s ~ '^[0-9]+(\.[0-9]+)?$' then s::numeric end
  from (select replace(regexp_replace(coalesce(p, ''), '[^0-9.,]', '', 'g'), ',', '.') as s) q
$$;

-- 2) la parte del prodotto che vale solo per il B&B
create table if not exists menu.prodotti_bb (
  product_id        integer primary key references menu.menu_products(id) on delete cascade,
  visibile          boolean not null default true,   -- visibile agli hotel (non e' la visibilita' del Menu)
  ordine            integer not null default 0,
  tags              text[]  not null default '{}',
  varianti          jsonb,
  descrizione_lunga text    not null default '',
  materiali         text    not null default '',
  descrizione       text                              -- solo se il B&B ha un testo diverso da quello del Menu
);
alter table menu.prodotti_bb enable row level security;  -- nessuna policy: lo leggono solo la vista e le funzioni bb_*
revoke all on menu.prodotti_bb from anon, authenticated;

-- 3) categorie e sottocategorie del B&B che il Menu non aveva (stessi id, stessi nomi): una sola tassonomia
insert into menu.menu_categories (id, name, name_it, origine)
  select c.id, c.nome, c.nome, null from public.bb_prod_cat c
  where not exists (select 1 from menu.menu_categories m where m.id = c.id);
insert into menu.menu_subcategories (id, category_id, name, name_it, origine)
  select s.id, s.cat_id, s.nome, s.nome, null from public.bb_prod_sub s
  where not exists (select 1 from menu.menu_subcategories m where m.id = s.id);
-- e viceversa: la sottocategoria creata nel Menu per la colazione esterna deve esistere anche per il B&B
insert into public.bb_prod_sub (id, cat_id, nome, ordine, attivo)
  select s.id, s.category_id, s.name, 0, true from menu.menu_subcategories s
  where s.id = 102288 and not exists (select 1 from public.bb_prod_sub b where b.id = s.id);

-- 4) i prodotti che esistevano solo nel B&B entrano nel Menu (stesso id; il codice PRD lo assegna il database)
insert into menu.menu_products
  (id, category_id, subcategory_id, name, name_it, price, description, description_it, allergens, image, visible, origine, menu_bb)
select b.id, b.cat_id, b.sub_id, b.nome, b.nome,
       case when b.prezzo_tavolo > 0 then to_char(b.prezzo_tavolo, 'FM990.00') || '€' else '' end,
       nullif(b.descrizione, ''), nullif(b.descrizione, ''), b.allergeni, b.immagine,
       (b.cat_id <> 19643),      -- «Comunicazioni» e' un avviso per gli ospiti, non un prodotto del Menu
       null, true
from public.bb_prodotti b
where b.sub_id is not null
  and not exists (select 1 from menu.menu_products m where m.id = b.id);

-- 5) prezzo al banco, parte B&B e allergeni (unione dei due elenchi) per tutti i prodotti del B&B
update menu.menu_products m set prezzo_banco = b.prezzo
  from public.bb_prodotti b where b.id = m.id and m.prezzo_banco is distinct from b.prezzo;

update menu.menu_products m
   set allergens = (select coalesce(array_agg(distinct x order by x), '{}') from unnest(m.allergens || b.allergeni) x)
  from public.bb_prodotti b
 where b.id = m.id and not (m.allergens @> b.allergeni and b.allergeni @> m.allergens);

insert into menu.prodotti_bb (product_id, visibile, ordine, tags, varianti, descrizione_lunga, materiali, descrizione)
select b.id, b.visibile, b.ordine, b.tags, b.varianti, b.descrizione_lunga, b.materiali,
       case when coalesce(b.descrizione, '') <> coalesce(m.description_it, m.description, '') then b.descrizione end
from public.bb_prodotti b join menu.menu_products m on m.id = b.id
on conflict (product_id) do nothing;

-- 6) la copia diventa una vista: stesse colonne, stessi tipi, stessi permessi (nessuno per anon/authenticated)
alter table public.bb_prodotti rename to bb_prodotti_prima_unificazione;

drop function if exists public.bb_prodotti_disponibili(uuid, timestamptz);

alter table cassa.righe     drop constraint if exists righe_product_id_fkey;
alter table cassa.movimenti drop constraint if exists movimenti_product_id_fkey;
alter table cassa.prezzi    drop constraint if exists prezzi_product_id_fkey;
alter table cassa.prodotti  drop constraint if exists prodotti_product_id_fkey;
alter table cassa.righe     add constraint righe_product_id_fkey     foreign key (product_id) references menu.menu_products(id) on delete set null;
alter table cassa.movimenti add constraint movimenti_product_id_fkey foreign key (product_id) references menu.menu_products(id) on delete set null;
alter table cassa.prezzi    add constraint prezzi_product_id_fkey    foreign key (product_id) references menu.menu_products(id) on delete cascade;
alter table cassa.prodotti  add constraint prodotti_product_id_fkey  foreign key (product_id) references menu.menu_products(id) on delete cascade;

create view public.bb_prodotti as
select m.id,
       m.category_id                                                        as cat_id,
       m.subcategory_id                                                     as sub_id,
       m.name                                                               as nome,
       coalesce(x.descrizione, m.description_it, m.description, '')         as descrizione,
       coalesce(m.prezzo_banco, 0)                                          as prezzo,
       x.visibile                                                           as visibile,
       m.allergens                                                          as allergeni,
       x.tags                                                               as tags,
       x.varianti                                                           as varianti,
       m.image                                                              as immagine,
       x.ordine                                                             as ordine,
       x.descrizione_lunga                                                  as descrizione_lunga,
       x.materiali                                                          as materiali,
       menu.prezzo_numero(m.price)                                          as prezzo_tavolo
from menu.menu_products m
join menu.prodotti_bb x on x.product_id = m.id;

revoke all on public.bb_prodotti from public, anon, authenticated;
grant select on public.bb_prodotti to service_role;

create function public.bb_prodotti_disponibili(p_struttura uuid, p_at timestamptz default now())
returns setof public.bb_prodotti
language sql stable as $$
  select b.* from public.bb_prodotti b
  where b.visibile and catalogo.disponibile(b.id, b.cat_id, b.sub_id, 'bb', p_struttura, p_at)
$$;
grant execute on function public.bb_prodotti_disponibili(uuid, timestamptz) to anon, authenticated, service_role;

-- 7) il gateway pubblico del Menu e' una vista `select *` espansa alla creazione: va rifatta per vedere la colonna nuova
create or replace view public.menu_products with (security_invoker = true) as select * from menu.menu_products;
