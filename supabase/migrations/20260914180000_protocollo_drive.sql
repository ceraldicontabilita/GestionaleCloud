-- Protocollo-indice dei documenti su Google Drive.
--
-- Inventario VIVO di ogni file sotto la radice GESTIONALE: una riga per file
-- Drive, aggiornata da un giro periodico che RICONCILIA Drive con la tabella
-- (non accoda): file nuovo -> riga nuova; file cambiato -> riga aggiornata;
-- file sparito da Drive -> riga marcata 'rimosso' con la data, MAI cancellata.
-- E' un protocollo: deve ricordare che un documento e' esistito, con il suo
-- hash, anche dopo che qualcuno lo ha tolto da Drive.
--
-- L'hash MD5 arriva dall'API Drive (md5Checksum): i duplicati certi si
-- trovano senza scaricare nulla. Le impronte dei documenti gia' in archivio
-- (cedolini HR, allegati fattura) vengono calcolate una volta sola e messe in
-- protocollo_impronte, cosi' ogni file Drive puo' essere agganciato al
-- documento del gestionale che lo contiene.
--
-- Tabella relazionale (asyncpg), non gestionale.documents: 30.000 righe di
-- inventario non devono essere idratate in memoria a ogni avvio dell'app.
-- Lo schema gestionale non e' esposto ad anon/authenticated (nessuna policy
-- RLS necessaria: si legge solo dal backend).

create table if not exists gestionale.protocollo_drive (
  drive_id            text primary key,
  nome                text not null,
  mime                text,
  estensione          text,
  dimensione          bigint,
  md5                 text,
  parent_id           text,
  percorso            text not null,
  area                text,
  categoria           text,
  anno                integer,
  creato_drive        timestamptz,
  modificato_drive    timestamptz,
  link                text,
  stato               text not null default 'attivo'
                      check (stato in ('attivo', 'rimosso')),
  visto_il            timestamptz not null default now(),
  rimosso_il          timestamptz,
  duplicato_di        text,
  collegamento_tipo   text,
  collegamento_id     text,
  aggiornato_il       timestamptz not null default now()
);

create index if not exists protocollo_drive_md5_idx      on gestionale.protocollo_drive (md5);
create index if not exists protocollo_drive_parent_idx   on gestionale.protocollo_drive (parent_id);
create index if not exists protocollo_drive_stato_idx    on gestionale.protocollo_drive (stato);
create index if not exists protocollo_drive_area_idx     on gestionale.protocollo_drive (area, categoria);
create index if not exists protocollo_drive_anno_idx     on gestionale.protocollo_drive (anno);
create index if not exists protocollo_drive_colleg_idx   on gestionale.protocollo_drive (collegamento_tipo, collegamento_id);

comment on table gestionale.protocollo_drive is
  'Protocollo-indice vivo dei file su Google Drive (radice GESTIONALE). Le righe non si cancellano: un file sparito da Drive resta con stato=rimosso.';

-- Impronte (MD5) dei documenti gia' in archivio, calcolate una volta sola.
create table if not exists gestionale.protocollo_impronte (
  origine       text not null,      -- 'hr_cedolino' | 'hr_bonifico' | 'invoice'
  doc_id        text not null,
  md5           text,
  calcolato_il  timestamptz not null default now(),
  primary key (origine, doc_id)
);
create index if not exists protocollo_impronte_md5_idx on gestionale.protocollo_impronte (md5);

-- Registro dei giri di sincronizzazione.
create table if not exists gestionale.protocollo_drive_giri (
  id            bigserial primary key,
  avvio         timestamptz not null default now(),
  fine          timestamptz,
  esito         text,                -- 'ok' | 'errore' | 'in_corso'
  file_visti    integer,
  nuovi         integer,
  aggiornati    integer,
  rimossi       integer,
  duplicati     integer,
  collegati     integer,
  dettaglio     text
);

-- MD5 di un contenuto base64, senza far fallire la query su righe malformate.
create or replace function gestionale.md5_base64_sicuro(p_base64 text)
returns text
language plpgsql
immutable
set search_path to pg_catalog
as $$
begin
  if p_base64 is null or p_base64 = '' then
    return null;
  end if;
  return md5(decode(regexp_replace(p_base64, '^data:[^,]*,', ''), 'base64'));
exception when others then
  return null;
end;
$$;

-- Stessa guardia contro le cancellazioni di massa gia' attiva sull'archivio:
-- il protocollo non cancella mai righe, quindi un DELETE a mano e' sempre
-- un errore da fermare.
do $$
declare
  t text;
begin
  foreach t in array array['protocollo_drive', 'protocollo_impronte', 'protocollo_drive_giri'] loop
    execute format('drop trigger if exists trg_guardia_delete on gestionale.%I', t);
    execute format(
      'create trigger trg_guardia_delete after delete on gestionale.%I '
      'referencing old table as righe_cancellate '
      'for each statement execute function gestionale.blocca_delete_non_autorizzata()', t);
    execute format('drop trigger if exists trg_guardia_truncate on gestionale.%I', t);
    execute format(
      'create trigger trg_guardia_truncate before truncate on gestionale.%I '
      'for each statement execute function gestionale.blocca_truncate_non_autorizzato()', t);
  end loop;
end;
$$;
