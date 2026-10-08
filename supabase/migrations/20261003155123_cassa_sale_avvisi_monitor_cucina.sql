-- Struttura recuperata dal registro Supabase (20261003155123) il 08/10/2026.
-- Escluse copie di prodotti, instradamenti/stampanti legacy e orari applicativi.
-- Conservate soltanto configurazioni strutturali; nessun dato operativo storico.
alter table cassa.operatori drop constraint if exists operatori_ruolo_check;
alter table cassa.operatori add constraint operatori_ruolo_check check (ruolo in ('cucina','cameriere','cassiere','responsabile','admin'));
create or replace function cassa.livello(p_ruolo text) returns int language sql immutable as $$
  select case p_ruolo when 'cucina' then 0 when 'cameriere' then 1 when 'cassiere' then 2 when 'responsabile' then 3 when 'admin' then 4 else -1 end $$;
alter table cassa.stampanti add column if not exists stampa boolean not null default true;
alter table cassa.stampanti add column if not exists monitor boolean not null default false;
create table cassa.monitor (
  id bigserial primary key,
  conto_id uuid references cassa.conti(id),
  stampante_id text not null references cassa.stampanti(id),
  titolo text not null,
  payload jsonb not null,
  stato text not null default 'nuova' check (stato in ('nuova','in_preparazione','pronta','consegnata')),
  creata_il timestamptz not null default now(),
  aggiornata_il timestamptz not null default now()
);
create index monitor_aperte on cassa.monitor(stampante_id, stato);
create table cassa.avvisi (
  id bigserial primary key,
  tipo text not null check (tipo in ('ordine','conto','pronto','cassa')),
  per_ruolo text not null default 'cassiere',
  conto_id uuid references cassa.conti(id),
  tavolo_id text,
  testo text not null,
  da_operatore text,
  creato_il timestamptz not null default now(),
  letto_il timestamptz,
  letto_da text
);
create index avvisi_recenti on cassa.avvisi(id) where letto_il is null;
alter table cassa.monitor enable row level security;
alter table cassa.avvisi enable row level security;
create or replace function cassa.avvisa(p_tipo text, p_ruolo text, p_conto uuid, p_testo text, p_da text) returns void language sql set search_path = cassa, pg_temp as $$
  insert into cassa.avvisi (tipo, per_ruolo, conto_id, tavolo_id, testo, da_operatore)
  values (p_tipo, p_ruolo, p_conto, (select tavolo_id from cassa.conti where id = p_conto), p_testo, p_da) $$;
create or replace function cassa.invia_comanda(p_st text, p_conto uuid, p_payload jsonb) returns void language plpgsql set search_path = cassa, pg_temp as $$
declare s cassa.stampanti;
begin
  select * into s from cassa.stampanti where id = p_st;
  if not found or (not s.stampa and not s.monitor) then
    perform cassa.accoda('comanda', coalesce(s.id, cassa.cfg('stampante_comande_default')), p_conto, p_payload); return;
  end if;
  if s.stampa then perform cassa.accoda('comanda', s.id, p_conto, p_payload); end if;
  if s.monitor then
    insert into cassa.monitor (conto_id, stampante_id, titolo, payload) values (p_conto, s.id, p_payload->>'titolo', p_payload);
  end if;
