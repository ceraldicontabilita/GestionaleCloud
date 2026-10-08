-- Struttura recuperata dal registro Supabase (20261003154447) il 08/10/2026.
-- Escluse copie di prodotti, instradamenti/stampanti legacy e orari applicativi.
-- Conservate soltanto configurazioni strutturali; nessun dato operativo storico.
alter table cassa.righe drop constraint if exists righe_product_id_fkey;
alter table cassa.movimenti drop constraint if exists movimenti_product_id_fkey;
alter table cassa.prezzi drop constraint if exists prezzi_product_id_fkey;
alter table cassa.prodotti drop constraint if exists prodotti_product_id_fkey;
alter table cassa.prodotti alter column reparto_id drop not null;
alter table cassa.righe add constraint righe_product_id_fkey foreign key (product_id) references public.bb_prodotti(id) on delete set null;
alter table cassa.movimenti add constraint movimenti_product_id_fkey foreign key (product_id) references public.bb_prodotti(id) on delete set null;
alter table cassa.prezzi add constraint prezzi_product_id_fkey foreign key (product_id) references public.bb_prodotti(id) on delete cascade;
alter table cassa.prodotti add constraint prodotti_product_id_fkey foreign key (product_id) references public.bb_prodotti(id) on delete cascade;
insert into cassa.config (k, v, nota) values
 ('reparto_default','rep1','Reparto usato per i prodotti del catalogo senza reparto specifico'),
 ('categorie_escluse','19643','Categorie del catalogo non vendibili in cassa (Comunicazioni)')
on conflict (k) do nothing;
create or replace function cassa.prezzo(p_prod int, p_listino text) returns int language sql stable set search_path = cassa, pg_temp as $$
  select coalesce(
    (select prezzo_cent from cassa.prezzi where product_id = p_prod and listino_id = p_listino),
    (select nullif(round(case when p_listino = 'tavolo' then coalesce(b.prezzo_tavolo, b.prezzo) else coalesce(b.prezzo, b.prezzo_tavolo) end * 100)::int, 0)
       from public.bb_prodotti b where b.id = p_prod)) $$;
create or replace function cassa.reparto_prodotto(p_prod int) returns text language sql stable set search_path = cassa, pg_temp as $$
  select coalesce((select reparto_id from cassa.prodotti where product_id = p_prod), cassa.cfg('reparto_default')) $$;
create or replace function cassa.vendibile(p_prod int) returns boolean language sql stable set search_path = cassa, pg_temp as $$
  select exists (select 1 from public.bb_prodotti b where b.id = p_prod
                  and b.cat_id <> all (string_to_array(coalesce(cassa.cfg('categorie_escluse'),''), ',')::int[]))
     and coalesce((select vendibile_in_cassa from cassa.prodotti where product_id = p_prod), true) $$;
create or replace function cassa.op_catalogo(o cassa.operatori, a jsonb) returns jsonb language sql stable set search_path = cassa, pg_temp as $$
  with l as (select coalesce(a->>'listino','banco') as listino),
  p as (
    select b.id, coalesce(cp.nome_pulsante, b.nome) nome, b.sub_id, b.cat_id, coalesce(cp.preferito, false) preferito,
           coalesce(cp.reparto_id, cassa.cfg('reparto_default')) reparto_id, cassa.prezzo(b.id, (select listino from l)) prezzo
      from public.bb_prodotti b left join cassa.prodotti cp on cp.product_id = b.id
     where cassa.vendibile(b.id))
  select jsonb_build_object(
    'listino', (select listino from l),
    'categorie', coalesce((select jsonb_agg(jsonb_build_object('id', s.id, 'nome', s.nome) order by c.ordine, s.ordine, s.id)
        from public.bb_prod_sub s join public.bb_prod_cat c on c.id = s.cat_id
       where exists (select 1 from p where p.sub_id = s.id and p.prezzo is not null)), '[]'::jsonb),
    'prodotti', coalesce((select jsonb_agg(jsonb_build_object('id', p.id, 'nome', p.nome, 'categoria', p.sub_id,
        'prezzo_cent', p.prezzo, 'preferito', p.preferito, 'reparto', p.reparto_id) order by p.nome)
        from p where p.prezzo is not null), '[]'::jsonb),
    'senza_prezzo', (select count(*) from p where p.prezzo is null)) $$;
