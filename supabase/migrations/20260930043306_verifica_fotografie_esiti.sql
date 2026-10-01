create table if not exists verifica.fotografie (
  scattata_il timestamptz not null default now(),
  tipo text not null,
  documento_id text not null,
  esito text not null,
  motivi text[] not null default '{}',
  importo numeric,
  primary key (scattata_il, tipo, documento_id)
);
comment on table verifica.fotografie is 'Esiti di verifica salvati a una certa data, per confrontare documento per documento tra un controllo e il successivo. Solo inserimenti.';
revoke all on verifica.fotografie from anon, authenticated;

insert into verifica.fotografie (scattata_il, tipo, documento_id, esito, motivi, importo)
select now(), 'cedolini', id, esito, motivi, netto from verifica.cedolini
union all
select now(), 'quietanze_f24', id, esito, motivi, saldo from verifica.quietanze_f24;

