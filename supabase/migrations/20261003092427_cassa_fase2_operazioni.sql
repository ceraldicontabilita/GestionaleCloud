-- Struttura recuperata dal registro Supabase (20261003092427) il 08/10/2026.
-- Escluse copie di prodotti, instradamenti/stampanti legacy e orari applicativi.
-- Conservate soltanto configurazioni strutturali; nessun dato operativo storico.
create or replace function cassa.op_login(a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare o cassa.operatori; t uuid;
begin
  select * into o from cassa.operatori where attivo and pin_hash = extensions.crypt(coalesce(a->>'pin',''), pin_hash) limit 1;
  if not found then
    perform pg_sleep(1);
    raise exception 'PIN_ERRATO: PIN non valido';
  end if;
  insert into cassa.sessioni (operatore_id) values (o.id) returning token into t;
  perform cassa.registra(o.id, 'login', 'operatore', o.id::text, null, null);
  return jsonb_build_object('token', t, 'nome', o.nome, 'ruolo', o.ruolo);
end $$;
create or replace function cassa.op_catalogo(o cassa.operatori, a jsonb) returns jsonb language sql stable set search_path = cassa, pg_temp as $$
  with l as (select coalesce(a->>'listino','banco') as listino),
  p as (
    select m.id, coalesce(cp.nome_pulsante, m.name) nome, m.subcategory_id, m.category_id, cp.preferito, cp.reparto_id,
           cassa.prezzo(m.id, (select listino from l)) prezzo
      from menu.menu_products m join cassa.prodotti cp on cp.product_id = m.id
     where cp.vendibile_in_cassa and m.visible)
  select jsonb_build_object(
    'listino', (select listino from l),
    'categorie', coalesce((select jsonb_agg(jsonb_build_object('id', s.id, 'nome', s.name) order by s.category_id, s.id)
        from menu.menu_subcategories s where exists (select 1 from p where p.subcategory_id = s.id and p.prezzo is not null)), '[]'::jsonb),
    'prodotti', coalesce((select jsonb_agg(jsonb_build_object('id', p.id, 'nome', p.nome, 'categoria', p.subcategory_id,
        'prezzo_cent', p.prezzo, 'preferito', p.preferito, 'reparto', p.reparto_id) order by p.nome)
        from p where p.prezzo is not null), '[]'::jsonb),
    'senza_prezzo', (select count(*) from p where p.prezzo is null)) $$;
create or replace function cassa.op_stato(o cassa.operatori, a jsonb) returns jsonb language sql stable set search_path = cassa, pg_temp as $$
  select jsonb_build_object(
    'operatore', jsonb_build_object('nome', o.nome, 'ruolo', o.ruolo),
    'giornata', cassa.giornata(),
    'sale', (select jsonb_agg(jsonb_build_object('id', s.id, 'nome', s.nome,
        'tavoli', (select jsonb_agg(jsonb_build_object('id', t.id, 'nome', t.nome,
            'conto', (select jsonb_build_object('id', c.id, 'totale_cent', (cassa.conto_json(c.id)->>'totale_cent')::int,
                        'da_inviare', (cassa.conto_json(c.id)->>'da_inviare')::int, 'aperto_il', c.aperto_il)
                       from cassa.conti c where c.tavolo_id = t.id and c.stato = 'aperto'))
            order by t.ordine) from cassa.tavoli t where t.sala_id = s.id)) order by s.ordine) from cassa.sale s),
    'banco', coalesce((select jsonb_agg(jsonb_build_object('id', c.id, 'numero_ordine', c.numero_ordine,
        'totale_cent', (cassa.conto_json(c.id)->>'totale_cent')::int) order by c.aperto_il)
        from cassa.conti c where c.tipo = 'banco' and c.stato = 'aperto'), '[]'::jsonb),
    'coda_errori', (select count(*) from cassa.coda where stato = 'errore' and creato_il > now() - interval '1 day'),
    'coda_in_attesa', (select count(*) from cassa.coda where stato in ('in_attesa','presa')),
    'scontrini_errore', (select count(*) from cassa.scontrini where stato = 'errore' and giornata = cassa.giornata()),
    'incassato_oggi_cent', coalesce((select sum(case when tipo = 'annullo' then -totale_cent else totale_cent end)
        from cassa.scontrini where giornata = cassa.giornata() and stato = 'emesso'), 0)) $$;
create or replace function cassa.op_apri(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare c uuid; v_tipo text := coalesce(a->>'tipo','banco'); v_tav text := a->>'tavolo';
begin
  if v_tipo = 'tavolo' then
    if v_tav is null then raise exception 'DATI: manca il tavolo'; end if;
    select id into c from cassa.conti where tavolo_id = v_tav and stato = 'aperto';
    if found then return cassa.conto_json(c); end if;
  end if;
  insert into cassa.conti (giornata, tipo, tavolo_id, listino_id, numero_ordine, coperti, aperto_da)
  values (cassa.giornata(), v_tipo, case when v_tipo = 'tavolo' then v_tav end,
          coalesce(a->>'listino', case when v_tipo = 'tavolo' then 'tavolo' else 'banco' end),
          case when v_tipo = 'banco' then cassa.numero_ordine() end, nullif(a->>'coperti','')::int, o.id)
  returning id into c;
  return cassa.conto_json(c);
end $$;
create or replace function cassa.conto_aperto(p_conto uuid) returns cassa.conti language plpgsql set search_path = cassa, pg_temp as $$
declare c cassa.conti;
begin
  select * into c from cassa.conti where id = p_conto for update;
  if not found then raise exception 'DATI: conto inesistente'; end if;
  if c.stato <> 'aperto' then raise exception 'CONTO_CHIUSO: il conto non e piu aperto'; end if;
  return c;
end $$;
create or replace function cassa.op_aggiungi(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare c cassa.conti; v_prod int := (a->>'prodotto')::int; v_q numeric := coalesce((a->>'quantita')::numeric, 1);
        v_prezzo int; cp cassa.prodotti; v_nome text; r uuid; v_iva numeric;
begin
  c := cassa.conto_aperto((a->>'conto')::uuid);
  select * into cp from cassa.prodotti where product_id = v_prod and vendibile_in_cassa;
  if not found then raise exception 'DATI: prodotto non vendibile'; end if;
  v_prezzo := cassa.prezzo(v_prod, c.listino_id);
  if v_prezzo is null then raise exception 'PREZZO_MANCANTE: il prodotto non ha prezzo'; end if;
  select coalesce(cp.nome_scontrino, upper(m.name)) into v_nome from menu.menu_products m where m.id = v_prod;
  select i.aliquota into v_iva from cassa.reparti rp join cassa.iva i on i.id = rp.iva_id where rp.id = cp.reparto_id;
  if coalesce(a->>'nota','') = '' then
    select id into r from cassa.righe where conto_id = c.id and product_id = v_prod and stato = 'attiva'
       and not inviata and scontrino_id is null and nota is null and sconto_cent = 0 and prezzo_cent = v_prezzo limit 1;
  end if;
  if r is not null then
    update cassa.righe set quantita = quantita + v_q where id = r;
  else
    insert into cassa.righe (conto_id, product_id, descrizione, quantita, prezzo_cent, reparto_id, iva, nota, creata_da)
    values (c.id, v_prod, left(v_nome, 38), v_q, v_prezzo, cp.reparto_id, v_iva, nullif(a->>'nota',''), o.id);
  end if;
  return cassa.conto_json(c.id);
end $$;
create or replace function cassa.op_quantita(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare r cassa.righe; v_q numeric := (a->>'quantita')::numeric;
begin
  select * into r from cassa.righe where id = (a->>'riga')::uuid;
  perform cassa.conto_aperto(r.conto_id);
  if r.inviata or r.scontrino_id is not null or r.stato <> 'attiva' then raise exception 'NON_MODIFICABILE: riga gia inviata o pagata, usa Togli'; end if;
  if v_q is null or v_q <= 0 then
    delete from cassa.righe where id = r.id;
  else
    update cassa.righe set quantita = v_q where id = r.id;
  end if;
  return cassa.conto_json(r.conto_id);
end $$;
create or replace function cassa.op_togli(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare r cassa.righe; c cassa.conti; v_st text;
begin
  select * into r from cassa.righe where id = (a->>'riga')::uuid;
  if not found then raise exception 'DATI: riga inesistente'; end if;
  c := cassa.conto_aperto(r.conto_id);
  if r.scontrino_id is not null or r.stato <> 'attiva' then raise exception 'NON_MODIFICABILE: riga gia pagata o tolta'; end if;
  if not r.inviata then
    delete from cassa.righe where id = r.id;
    return cassa.conto_json(c.id);
  end if;
  if r.creata_da <> o.id then perform cassa.richiedi(o.ruolo, 'cassiere'); end if;
  if coalesce(a->>'motivo','') = '' then raise exception 'MOTIVO: indica il motivo'; end if;
  update cassa.righe set stato = 'tolta', tolta_da = o.id, tolta_il = now(), motivo_tolta = a->>'motivo' where id = r.id;
  select coalesce(i.stampante_id, cassa.cfg('stampante_comande_default')) into v_st
    from menu.menu_products m left join cassa.instradamento i on i.subcategory_id = m.subcategory_id where m.id = r.product_id;
  perform cassa.accoda('comanda', coalesce(v_st, cassa.cfg('stampante_comande_default')), c.id, jsonb_build_object(
    'titolo', case when c.tipo = 'tavolo' then 'TAVOLO ' || c.tavolo_id else 'BANCO N.' || c.numero_ordine end,
    'operatore', o.nome, 'ora', to_char(now() at time zone 'Europe/Rome','HH24:MI'),
    'righe', jsonb_build_array(jsonb_build_object('q', r.quantita, 'd', r.descrizione, 'storno', true, 'nota', a->>'motivo'))));
  perform cassa.registra(o.id, 'togli_riga_inviata', 'riga', r.id::text, to_jsonb(r), jsonb_build_object('motivo', a->>'motivo'));
  return cassa.conto_json(c.id);
end $$;
create or replace function cassa.op_sconto(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare r cassa.righe; v_s int := coalesce((a->>'sconto_cent')::int, 0);
begin
  select * into r from cassa.righe where id = (a->>'riga')::uuid;
  perform cassa.conto_aperto(r.conto_id);
  if r.scontrino_id is not null or r.stato <> 'attiva' then raise exception 'NON_MODIFICABILE: riga pagata o tolta'; end if;
  perform cassa.richiedi(o.ruolo, 'cassiere');
  if v_s > coalesce(cassa.cfg('soglia_sconto_cassiere_cent')::int, 0) then perform cassa.richiedi(o.ruolo, 'responsabile'); end if;
  if v_s < 0 or v_s >= round(r.quantita * r.prezzo_cent) then raise exception 'DATI: sconto non valido'; end if;
  if v_s > 0 and coalesce(a->>'motivo','') = '' then raise exception 'MOTIVO: indica il motivo dello sconto'; end if;
  update cassa.righe set sconto_cent = v_s, motivo_sconto = nullif(a->>'motivo','') where id = r.id;
  perform cassa.registra(o.id, 'sconto', 'riga', r.id::text, jsonb_build_object('sconto_cent', r.sconto_cent), jsonb_build_object('sconto_cent', v_s, 'motivo', a->>'motivo'));
  return cassa.conto_json(r.conto_id);
end $$;
create or replace function cassa.op_cambia_prezzo(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare r cassa.righe; v_p int := (a->>'prezzo_cent')::int;
begin
  select * into r from cassa.righe where id = (a->>'riga')::uuid;
  perform cassa.conto_aperto(r.conto_id);
  perform cassa.richiedi(o.ruolo, 'responsabile');
  if r.scontrino_id is not null or r.stato <> 'attiva' then raise exception 'NON_MODIFICABILE: riga pagata o tolta'; end if;
  if v_p is null or v_p < 0 or coalesce(a->>'motivo','') = '' then raise exception 'DATI: prezzo e motivo obbligatori'; end if;
  update cassa.righe set prezzo_cent = v_p, sconto_cent = 0 where id = r.id;
  perform cassa.registra(o.id, 'cambio_prezzo', 'riga', r.id::text, jsonb_build_object('prezzo_cent', r.prezzo_cent), jsonb_build_object('prezzo_cent', v_p, 'motivo', a->>'motivo'));
  return cassa.conto_json(r.conto_id);
end $$;
create or replace function cassa.op_comanda(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare c cassa.conti; g record; n int := 0;
begin
  c := cassa.conto_aperto((a->>'conto')::uuid);
  for g in
    select coalesce(i.stampante_id, cassa.cfg('stampante_comande_default')) st,
           jsonb_agg(jsonb_build_object('q', r.quantita, 'd', r.descrizione, 'nota', r.nota) order by m.subcategory_id, r.creata_il) righe,
           array_agg(r.id) ids
      from cassa.righe r join menu.menu_products m on m.id = r.product_id
      left join cassa.instradamento i on i.subcategory_id = m.subcategory_id
     where r.conto_id = c.id and r.stato = 'attiva' and not r.inviata
     group by 1
  loop
    perform cassa.accoda('comanda', g.st, c.id, jsonb_build_object(
      'titolo', case when c.tipo = 'tavolo' then 'TAVOLO ' || c.tavolo_id else 'BANCO N.' || c.numero_ordine end,
      'operatore', o.nome, 'ora', to_char(now() at time zone 'Europe/Rome','HH24:MI'), 'coperti', c.coperti, 'righe', g.righe));
    update cassa.righe set inviata = true where id = any(g.ids);
    n := n + 1;
  end loop;
  return cassa.conto_json(c.id) || jsonb_build_object('comande_inviate', n);
end $$;
create or replace function cassa.op_preconto(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare c cassa.conti; j jsonb; v_st text;
begin
  c := cassa.conto_aperto((a->>'conto')::uuid);
  j := cassa.conto_json(c.id);
  if c.tipo = 'tavolo' then select s.stampante_preconto into v_st from cassa.tavoli t join cassa.sale s on s.id = t.sala_id where t.id = c.tavolo_id;
  else v_st := cassa.cfg('stampante_preconto_banco'); end if;
  perform cassa.accoda('preconto', v_st, c.id, jsonb_build_object(
    'titolo', case when c.tipo = 'tavolo' then 'TAVOLO ' || c.tavolo_id else 'BANCO N.' || c.numero_ordine end,
    'operatore', o.nome, 'ora', to_char(now() at time zone 'Europe/Rome','DD/MM/YYYY HH24:MI'),
    'righe', (select coalesce(jsonb_agg(jsonb_build_object('q', x->'quantita', 'd', x->>'descrizione', 'importo_cent', x->'importo_cent')), '[]'::jsonb)
                from jsonb_array_elements(j->'righe') x where (x->>'da_pagare')::boolean),
    'totale_cent', j->'da_pagare_cent'));
  return j;
end $$;
