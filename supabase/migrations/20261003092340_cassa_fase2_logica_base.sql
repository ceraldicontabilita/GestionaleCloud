-- Struttura recuperata dal registro Supabase (20261003092340) il 08/10/2026.
-- Escluse copie di prodotti, instradamenti/stampanti legacy e orari applicativi.
-- Conservate soltanto configurazioni strutturali; nessun dato operativo storico.
create or replace function cassa.cfg(p_k text) returns text language sql stable set search_path = cassa, pg_temp as $$ select v from cassa.config where k = p_k $$;
create or replace function cassa.giornata() returns date language sql stable set search_path = cassa, pg_temp as $$
  select ((now() at time zone 'Europe/Rome') - make_interval(hours => coalesce(cassa.cfg('ora_cambio_giornata')::int, 4)))::date $$;
create or replace function cassa.livello(p_ruolo text) returns int language sql immutable as $$
  select case p_ruolo when 'cameriere' then 1 when 'cassiere' then 2 when 'responsabile' then 3 when 'admin' then 4 else 0 end $$;
create or replace function cassa.richiedi(p_ruolo text, p_minimo text) returns void language plpgsql immutable as $$
begin
  if cassa.livello(p_ruolo) < cassa.livello(p_minimo) then
    raise exception 'PERMESSO_NEGATO: serve il ruolo % o superiore', p_minimo;
  end if;
end $$;
create or replace function cassa.operatore(p_tok uuid) returns cassa.operatori language plpgsql set search_path = cassa, pg_temp as $$
declare o cassa.operatori;
begin
  select op.* into o from cassa.sessioni s join cassa.operatori op on op.id = s.operatore_id
   where s.token = p_tok and s.scade_il > now() and op.attivo;
  if not found then raise exception 'SESSIONE_SCADUTA: rientra con il PIN'; end if;
  update cassa.sessioni set scade_il = now() + interval '12 hours' where token = p_tok;
  return o;
end $$;
create or replace function cassa.prezzo(p_prod int, p_listino text) returns int language sql stable set search_path = cassa, pg_temp as $$
  select coalesce((select prezzo_cent from cassa.prezzi where product_id = p_prod and listino_id = p_listino),
                  (select prezzo_cent from cassa.prezzi where product_id = p_prod and listino_id = 'base')) $$;
create or replace function cassa.importo_riga(r cassa.righe) returns int language sql immutable as $$
  select (round(r.quantita * r.prezzo_cent))::int - r.sconto_cent $$;
create or replace function cassa.riga_da_pagare(r cassa.righe) returns boolean language sql stable set search_path = cassa, pg_temp as $$
  select r.stato = 'attiva' and (r.scontrino_id is null) $$;
create or replace function cassa.registra(p_op uuid, p_azione text, p_entita text, p_id text, p_prima jsonb, p_dopo jsonb) returns void language sql set search_path = cassa, pg_temp as $$
  insert into cassa.log (operatore, azione, entita, entita_id, prima, dopo)
  values ((select nome from cassa.operatori where id = p_op), p_azione, p_entita, p_id, p_prima, p_dopo) $$;
create or replace function cassa.accoda(p_tipo text, p_stampante text, p_rif uuid, p_payload jsonb) returns bigint language sql set search_path = cassa, pg_temp as $$
  insert into cassa.coda (tipo, stampante_id, rif_id, payload) values (p_tipo, p_stampante, p_rif, p_payload) returning id $$;
create or replace function cassa.numero_ordine() returns int language plpgsql set search_path = cassa, pg_temp as $$
declare g text := cassa.giornata()::text; n int;
begin
  if cassa.cfg('giornata_numero_ordine') is distinct from g then
    n := 1;
    update cassa.config set v = g where k = 'giornata_numero_ordine';
  else
    n := coalesce(cassa.cfg('ultimo_numero_ordine')::int, 0) % 99 + 1;
  end if;
  update cassa.config set v = n::text where k = 'ultimo_numero_ordine';
  return n;
end $$;
create or replace function cassa.conto_json(p_conto uuid) returns jsonb language sql stable set search_path = cassa, pg_temp as $$
  select jsonb_build_object(
    'id', c.id, 'tipo', c.tipo, 'tavolo', c.tavolo_id, 'listino', c.listino_id, 'stato', c.stato,
    'numero_ordine', c.numero_ordine, 'coperti', c.coperti, 'aperto_il', c.aperto_il,
    'righe', coalesce((select jsonb_agg(jsonb_build_object(
        'id', r.id, 'prodotto', r.product_id, 'descrizione', r.descrizione, 'quantita', r.quantita,
        'prezzo_cent', r.prezzo_cent, 'sconto_cent', r.sconto_cent, 'importo_cent', cassa.importo_riga(r),
        'nota', r.nota, 'stato', r.stato, 'inviata', r.inviata,
        'pagata', r.scontrino_id is not null, 'da_pagare', cassa.riga_da_pagare(r)) order by r.creata_il)
      from cassa.righe r where r.conto_id = c.id), '[]'::jsonb),
    'totale_cent', coalesce((select sum(cassa.importo_riga(r)) from cassa.righe r where r.conto_id = c.id and r.stato = 'attiva'), 0),
    'da_pagare_cent', coalesce((select sum(cassa.importo_riga(r)) from cassa.righe r where r.conto_id = c.id and cassa.riga_da_pagare(r)), 0),
    'da_inviare', (select count(*) from cassa.righe r where r.conto_id = c.id and r.stato = 'attiva' and not r.inviata))
  from cassa.conti c where c.id = p_conto $$;
create or replace function cassa.chiudi_se_finito(p_conto uuid) returns void language sql set search_path = cassa, pg_temp as $$
  update cassa.conti c set stato = 'chiuso', chiuso_il = now()
   where c.id = p_conto and c.stato = 'aperto'
     and exists (select 1 from cassa.righe r where r.conto_id = c.id and r.stato = 'attiva')
     and not exists (select 1 from cassa.righe r left join cassa.scontrini s on s.id = r.scontrino_id
                      where r.conto_id = c.id and r.stato = 'attiva'
                        and (r.scontrino_id is null or s.stato not in ('emesso','registrato'))) $$;
