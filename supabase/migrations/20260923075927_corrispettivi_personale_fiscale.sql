-- Corrispettivi, personale, fiscale, e il registro di che cosa è entrato.

create table corrispettivi (
  id           uuid primary key default gen_random_uuid(),
  data         date not null,
  matricola_rt text,
  imponibile   numeric(14,2),
  imposta      numeric(14,2),
  totale       numeric(14,2) not null,
  contanti     numeric(14,2),
  pos          numeric(14,2),
  pos_numia    numeric(14,2),
  pos_sumup    numeric(14,2),
  documenti    int,
  movimento_id uuid references movimenti(id) on delete set null,
  ext_id       text unique,       -- COR|matricola|giorno|riepilogo
  note         text,
  creato_il    timestamptz not null default now()
);
comment on table corrispettivi is 'Una chiusura rilevata prima delle 06:00 è la serata del giorno prima. Un giorno a zero è un giorno senza incassi, non un file perduto.';
create unique index corrispettivi_giorno_idx on corrispettivi (data, matricola_rt, coalesce(ext_id,''));

create table chiusure (
  id         uuid primary key default gen_random_uuid(),
  dal        date,
  al         date,
  ricorrente text,          -- '01-01' per Capodanno, '12-25' per Natale
  pasqua     boolean not null default false,
  nota       text not null
);
comment on table chiusure is 'Giorni senza attività dichiarata, e giorni in cui la chiusura di cassa non è stata fatta e l''incasso è finito nel giorno dopo: non sono buchi.';

create table cedolini (
  id            uuid primary key default gen_random_uuid(),
  dipendente_id uuid references dipendenti(id) on delete set null,
  dipendente    text,
  periodo       text not null,       -- 2026-08
  lordo         numeric(14,2),
  netto         numeric(14,2),
  contributi    numeric(14,2),
  movimento_id  uuid references movimenti(id) on delete set null,
  ext_id        text unique,
  note          text
);
create index cedolini_periodo_idx on cedolini (periodo);

create table f24 (
  id            uuid primary key default gen_random_uuid(),
  data          date not null,
  protocollo    text,
  totale        numeric(14,2),
  quietanza     boolean not null default false,
  data_quietanza date,
  movimento_id  uuid references movimenti(id) on delete set null,
  ext_id        text unique,
  file          text,
  note          text
);
comment on table f24 is 'Un F24 non è una prova di pagamento. La prova ha quattro gradini: dovuto, predisposto, trasmesso con quietanza, addebitato in estratto conto.';

create table f24_righe (
  id             uuid primary key default gen_random_uuid(),
  f24_id         uuid not null references f24(id) on delete cascade,
  sezione        text,
  codice_tributo text not null,
  anno_riferimento int,
  periodo_riferimento text,
  importo_debito numeric(14,2),
  importo_credito numeric(14,2)
);
create index f24_righe_tributo_idx on f24_righe (codice_tributo, anno_riferimento);

create table obbligazioni (
  id              uuid primary key default gen_random_uuid(),
  anno_imposta    int not null,
  tributo         text not null,
  sezione         text,
  descrizione     text,
  dovuto          numeric(14,2),
  versato         numeric(14,2),
  stato           text,          -- dovuto | predisposto | trasmesso | addebitato
  madre_id        uuid references obbligazioni(id) on delete cascade,
  note            text
);
comment on column obbligazioni.madre_id is 'Interessi e sanzioni da ravvedimento non sono obbligazioni autonome: si attaccano alla madre.';
comment on table obbligazioni is 'Nelle aggregazioni fiscali l''anno di riferimento vince sulla data di pagamento.';

create table dichiarazioni (
  id            uuid primary key default gen_random_uuid(),
  anno          int not null,
  modello       text not null,
  protocollo    text,
  data_presentazione date,
  righi         jsonb,
  file          text,
  note          text
);

create table codici_tributo (
  codice      text primary key,
  descrizione text,
  sezione     text,
  natura      text,
  fonte       text
);

create table importazioni (
  id         uuid primary key default gen_random_uuid(),
  quando     timestamptz not null default now(),
  tipo       text not null,        -- fattura | corrispettivi | banca | carta | cedolini | posta
  file       text,
  righe_lette int,
  righe_nuove int,
  doppioni   int,
  dal        date,
  al         date,
  esito      text,
  note       text
);
comment on table importazioni is 'Che cosa è entrato, quando, fino a che data e da dove. È il contratto fra l''app e i produttori di dati.';

create table posta (
  thread_id  text primary key,
  data       date,
  mittente   text,
  oggetto    text,
  cartella   text,
  stato      text,
  aggiornato timestamptz not null default now()
);
create index posta_data_idx on posta (data desc);
create index posta_cartella_idx on posta (cartella);