end $$;
create or replace function cassa.op_comanda(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare c cassa.conti; g record; n int := 0; v_tit text; v_pezzi numeric := 0;
begin
  c := cassa.conto_aperto((a->>'conto')::uuid);
  v_tit := case when c.tipo = 'tavolo' then 'TAVOLO ' || c.tavolo_id else 'BANCO N.' || c.numero_ordine end;
  for g in
    select cassa.stampante_prodotto(r.product_id) st,
           jsonb_agg(jsonb_build_object('q', r.quantita, 'd', r.descrizione, 'nota', r.nota) order by b.sub_id, r.creata_il) righe,
           array_agg(r.id) ids, sum(r.quantita) pezzi
      from cassa.righe r left join public.bb_prodotti b on b.id = r.product_id
     where r.conto_id = c.id and r.stato = 'attiva' and not r.inviata
     group by 1
  loop
    perform cassa.invia_comanda(g.st, c.id, jsonb_build_object('titolo', v_tit, 'operatore', o.nome,
      'ora', to_char(now() at time zone 'Europe/Rome','HH24:MI'), 'coperti', c.coperti, 'righe', g.righe));
    update cassa.righe set inviata = true where id = any(g.ids);
    n := n + 1; v_pezzi := v_pezzi + g.pezzi;
  end loop;
  if n > 0 and cassa.livello(o.ruolo) < cassa.livello('cassiere') then
    perform cassa.avvisa('ordine', 'cassiere', c.id, initcap(lower(v_tit)) || ': nuovo ordine, ' || v_pezzi::int || ' pezzi', o.nome);
  end if;
  return cassa.conto_json(c.id) || jsonb_build_object('comande_inviate', n);
end $$;
create or replace function cassa.op_togli(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare r cassa.righe; c cassa.conti;
begin
  select * into r from cassa.righe where id = (a->>'riga')::uuid;
  if not found then raise exception 'DATI: riga inesistente'; end if;
  c := cassa.conto_aperto(r.conto_id);
  if r.scontrino_id is not null or r.stato <> 'attiva' then raise exception 'NON_MODIFICABILE: riga gia pagata o tolta'; end if;
  if not r.inviata then delete from cassa.righe where id = r.id; return cassa.conto_json(c.id); end if;
  if r.creata_da <> o.id then perform cassa.richiedi(o.ruolo, 'cassiere'); end if;
  if coalesce(a->>'motivo','') = '' then raise exception 'MOTIVO: indica il motivo'; end if;
  update cassa.righe set stato = 'tolta', tolta_da = o.id, tolta_il = now(), motivo_tolta = a->>'motivo' where id = r.id;
  perform cassa.invia_comanda(cassa.stampante_prodotto(r.product_id), c.id, jsonb_build_object(
    'titolo', case when c.tipo = 'tavolo' then 'TAVOLO ' || c.tavolo_id else 'BANCO N.' || c.numero_ordine end,
    'operatore', o.nome, 'ora', to_char(now() at time zone 'Europe/Rome','HH24:MI'),
    'righe', jsonb_build_array(jsonb_build_object('q', r.quantita, 'd', r.descrizione, 'storno', true, 'nota', a->>'motivo'))));
  perform cassa.registra(o.id, 'togli_riga_inviata', 'riga', r.id::text, to_jsonb(r), jsonb_build_object('motivo', a->>'motivo'));
  return cassa.conto_json(c.id);
end $$;
create or replace function cassa.op_chiedi_conto(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare c cassa.conti; j jsonb;
begin
  c := cassa.conto_aperto((a->>'conto')::uuid);
  j := cassa.conto_json(c.id);
  perform cassa.avvisa('conto', 'cassiere', c.id,
    initcap(lower(case when c.tipo = 'tavolo' then 'tavolo ' || c.tavolo_id else 'banco n.' || c.numero_ordine end)) || ' chiede il conto: ' ||
    to_char((j->>'da_pagare_cent')::int / 100.0, 'FM999990.00') || ' euro' || coalesce(' (' || nullif(a->>'nota','') || ')', ''), o.nome);
  return j;
end $$;
create or replace function cassa.op_avvisi(o cassa.operatori, a jsonb) returns jsonb language sql stable set search_path = cassa, pg_temp as $$
  select jsonb_build_object(
    'avvisi', coalesce((select jsonb_agg(jsonb_build_object('id', v.id, 'tipo', v.tipo, 'testo', v.testo, 'tavolo', v.tavolo_id, 'conto', v.conto_id,
        'da', v.da_operatore, 'ora', to_char(v.creato_il at time zone 'Europe/Rome','HH24:MI')) order by v.id desc)
      from cassa.avvisi v where v.letto_il is null and v.creato_il > now() - interval '12 hours'
        and cassa.livello(o.ruolo) >= cassa.livello(v.per_ruolo) and o.ruolo <> 'cucina'), '[]'::jsonb),
    'ultimo', (select coalesce(max(id), 0) from cassa.avvisi)) $$;
create or replace function cassa.op_avviso_letto(o cassa.operatori, a jsonb) returns jsonb language sql set search_path = cassa, pg_temp as $$
  update cassa.avvisi set letto_il = now(), letto_da = o.nome
   where letto_il is null and (id = nullif(a->>'id','')::bigint or (a->>'tutti')::boolean);
  select jsonb_build_object('ok', true) $$;
create or replace function cassa.op_cucina(o cassa.operatori, a jsonb) returns jsonb language sql stable set search_path = cassa, pg_temp as $$
  select jsonb_build_object(
    'postazioni', (select jsonb_agg(jsonb_build_object('id', id, 'nome', nome)) from cassa.stampanti where monitor),
    'comande', coalesce((select jsonb_agg(jsonb_build_object('id', m.id, 'titolo', m.titolo, 'stato', m.stato, 'postazione', m.stampante_id,
        'righe', m.payload->'righe', 'operatore', m.payload->>'operatore', 'coperti', m.payload->'coperti',
        'ora', to_char(m.creata_il at time zone 'Europe/Rome','HH24:MI'),
        'minuti', floor(extract(epoch from now() - m.creata_il) / 60)) order by m.id)
      from cassa.monitor m
     where (a->>'postazione' is null or m.stampante_id = a->>'postazione')
       and (m.stato in ('nuova','in_preparazione') or (m.stato = 'pronta' and m.aggiornata_il > now() - interval '10 minutes'))), '[]'::jsonb)) $$;
create or replace function cassa.op_cucina_stato(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare m cassa.monitor; v_st text := a->>'stato';
begin
  if v_st not in ('nuova','in_preparazione','pronta','consegnata') then raise exception 'DATI: stato non valido'; end if;
  update cassa.monitor set stato = v_st, aggiornata_il = now() where id = (a->>'id')::bigint returning * into m;
  if not found then raise exception 'DATI: comanda inesistente'; end if;
  if v_st = 'pronta' then
    perform cassa.avvisa('pronto', 'cameriere', m.conto_id, initcap(lower(m.titolo)) || ': pronto in ' || lower((select nome from cassa.stampanti where id = m.stampante_id)), o.nome);
  end if;
  return jsonb_build_object('ok', true);
end $$;
do $$ declare src text; begin
  select pg_get_functiondef('cassa.api(text,uuid,jsonb)'::regprocedure) into src;
  src := replace(src, E'  select coalesce(max(id), 0) into v_max from cassa.coda;',
E'  if p_azione = ''cucina'' then return cassa.op_cucina(o, a);
  elsif p_azione = ''cucina_stato'' then return cassa.op_cucina_stato(o, a);
  elsif p_azione = ''avvisi'' then return cassa.op_avvisi(o, a);
  elsif p_azione = ''avviso_letto'' then return cassa.op_avviso_letto(o, a);
  elsif p_azione = ''logout'' then delete from cassa.sessioni where token = p_tok; return jsonb_build_object(''ok'', true);
  end if;
  if o.ruolo = ''cucina'' then raise exception ''PERMESSO_NEGATO: il profilo cucina usa solo il monitor''; end if;
  select coalesce(max(id), 0) into v_max from cassa.coda;');
  src := replace(src, E'    when ''preconto'' then r := cassa.op_preconto(o, a);',
E'    when ''preconto'' then r := cassa.op_preconto(o, a);\n    when ''chiedi_conto'' then r := cassa.op_chiedi_conto(o, a);');
  src := replace(src, E'''stampanti'' then r := (select jsonb_agg(jsonb_build_object(''id'', id, ''nome'', nome, ''tipo'', tipo, ''ip'', ip, ''devid'', devid, ''modello'', modello) order by id) from cassa.stampanti where attiva);',
E'''stampanti'' then r := (select jsonb_agg(jsonb_build_object(''id'', id, ''nome'', nome, ''tipo'', tipo, ''ip'', ip, ''devid'', devid, ''modello'', modello, ''stampa'', stampa, ''monitor'', monitor) order by id) from cassa.stampanti where attiva);');
  execute src;
end $$;
do $$ declare src text; begin
  select pg_get_functiondef('cassa.op_admin(cassa.operatori,text,jsonb)'::regprocedure) into src;
  src := replace(src, E'update cassa.stampanti set ip = coalesce(a->>''ip'', ip) where id = a->>''id'';',
    E'update cassa.stampanti set ip = coalesce(a->>''ip'', ip), stampa = coalesce((a->>''stampa'')::boolean, stampa), monitor = coalesce((a->>''monitor'')::boolean, monitor) where id = a->>''id'';');
  execute src;
end $$;
revoke all on all functions in schema cassa from public, anon, authenticated;
