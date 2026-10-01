-- Il registro: entrate, uscite, giroconti, e il legame fra una fattura e il
-- movimento che ne prova il pagamento.

create table movimenti (
  id             uuid primary key default gen_random_uuid(),
  app_id         text,                       -- id nell'app «Gestore Attività», per la migrazione
  tipo           char(1) not null check (tipo in ('E','U')),
  data           date not null,
  conto_id       uuid not null references conti(id),
  categoria      text not null,
  descrizione    text,
  importo        numeric(14,2) not null,
  imponibile     numeric(14,2),
  imposta        numeric(14,2),
  aliquota_iva   text references aliquote_iva(nome),
  detrazione     text references aliquote_detrazione(nome),
  natura         text,                       -- N1..N7 per le operazioni senza IVA
  pagata         boolean not null default false,
  data_pagamento date,
  scadenza       date,
  fornitore_id   uuid references fornitori(id) on delete set null,
  controparte    text,
  numero_doc     text,
  tipo_documento text,                       -- TD01, TD04 nota di credito, ...
  id_sdi         text,
  centro_costo_id uuid references centri_costo(id) on delete set null,
  mezzo_pagamento text,                      -- come risulta all'app
  mezzo_canonico  text,                      -- come è stato pagato davvero: contanti, banca, assegno, sumup, paypal, carta
  mp_dichiarato   text,                      -- MP01..MP23 dichiarato dal fornitore nell'XML
  numero_assegno  text,
  carta_ultime4   text,
  origine        text,                       -- fattura | banca | corrispettivi | carta | manuale
  ext_id         text unique,                -- impronta anti-duplicato: FT|piva|numero|data|indice · BNK|data|importo|hash
  provenienza    text,                       -- nome del file da cui è entrato
  fonte_stato_pagamento text,
  note           text,
  creato_il      timestamptz not null default now()
);
comment on table movimenti is 'Una fattura si spezza in una riga per aliquota IVA: l''imposta resta esatta anche con più aliquote sullo stesso documento.';
comment on column movimenti.ext_id is 'Impronta del documento di origine. Ricaricare lo stesso file non crea doppioni.';
comment on column movimenti.mezzo_canonico is 'Il mezzo reale, diverso da quello dichiarato dal fornitore. Non sovrascrivere mp_dichiarato con questo.';
create index movimenti_data_idx on movimenti (data desc);
create index movimenti_conto_idx on movimenti (conto_id, data desc);
create index movimenti_fornitore_idx on movimenti (fornitore_id);
create index movimenti_doc_idx on movimenti (numero_doc) where numero_doc is not null;
create index movimenti_aperte_idx on movimenti (data desc) where pagata = false;

create table giroconti (
  id           uuid primary key default gen_random_uuid(),
  app_id       text,
  data         date not null,
  da_conto_id  uuid not null references conti(id),
  verso_conto_id uuid not null references conti(id),
  importo      numeric(14,2) not null check (importo > 0),
  descrizione  text,
  pos_stato    text check (pos_stato in ('registrato','incassato')),
  ext_id       text unique,
  creato_il    timestamptz not null default now(),
  check (da_conto_id <> verso_conto_id)
);
comment on column giroconti.pos_stato is 'registrato = transato del giorno; incassato = accredito arrivato. La differenza è il POS che aspetta.';
create index giroconti_data_idx on giroconti (data desc);

-- Un pagamento può saldare più fatture, e una fattura può essere pagata da più
-- movimenti: il legame è molti-a-molti, mai un campo singolo.
create table abbinamenti (
  id            uuid primary key default gen_random_uuid(),
  documento_id  uuid not null references movimenti(id) on delete cascade,
  pagamento_id  uuid not null references movimenti(id) on delete cascade,
  prova         text not null,   -- numero assegno | mandato SDD | numero fattura in causale | dichiarato dal foglio
  importo       numeric(14,2),
  creato_il     timestamptz not null default now(),
  unique (documento_id, pagamento_id),
  check (documento_id <> pagamento_id)
);
comment on table abbinamenti is 'Quando i candidati sono più d''uno il programma non sceglie: non si scrive niente qui e si aspetta una persona.';

-- Le righe di dettaglio della fattura: da qui nascono magazzino e centro di costo.
create table righe_documento (
  id             uuid primary key default gen_random_uuid(),
  movimento_id   uuid not null references movimenti(id) on delete cascade,
  linea          int,
  codice         text,
  codice_tipo    text,
  descrizione    text,
  quantita       numeric(14,4),
  unita_misura   text,
  prezzo_unitario numeric(14,5),
  prezzo_totale  numeric(14,2),
  aliquota       numeric(5,2),
  natura         text,
  lotto          text,
  scadenza       date
);
create index righe_documento_mov_idx on righe_documento (movimento_id);

