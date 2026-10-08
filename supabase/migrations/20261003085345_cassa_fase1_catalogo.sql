-- Struttura recuperata dal registro Supabase (20261003085345) il 08/10/2026.
-- Escluse copie di prodotti, instradamenti/stampanti legacy e orari applicativi.
-- Conservate soltanto configurazioni strutturali; nessun dato operativo storico.
create schema if not exists cassa;
create table cassa.iva (
  id text primary key,
  descrizione text not null,
  aliquota numeric(5,2) not null check (aliquota >= 0),
  natura text,
  ventilazione boolean not null default false,
  codice_ateco text,
  attiva boolean not null default true,
  creato_il timestamptz not null default now()
);
create table cassa.reparti (
  id text primary key,
  nome text not null,
  testo_scontrino text not null,
  numero_rt integer,
  numero_rt_verificato boolean not null default false,
  iva_id text not null references cassa.iva(id),
  tipo_vendita text not null default 'beni' check (tipo_vendita in ('beni','servizi')),
  importo_massimo_cent integer,
  attivo boolean not null default true,
  creato_il timestamptz not null default now()
);
create table cassa.listini (
  id text primary key,
  nome text not null,
  reparto_sostitutivo_id text references cassa.reparti(id),
  ordine integer not null default 0,
  attivo boolean not null default true
);
create table cassa.prodotti (
  product_id integer primary key references menu.menu_products(id) on delete cascade,
  reparto_id text not null references cassa.reparti(id),
  nome_pulsante text,
  nome_scontrino text,
  preferito boolean not null default false,
  vendibile_in_cassa boolean not null default true,
  da_verificare text,
  aggiornato_il timestamptz not null default now()
);
create table cassa.prezzi (
  product_id integer not null references menu.menu_products(id) on delete cascade,
  listino_id text not null references cassa.listini(id),
  prezzo_cent integer not null check (prezzo_cent >= 0),
  origine text not null default 'manuale',
  aggiornato_il timestamptz not null default now(),
  primary key (product_id, listino_id)
);
create table cassa.log (
  id bigserial primary key,
  quando timestamptz not null default now(),
  operatore text,
  azione text not null,
  entita text,
  entita_id text,
  prima jsonb,
  dopo jsonb,
  dispositivo text
);
alter table cassa.iva enable row level security;
alter table cassa.reparti enable row level security;
alter table cassa.listini enable row level security;
alter table cassa.prodotti enable row level security;
alter table cassa.prezzi enable row level security;
alter table cassa.log enable row level security;
comment on schema cassa is 'Cassa Ceraldi - fase 1 catalogo (specifica del 3 ottobre 2026). Tabelle aggiuntive: non modificano menu.*';
comment on column cassa.reparti.numero_rt_verificato is 'false finche il numero reparto non e confrontato con la programmazione dell Epson FP-90III RT';
