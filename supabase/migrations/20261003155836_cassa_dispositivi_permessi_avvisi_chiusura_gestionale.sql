-- Struttura recuperata dal registro Supabase (20261003155836) il 08/10/2026.
-- Escluse copie di prodotti, instradamenti/stampanti legacy e orari applicativi.
-- Conservate soltanto configurazioni strutturali; nessun dato operativo storico.
update cassa.config set v = '99MEY026532', nota = 'Matricola Epson FP-90III RT (dai corrispettivi XML)' where k = 'rt_matricola';
create table cassa.dispositivi (
  id uuid primary key default gen_random_uuid(),
  nome text not null,
  tipo text not null check (tipo in ('cassa','sala','palmare','cucina')),
  sala_id text references cassa.sale(id),
  attivo boolean not null default true,
  creato_il timestamptz not null default now(),
  check (tipo <> 'sala' or sala_id is not null)
);
alter table cassa.dispositivi enable row level security;
alter table cassa.sessioni add column if not exists dispositivo_id uuid references cassa.dispositivi(id);
create or replace function cassa.disp() returns cassa.dispositivi language sql stable set search_path = cassa, pg_temp as $$
  select * from cassa.dispositivi where id = nullif(current_setting('cassa.dispositivo', true), '')::uuid $$;
create or replace function cassa.chiave_lettore(o cassa.operatori) returns text language sql stable set search_path = cassa, pg_temp as $$
  select case when (cassa.disp()).tipo = 'sala' then 'sala:' || (cassa.disp()).sala_id
              when cassa.livello(o.ruolo) >= 2 and coalesce((cassa.disp()).tipo, 'cassa') = 'cassa' then 'cassa'
              else 'op:' || o.id end $$;
