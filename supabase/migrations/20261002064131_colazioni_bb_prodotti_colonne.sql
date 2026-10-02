-- Colazioni B&B: colonne di bb_prodotti che v11/v12 (20260929164914) aggiornano ma che nessuna
-- migrazione del registro creava (in produzione esistevano gia'). Idempotente.
alter table public.bb_prodotti
  add column if not exists descrizione_lunga text not null default '',
  add column if not exists materiali text not null default '';
