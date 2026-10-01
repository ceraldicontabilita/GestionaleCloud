create table if not exists bb_prod_cat (
  id int primary key, nome text not null, ordine int not null default 0, attivo boolean not null default true, ospiti boolean not null default true);
create table if not exists bb_prod_sub (
  id int primary key, cat_id int not null references bb_prod_cat(id) on delete cascade, nome text not null, ordine int not null default 0, attivo boolean not null default true);
create table if not exists bb_prodotti (
  id int primary key, cat_id int not null references bb_prod_cat(id) on delete cascade, sub_id int references bb_prod_sub(id) on delete set null,
  nome text not null, descrizione text not null default '', prezzo numeric(8,2) not null default 0, visibile boolean not null default true,
  allergeni text[] not null default '{}', tags text[] not null default '{}', varianti jsonb, immagine text, ordine int not null default 0);
create index if not exists bb_prodotti_cat on bb_prodotti(cat_id, sub_id);
alter table bb_prod_cat enable row level security;
alter table bb_prod_sub enable row level security;
alter table bb_prodotti enable row level security;
revoke all on bb_prod_cat, bb_prod_sub, bb_prodotti from anon, authenticated;

