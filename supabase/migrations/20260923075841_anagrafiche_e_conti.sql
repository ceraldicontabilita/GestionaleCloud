-- Impresa Semplice · anagrafiche di base
-- Modello ricavato dall'app «Gestore Attività», dati reali Ceraldi Group SRL 2026.

create table conti (
  id            uuid primary key default gen_random_uuid(),
  nome          text not null unique,
  tipo          text not null check (tipo in ('cassa','banca','pos','transito','finanziario','carta','scontrino')),
  icona         text,
  saldo_iniziale numeric(14,2) not null default 0,
  nota          text,
  attivo        boolean not null default true,
  creato_il     timestamptz not null default now()
);
comment on table conti is 'Cassa, banche, POS, conti di transito, carte. Il POS e i corrispettivi sono conti di transito: ci passa il denaro prima di arrivare in banca.';
comment on column conti.tipo is 'pos e transito non sono liquidità: aspettano l''accredito.';

create table centri_costo (
  id          uuid primary key default gen_random_uuid(),
  nome        text not null unique,
  detrazione  numeric(5,4) not null default 1,
  chiavi      text,
  di_magazzino boolean not null default true
);
comment on column centri_costo.chiavi is 'Parole che riconoscono il centro di costo dalla descrizione della fattura.';
comment on column centri_costo.di_magazzino is 'false per energia, leasing, lavori, consulenze: restano fuori dagli articoli di magazzino.';

create table fornitori (
  id             uuid primary key default gen_random_uuid(),
  nome           text not null,
  piva           text,
  codice_fiscale text,
  metodo_pagamento text,
  conto_id       uuid references conti(id) on delete set null,
  centro_costo_id uuid references centri_costo(id) on delete set null,
  di_magazzino   boolean not null default true,
  note           text,
  creato_il      timestamptz not null default now()
);
create unique index fornitori_piva_uniq on fornitori (piva) where piva is not null and piva <> '';
create index fornitori_nome_idx on fornitori (lower(nome));

create table dipendenti (
  id             uuid primary key default gen_random_uuid(),
  nome           text not null,
  codice_fiscale text unique,
  matricola      text,
  data_assunzione date,
  data_cessazione date,
  note           text
);

create table aliquote_iva (
  nome text primary key,
  perc numeric(5,4) not null
);
insert into aliquote_iva (nome, perc) values
  ('IVA 0%',0),('IVA 4%',0.04),('IVA 5%',0.05),('IVA 10%',0.10),('IVA 22%',0.22);

create table aliquote_detrazione (
  nome text primary key,
  perc numeric(5,4) not null
);
insert into aliquote_detrazione (nome, perc) values
  ('AL 100%',1),('AL 50%',0.5),('AL 40%',0.4),('AL 0%',0);