create or replace function cassa.op_aggiungi(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare c cassa.conti; v_prod int := (a->>'prodotto')::int; v_q numeric := coalesce((a->>'quantita')::numeric, 1);
        v_prezzo int; v_rep text; v_nome text; r uuid; v_iva numeric;
begin
  c := cassa.conto_aperto((a->>'conto')::uuid);
  if not cassa.vendibile(v_prod) then raise exception 'DATI: prodotto non vendibile in cassa'; end if;
  v_prezzo := cassa.prezzo(v_prod, c.listino_id);
  if v_prezzo is null then raise exception 'PREZZO_MANCANTE: il prodotto non ha prezzo'; end if;
  v_rep := cassa.reparto_prodotto(v_prod);
  select coalesce(cp.nome_scontrino, upper(b.nome)) into v_nome
    from public.bb_prodotti b left join cassa.prodotti cp on cp.product_id = b.id where b.id = v_prod;
  select i.aliquota into v_iva from cassa.reparti rp join cassa.iva i on i.id = rp.iva_id where rp.id = v_rep;
  if coalesce(a->>'nota','') = '' then
    select id into r from cassa.righe where conto_id = c.id and product_id = v_prod and stato = 'attiva'
       and not inviata and scontrino_id is null and nota is null and sconto_cent = 0 and prezzo_cent = v_prezzo limit 1;
  end if;
  if r is not null then
    update cassa.righe set quantita = quantita + v_q where id = r;
  else
    insert into cassa.righe (conto_id, product_id, descrizione, quantita, prezzo_cent, reparto_id, iva, nota, creata_da)
    values (c.id, v_prod, left(v_nome, 38), v_q, v_prezzo, v_rep, v_iva, nullif(a->>'nota',''), o.id);
  end if;
  return cassa.conto_json(c.id);
end $$;
create or replace function cassa.stampante_prodotto(p_prod int) returns text language sql stable set search_path = cassa, pg_temp as $$
  select coalesce((select i.stampante_id from public.bb_prodotti b join cassa.instradamento i on i.subcategory_id = b.sub_id where b.id = p_prod),
                  cassa.cfg('stampante_comande_default')) $$;
create or replace function cassa.op_comanda(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare c cassa.conti; g record; n int := 0;
begin
  c := cassa.conto_aperto((a->>'conto')::uuid);
  for g in
    select cassa.stampante_prodotto(r.product_id) st,
           jsonb_agg(jsonb_build_object('q', r.quantita, 'd', r.descrizione, 'nota', r.nota) order by b.sub_id, r.creata_il) righe,
           array_agg(r.id) ids
      from cassa.righe r left join public.bb_prodotti b on b.id = r.product_id
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
create or replace function cassa.op_togli(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare r cassa.righe; c cassa.conti;
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
  perform cassa.accoda('comanda', cassa.stampante_prodotto(r.product_id), c.id, jsonb_build_object(
    'titolo', case when c.tipo = 'tavolo' then 'TAVOLO ' || c.tavolo_id else 'BANCO N.' || c.numero_ordine end,
    'operatore', o.nome, 'ora', to_char(now() at time zone 'Europe/Rome','HH24:MI'),
    'righe', jsonb_build_array(jsonb_build_object('q', r.quantita, 'd', r.descrizione, 'storno', true, 'nota', a->>'motivo'))));
  perform cassa.registra(o.id, 'togli_riga_inviata', 'riga', r.id::text, to_jsonb(r), jsonb_build_object('motivo', a->>'motivo'));
  return cassa.conto_json(c.id);
end $$;
revoke all on all functions in schema cassa from public, anon, authenticated;
