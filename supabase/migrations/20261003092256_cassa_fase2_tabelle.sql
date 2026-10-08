-- Struttura recuperata dal registro Supabase (20261003092256) il 08/10/2026.
-- Escluse copie di prodotti, instradamenti/stampanti legacy e orari applicativi.
-- Conservate soltanto configurazioni strutturali; nessun dato operativo storico.
create extension if not exists pgcrypto with schema extensions;
create table cassa.config (k text primary key, v text, nota text);
create table cassa.operatori (
  id uuid primary key default gen_random_uuid(),
  nome text not null,
  pin_hash text not null,
  ruolo text not null check (ruolo in ('cameriere','cassiere','responsabile','admin')),
  operatore_rt integer not null default 1 check (operatore_rt between 1 and 12),
  attivo boolean not null default true,
  creato_il timestamptz not null default now()
);
create table cassa.sessioni (
  token uuid primary key default gen_random_uuid(),
  operatore_id uuid not null references cassa.operatori(id),
  creata_il timestamptz not null default now(),
  scade_il timestamptz not null default now() + interval '12 hours'
);
create table cassa.stampanti (
  id text primary key,
  nome text not null,
  tipo text not null check (tipo in ('fiscale','non_fiscale')),
  ip text,
  devid text,
  modello text,
  attiva boolean not null default true
);
create table cassa.sale (
  id text primary key,
  nome text not null,
  ordine integer not null default 0,
  stampante_preconto text references cassa.stampanti(id)
);
create table cassa.tavoli (
  id text primary key,
  sala_id text not null references cassa.sale(id),
  nome text not null,
  ordine integer not null default 0
);
create table cassa.instradamento (
  subcategory_id integer primary key,
  stampante_id text not null references cassa.stampanti(id)
);
create table cassa.conti (
  id uuid primary key default gen_random_uuid(),
  giornata date not null,
  tipo text not null check (tipo in ('banco','tavolo')),
  tavolo_id text references cassa.tavoli(id),
  listino_id text not null references cassa.listini(id),
  stato text not null default 'aperto' check (stato in ('aperto','chiuso','annullato')),
  numero_ordine integer,
  coperti integer,
  nota text,
  aperto_da uuid references cassa.operatori(id),
  aperto_il timestamptz not null default now(),
  chiuso_il timestamptz
);
create unique index conti_tavolo_aperto on cassa.conti(tavolo_id) where stato = 'aperto' and tavolo_id is not null;
create table cassa.scontrini (
  id uuid primary key default gen_random_uuid(),
  conto_id uuid references cassa.conti(id),
  giornata date not null,
  tipo text not null check (tipo in ('vendita','annullo','senza_documento')),
  causale text,
  totale_cent integer not null,
  stato text not null default 'in_coda' check (stato in ('in_coda','emesso','errore','registrato','annullato')),
  numero_rt integer,
  z_numero integer,
  data_rt text,
  riferimento_id uuid references cassa.scontrini(id),
  operatore_id uuid references cassa.operatori(id),
  errore text,
  creato_il timestamptz not null default now(),
  emesso_il timestamptz
);
create table cassa.righe (
  id uuid primary key default gen_random_uuid(),
  conto_id uuid not null references cassa.conti(id),
  product_id integer references menu.menu_products(id),
  descrizione text not null,
  quantita numeric(10,3) not null check (quantita > 0),
  prezzo_cent integer not null check (prezzo_cent >= 0),
  reparto_id text not null references cassa.reparti(id),
  iva numeric(5,2) not null,
  sconto_cent integer not null default 0 check (sconto_cent >= 0),
  motivo_sconto text,
  nota text,
  stato text not null default 'attiva' check (stato in ('attiva','tolta')),
  inviata boolean not null default false,
  scontrino_id uuid references cassa.scontrini(id),
  creata_da uuid references cassa.operatori(id),
  creata_il timestamptz not null default now(),
  tolta_da uuid references cassa.operatori(id),
  tolta_il timestamptz,
  motivo_tolta text
);
create index righe_conto on cassa.righe(conto_id);
create table cassa.pagamenti (
  id uuid primary key default gen_random_uuid(),
  scontrino_id uuid not null references cassa.scontrini(id),
  metodo text not null check (metodo in ('contanti','carta')),
  importo_cent integer not null check (importo_cent > 0),
  resto_cent integer not null default 0,
  riferimento text,
  creato_il timestamptz not null default now()
);
create table cassa.coda (
  id bigserial primary key,
  tipo text not null check (tipo in ('fiscale','annullo','comanda','preconto','chiusura','configura')),
  stampante_id text references cassa.stampanti(id),
  rif_id uuid,
  payload jsonb not null,
  stato text not null default 'in_attesa' check (stato in ('in_attesa','presa','fatta','errore')),
  tentativi integer not null default 0,
  esito jsonb,
  creato_il timestamptz not null default now(),
  preso_il timestamptz,
  chiuso_il timestamptz
);
create index coda_attesa on cassa.coda(stato, id);
create table cassa.chiusure (
  id uuid primary key default gen_random_uuid(),
  giornata date not null,
  stato text not null default 'in_coda' check (stato in ('in_coda','fatta','errore')),
  z_numero integer,
  totale_rt_cent integer,
  totale_cassa_cent integer not null,
  contanti_teorici_cent integer not null,
  elettronico_cent integer not null,
  contanti_contati_cent integer,
  differenza_cent integer,
  totali jsonb not null,
  operatore_id uuid references cassa.operatori(id),
  errore text,
  creata_il timestamptz not null default now()
);
create table cassa.movimenti (
  id bigserial primary key,
  product_id integer references menu.menu_products(id),
  quantita numeric(10,3) not null,
  causale text not null,
  scontrino_id uuid references cassa.scontrini(id),
  creato_il timestamptz not null default now()
);
do $$ declare t text; begin
  for t in select table_name from information_schema.tables where table_schema='cassa' and table_type='BASE TABLE' loop
    execute format('alter table cassa.%I enable row level security', t);
  end loop;
end $$;
insert into cassa.config (k, v, nota) values
 ('ora_cambio_giornata','4','Le vendite prima di questa ora contano sul giorno precedente'),
 ('rt_matricola',null,'Matricola fiscale (11 caratteri) dell Epson FP-90III RT: serve per gli annulli'),
 ('ponte_token', encode(extensions.gen_random_bytes(24),'hex'),'Chiave del ponte locale'),
 ('stampante_comande_default','comande','Stampante comande se la sottocategoria non e instradata'),
 ('stampante_preconto_banco','preconto_cassa','Preconto per i conti al banco'),
 ('soglia_sconto_cassiere_cent','200','Sconto massimo che un cassiere puo fare senza responsabile'),
 ('ultimo_numero_ordine','0',null),
 ('giornata_numero_ordine',null,null);