create or replace function cassa.op_login(a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare o cassa.operatori; t uuid; d cassa.dispositivi;
begin
  select * into o from cassa.operatori where attivo and pin_hash = extensions.crypt(coalesce(a->>'pin',''), pin_hash) limit 1;
  if not found then perform pg_sleep(1); raise exception 'PIN_ERRATO: PIN non valido'; end if;
  if nullif(a->>'dispositivo','') is not null then
    select * into d from cassa.dispositivi where id = (a->>'dispositivo')::uuid and attivo;
    if not found then raise exception 'DISPOSITIVO: questo dispositivo non e piu registrato, chiedi all amministratore'; end if;
    if d.tipo = 'cassa' and cassa.livello(o.ruolo) < 2 then raise exception 'PERMESSO_NEGATO: questo tablet e la cassa, serve un cassiere'; end if;
    if d.tipo = 'cucina' and o.ruolo not in ('cucina','admin') then raise exception 'PERMESSO_NEGATO: questo schermo e riservato alla cucina'; end if;
    if d.tipo in ('sala','palmare') and o.ruolo = 'cucina' then raise exception 'PERMESSO_NEGATO: il profilo cucina usa il monitor'; end if;
  end if;
  insert into cassa.sessioni (operatore_id, dispositivo_id) values (o.id, d.id) returning token into t;
  perform cassa.registra(o.id, 'login', 'operatore', o.id::text, null, jsonb_build_object('dispositivo', d.nome));
  return jsonb_build_object('token', t, 'nome', o.nome, 'ruolo', o.ruolo,
    'dispositivo', case when d.id is null then null else jsonb_build_object('id', d.id, 'nome', d.nome, 'tipo', d.tipo, 'sala', d.sala_id) end);
end $$;
alter table cassa.avvisi add column if not exists per text not null default 'cassa' check (per in ('cassa','sala','tutti'));
alter table cassa.avvisi add column if not exists sala_id text;
create table if not exists cassa.avvisi_letti (avviso_id bigint references cassa.avvisi(id) on delete cascade, chiave text, letto_il timestamptz default now(), primary key (avviso_id, chiave));
alter table cassa.avvisi_letti enable row level security;
drop function if exists cassa.avvisa(text, text, uuid, text, text);
create or replace function cassa.avvisa(p_tipo text, p_per text, p_conto uuid, p_testo text, p_da text) returns void language sql set search_path = cassa, pg_temp as $$
  insert into cassa.avvisi (tipo, per, per_ruolo, conto_id, tavolo_id, sala_id, testo, da_operatore)
  select p_tipo, p_per, 'cameriere', p_conto, c.tavolo_id, t.sala_id, p_testo, p_da
    from (select p_conto id) x left join cassa.conti c on c.id = x.id left join cassa.tavoli t on t.id = c.tavolo_id $$;
create or replace function cassa.avvisi_visibili(o cassa.operatori) returns setof cassa.avvisi language sql stable set search_path = cassa, pg_temp as $$
  select v.* from cassa.avvisi v
   where v.creato_il > now() - interval '12 hours'
     and not exists (select 1 from cassa.avvisi_letti l where l.avviso_id = v.id and l.chiave = cassa.chiave_lettore(o))
     and case
       when o.ruolo = 'cucina' then false
       when (cassa.disp()).tipo = 'sala' then v.sala_id = (cassa.disp()).sala_id and v.per in ('sala','tutti')
       when cassa.chiave_lettore(o) = 'cassa' then v.per in ('cassa','tutti')
       else v.per = 'tutti' and v.tipo = 'pronto' end $$;
create or replace function cassa.op_avvisi(o cassa.operatori, a jsonb) returns jsonb language sql stable set search_path = cassa, pg_temp as $$
  select jsonb_build_object(
    'avvisi', coalesce((select jsonb_agg(jsonb_build_object('id', v.id, 'tipo', v.tipo, 'testo', v.testo, 'tavolo', v.tavolo_id, 'conto', v.conto_id,
        'da', v.da_operatore, 'ora', to_char(v.creato_il at time zone 'Europe/Rome','HH24:MI')) order by v.id desc) from cassa.avvisi_visibili(o) v), '[]'::jsonb),
    'ultimo', (select coalesce(max(id), 0) from cassa.avvisi)) $$;
create or replace function cassa.op_avviso_letto(o cassa.operatori, a jsonb) returns jsonb language sql set search_path = cassa, pg_temp as $$
  insert into cassa.avvisi_letti (avviso_id, chiave)
  select v.id, cassa.chiave_lettore(o) from cassa.avvisi_visibili(o) v
   where v.id = nullif(a->>'id','')::bigint or coalesce((a->>'tutti')::boolean, false)
  on conflict do nothing;
  select jsonb_build_object('ok', true) $$;
create or replace function cassa.controlla_tavolo(p_tavolo text) returns void language plpgsql stable set search_path = cassa, pg_temp as $$
begin
  if (cassa.disp()).tipo = 'sala' and not exists (select 1 from cassa.tavoli where id = p_tavolo and sala_id = (cassa.disp()).sala_id) then
    raise exception 'PERMESSO_NEGATO: questo tablet gestisce solo la %', (select nome from cassa.sale where id = (cassa.disp()).sala_id);
  end if;
end $$;
create or replace function cassa.op_conto(o cassa.operatori, a jsonb) returns jsonb language plpgsql stable set search_path = cassa, pg_temp as $$
declare c cassa.conti;
begin
  select * into c from cassa.conti where id = (a->>'conto')::uuid;
  if not found then raise exception 'DATI: conto inesistente'; end if;
  if c.tipo = 'banco' then perform cassa.richiedi(o.ruolo, 'cassiere'); else perform cassa.controlla_tavolo(c.tavolo_id); end if;
  return cassa.conto_json(c.id);
end $$;
create or replace function cassa.op_stato(o cassa.operatori, a jsonb) returns jsonb language sql stable set search_path = cassa, pg_temp as $$
  with s as (select * from cassa.sale where (cassa.disp()).tipo is distinct from 'sala' or id = (cassa.disp()).sala_id),
  cassiere as (select cassa.livello(o.ruolo) >= 2 as si)
  select jsonb_build_object(
    'operatore', jsonb_build_object('nome', o.nome, 'ruolo', o.ruolo),
    'giornata', cassa.giornata(),
    'sale', (select jsonb_agg(jsonb_build_object('id', s.id, 'nome', s.nome,
        'tavoli', (select jsonb_agg(jsonb_build_object('id', t.id, 'nome', t.nome,
            'conto', (select jsonb_build_object('id', c.id, 'totale_cent', (cassa.conto_json(c.id)->>'totale_cent')::int,
                        'da_inviare', (cassa.conto_json(c.id)->>'da_inviare')::int, 'aperto_il', c.aperto_il)
                       from cassa.conti c where c.tavolo_id = t.id and c.stato = 'aperto'))
            order by t.ordine) from cassa.tavoli t where t.sala_id = s.id)) order by s.ordine) from s),
    'banco', case when (select si from cassiere) then coalesce((select jsonb_agg(jsonb_build_object('id', c.id, 'numero_ordine', c.numero_ordine,
        'totale_cent', (cassa.conto_json(c.id)->>'totale_cent')::int) order by c.aperto_il)
        from cassa.conti c where c.tipo = 'banco' and c.stato = 'aperto'), '[]'::jsonb) else '[]'::jsonb end,
    'incassato_oggi_cent', case when (select si from cassiere) then coalesce((select sum(case when tipo = 'annullo' then -totale_cent else totale_cent end)
        from cassa.scontrini where giornata = cassa.giornata() and stato = 'emesso'), 0) end) $$;
create or replace function cassa.op_apri(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare c uuid; v_tipo text := coalesce(a->>'tipo','banco'); v_tav text := a->>'tavolo';
begin
  if v_tipo = 'tavolo' then
    if v_tav is null then raise exception 'DATI: manca il tavolo'; end if;
    perform cassa.controlla_tavolo(v_tav);
    select id into c from cassa.conti where tavolo_id = v_tav and stato = 'aperto';
    if found then return cassa.conto_json(c); end if;
  else
    perform cassa.richiedi(o.ruolo, 'cassiere');
  end if;
  insert into cassa.conti (giornata, tipo, tavolo_id, listino_id, numero_ordine, coperti, aperto_da)
  values (cassa.giornata(), v_tipo, case when v_tipo = 'tavolo' then v_tav end,
          coalesce(a->>'listino', case when v_tipo = 'tavolo' then 'tavolo' else 'banco' end),
          case when v_tipo = 'banco' then cassa.numero_ordine() end, nullif(a->>'coperti','')::int, o.id)
  returning id into c;
  return cassa.conto_json(c);
end $$;
do $$ declare src text; begin
  select pg_get_functiondef('cassa.op_togli(cassa.operatori,jsonb)'::regprocedure) into src;
  src := replace(src, 'if r.creata_da <> o.id then perform cassa.richiedi(o.ruolo, ''cassiere''); end if;', 'perform cassa.richiedi(o.ruolo, ''cassiere'');');
  execute src;
  select pg_get_functiondef('cassa.conto_aperto(uuid)'::regprocedure) into src;
  src := replace(src, 'if c.stato <> ''aperto'' then', E'if c.tipo = ''tavolo'' then perform cassa.controlla_tavolo(c.tavolo_id); end if;\n  if c.stato <> ''aperto'' then');
  execute src;
end $$;
create or replace function cassa.op_comanda(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare c cassa.conti; g record; n int := 0; v_tit text; v_pezzi numeric := 0; v_per text;
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
  if n > 0 and c.tipo = 'tavolo' then
    v_per := case when (cassa.disp()).tipo = 'sala' then 'cassa'
                  when cassa.chiave_lettore(o) = 'cassa' then 'sala'
                  else 'tutti' end;
    perform cassa.avvisa('ordine', v_per, c.id, initcap(lower(v_tit)) || ': nuovo ordine, ' || v_pezzi::int || ' pezzi', o.nome);
  end if;
  return cassa.conto_json(c.id) || jsonb_build_object('comande_inviate', n);
end $$;
do $$ declare src text; begin
  select pg_get_functiondef('cassa.op_chiedi_conto(cassa.operatori,jsonb)'::regprocedure) into src;
  src := replace(src, 'cassa.avvisa(''conto'', ''cassiere'',', 'cassa.avvisa(''conto'', ''cassa'',');
  execute src;
  select pg_get_functiondef('cassa.op_cucina_stato(cassa.operatori,jsonb)'::regprocedure) into src;
  src := replace(src, 'cassa.avvisa(''pronto'', ''cameriere'',', 'cassa.avvisa(''pronto'', ''tutti'',');
  execute src;
end $$;
create or replace function cassa.esporta_chiusura(p_id uuid) returns void language plpgsql set search_path = cassa, pg_temp as $$
declare ch cassa.chiusure; v_corr jsonb;
begin
  select * into ch from cassa.chiusure where id = p_id and stato = 'fatta';
  if not found then return; end if;
  select data into v_corr from gestionale.documents where collection = 'corrispettivi' and data->>'data' = ch.giornata::text
     and coalesce(data->>'status','') <> 'deleted' order by updated_at desc limit 1;
  insert into gestionale.documents (collection, id, data, idempotency_key)
  values ('cassa_chiusure', replace(ch.id::text, '-', ''), jsonb_build_object(
      'id', ch.id, 'data', ch.giornata, 'anno', extract(year from ch.giornata)::int, 'mese', extract(month from ch.giornata)::int,
      'source', 'cassa_ceraldi', 'fonte_dato', 'cassa', 'stato_dato', 'da_confrontare_con_xml',
      'matricola_rt', cassa.cfg('rt_matricola'), 'numero_z', ch.z_numero,
      'totale', round(ch.totale_cassa_cent / 100.0, 2), 'totale_cents', ch.totale_cassa_cent,
      'totale_registratore_cents', ch.totale_rt_cent,
      'pagato_contanti', round(ch.contanti_teorici_cent / 100.0, 2), 'pagato_elettronico', round(ch.elettronico_cent / 100.0, 2),
      'contanti_contati', round(ch.contanti_contati_cent / 100.0, 2), 'differenza_contanti', round(ch.differenza_cent / 100.0, 2),
      'numero_documenti', ch.totali->'scontrini', 'annulli', ch.totali->'annulli',
      'riepilogo_iva', (select jsonb_agg(jsonb_build_object('aliquota_iva', to_char((x->>'iva')::numeric, 'FM990.00'), 'reparto', x->>'reparto', 'totale_cents', (x->>'totale_cent')::int))
                          from jsonb_array_elements(ch.totali->'per_reparto') x),
      'senza_scontrino', ch.totali->'senza_documento',
      'corrispettivo_xml_id', v_corr->>'id',
      'differenza_con_xml', case when v_corr is not null then round(ch.totale_cassa_cent / 100.0 - (v_corr->>'totale')::numeric, 2) end,
      'nota', 'Chiusura registrata dalla cassa. La prima nota resta generata dal corrispettivo XML: questo documento serve al confronto.'),
    'cassa_chiusura:' || ch.id)
  on conflict (collection, id) do update set data = excluded.data, updated_at = now();
end $$;
do $$ declare src text; begin
  select pg_get_functiondef('cassa.esito_lavoro(bigint,boolean,jsonb)'::regprocedure) into src;
  src := replace(src, 'z_numero = (d->>''z'')::int, totale_rt_cent = (d->>''totale_cent'')::int, errore = d->>''errore'' where id = j.rif_id;',
                      E'z_numero = (d->>''z'')::int, totale_rt_cent = (d->>''totale_cent'')::int, errore = d->>''errore'' where id = j.rif_id;\n    if v_ok then perform cassa.esporta_chiusura(j.rif_id); end if;');
  execute src;
end $$;
create or replace function cassa.op_dispositivo_salva(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare v uuid;
begin
  perform cassa.richiedi(o.ruolo, 'admin');
  if a ? 'id' then
    update cassa.dispositivi set nome = coalesce(a->>'nome', nome), tipo = coalesce(a->>'tipo', tipo),
           sala_id = case when coalesce(a->>'tipo', tipo) = 'sala' then coalesce(a->>'sala', sala_id) end,
           attivo = coalesce((a->>'attivo')::boolean, attivo) where id = (a->>'id')::uuid returning id into v;
  else
    insert into cassa.dispositivi (nome, tipo, sala_id) values (a->>'nome', a->>'tipo', case when a->>'tipo' = 'sala' then a->>'sala' end) returning id into v;
  end if;
  perform cassa.registra(o.id, 'dispositivo_salvato', 'dispositivo', v::text, null, a);
  return jsonb_build_object('id', v);
end $$;
do $$ declare src text; begin
  select pg_get_functiondef('cassa.api(text,uuid,jsonb)'::regprocedure) into src;
  src := replace(src, E'  o := cassa.operatore(p_tok);',
E'  o := cassa.operatore(p_tok);\n  perform set_config(''cassa.dispositivo'', coalesce((select dispositivo_id::text from cassa.sessioni where token = p_tok), ''''), true);');
  src := replace(src, E'    when ''conto'' then r := cassa.conto_json((a->>''conto'')::uuid);', E'    when ''conto'' then r := cassa.op_conto(o, a);');
  src := replace(src, E'    when ''scontrini'' then r := cassa.op_scontrini(o, a);', E'    when ''scontrini'' then perform cassa.richiedi(o.ruolo, ''cassiere''); r := cassa.op_scontrini(o, a);');
  src := replace(src, E'    when ''chiusure'' then r := cassa.op_chiusure(o, a);', E'    when ''chiusure'' then perform cassa.richiedi(o.ruolo, ''cassiere''); r := cassa.op_chiusure(o, a);');
  src := replace(src, E'    when ''totali'' then r :=', E'    when ''dispositivi'' then perform cassa.richiedi(o.ruolo, ''admin''); r := (select coalesce(jsonb_agg(to_jsonb(d) order by d.nome), ''[]''::jsonb) from cassa.dispositivi d);\n    when ''dispositivo_salva'' then r := cassa.op_dispositivo_salva(o, a);\n    when ''totali'' then perform cassa.richiedi(o.ruolo, ''cassiere''); r :=');
  execute src;
end $$;
revoke all on all functions in schema cassa from public, anon, authenticated;
