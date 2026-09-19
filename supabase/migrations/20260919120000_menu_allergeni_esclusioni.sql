-- Esclusioni dalla verifica allergeni del Menu.
--
-- Perche' una tabella separata e non una colonna su menu.menu_products: la
-- sincronizzazione Qromo (app/menu/qromo_sync.py::_sostituisci_tabelle)
-- cancella e reinserisce per intero le righe con ``origine IS NULL``, e le
-- righe reinserite portano solo le colonne prodotte da ``trasforma_catalogo``
-- (id/category_id/subcategory_id/name/name_it/price/description/
-- description_it/allergens/image). Qualunque flag scritto dentro
-- menu_products verrebbe perso alla prima sincronizzazione: e' gia' quello
-- che succede agli allergeni messi a mano su un prodotto Qromo.
-- Gli id di Qromo (menu_item_id, menu_id, menu_category_id) sono invece
-- stabili tra una sync e l'altra, quindi un'esclusione chiavata su
-- quell'id, in una tabella che la sync non tocca, sopravvive.
--
-- Semantica: "questo prodotto / questa categoria NON richiede la
-- dichiarazione allergeni" (distillati, bibite in bottiglia...). Non e'
-- "nascondilo dal menu": e' un'informazione di conformita' (Reg. UE
-- 1169/2011, D.Lgs. 231/2017), quindi si conserva, si vede e si puo'
-- revocare.

create table if not exists menu.menu_allergeni_esclusioni (
  tipo text not null check (tipo in ('prodotto', 'categoria', 'sottocategoria')),
  riferimento_id integer not null,
  motivo text,
  creato_il timestamptz not null default now(),
  creato_da text not null default 'admin',
  primary key (tipo, riferimento_id)
);

grant select, insert, update, delete on menu.menu_allergeni_esclusioni
  to anon, authenticated, service_role;

alter table menu.menu_allergeni_esclusioni enable row level security;
drop policy if exists "menu app full access" on menu.menu_allergeni_esclusioni;
create policy "menu app full access" on menu.menu_allergeni_esclusioni
  for all to anon using (true) with check (true);

-- Stesso gateway delle altre tabelle menu.* (20260914024000_unify_menu_schema.sql):
-- senza la vista in public + security_invoker PostgREST non vede la tabella.
create or replace view public.menu_allergeni_esclusioni with (security_invoker = true) as
  select * from menu.menu_allergeni_esclusioni;

grant select, insert, update, delete on public.menu_allergeni_esclusioni
  to anon, authenticated, service_role;
