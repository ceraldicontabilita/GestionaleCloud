-- Le colonne sono gia' presenti come seconda colonna di indici compositi, ma
-- PostgreSQL non puo' usarli efficientemente cercando soltanto la FK.
create index if not exists prezzi_listino_id_fk_idx
  on cassa.prezzi (listino_id);

create index if not exists bb_prodotti_sub_id_fk_idx
  on public.bb_prodotti (sub_id);
