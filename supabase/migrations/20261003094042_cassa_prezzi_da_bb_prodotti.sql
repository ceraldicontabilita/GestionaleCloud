-- Struttura recuperata dal registro Supabase (20261003094042) il 08/10/2026.
-- Escluse copie di prodotti, instradamenti/stampanti legacy e orari applicativi.
-- Conservate soltanto configurazioni strutturali; nessun dato operativo storico.
create or replace function cassa.prezzo(p_prod int, p_listino text) returns int language sql stable set search_path = cassa, pg_temp as $$
  select coalesce(
    (select prezzo_cent from cassa.prezzi where product_id = p_prod and listino_id = p_listino and origine = 'manuale'),
    (select round(v * 100)::int from (select case p_listino when 'tavolo' then b.prezzo_tavolo when 'banco' then b.prezzo end v
                                       from public.bb_prodotti b where b.id = p_prod) x where v > 0),
    (select prezzo_cent from cassa.prezzi where product_id = p_prod and listino_id = p_listino),
    (select prezzo_cent from cassa.prezzi where product_id = p_prod and listino_id = 'base')) $$;
comment on function cassa.prezzo(int, text) is 'Ordine: prezzo manuale della cassa, poi bb_prodotti (prezzo = banco, prezzo_tavolo = tavolo), poi listino della cassa, poi base';
revoke all on all functions in schema cassa from public, anon, authenticated;
