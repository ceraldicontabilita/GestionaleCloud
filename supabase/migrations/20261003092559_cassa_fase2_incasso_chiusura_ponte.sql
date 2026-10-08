-- Struttura recuperata dal registro Supabase (20261003092559) il 08/10/2026.
-- Escluse copie di prodotti, instradamenti/stampanti legacy e orari applicativi.
-- Conservate soltanto configurazioni strutturali; nessun dato operativo storico.
create or replace function cassa.righe_selezionate(c cassa.conti, a jsonb) returns uuid[] language plpgsql set search_path = cassa, pg_temp as $$
declare ids uuid[];
begin
  if a ? 'righe' and jsonb_array_length(a->'righe') > 0 then
    select array_agg(r.id) into ids from cassa.righe r
     where r.conto_id = c.id and r.id in (select (x)::uuid from jsonb_array_elements_text(a->'righe') x) and cassa.riga_da_pagare(r);
    if coalesce(array_length(ids,1),0) <> jsonb_array_length(a->'righe') then raise exception 'DATI: alcune righe non sono da pagare'; end if;
  else
    select array_agg(r.id) into ids from cassa.righe r where r.conto_id = c.id and cassa.riga_da_pagare(r);
  end if;
  if ids is null then raise exception 'VUOTO: niente da pagare'; end if;
  perform 1 from cassa.righe where id = any(ids) for update;
  return ids;
end $$;
create or replace function cassa.op_paga(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare c cassa.conti; ids uuid[]; v_tot int; v_contanti int := 0; v_carta int := 0; v_resto int; s uuid; p jsonb; v_payload jsonb;
begin
  perform cassa.richiedi(o.ruolo, 'cassiere');
  c := cassa.conto_aperto((a->>'conto')::uuid);
  ids := cassa.righe_selezionate(c, a);
  select sum(cassa.importo_riga(r)) into v_tot from cassa.righe r where r.id = any(ids);
  if v_tot <= 0 then raise exception 'DATI: totale non valido'; end if;
  if exists (select 1 from cassa.righe r join cassa.reparti rp on rp.id = r.reparto_id where r.id = any(ids) and rp.numero_rt is null) then
    raise exception 'REPARTO_SENZA_NUMERO_RT: un reparto non ha il numero del registratore';
  end if;
  for p in select * from jsonb_array_elements(coalesce(a->'pagamenti', '[]'::jsonb)) loop
    if p->>'metodo' = 'contanti' then v_contanti := v_contanti + (p->>'importo_cent')::int;
    elsif p->>'metodo' = 'carta' then v_carta := v_carta + (p->>'importo_cent')::int;
    else raise exception 'DATI: metodo di pagamento non valido'; end if;
  end loop;
  if v_contanti + v_carta = 0 then v_contanti := v_tot; end if;
  if v_carta > v_tot then raise exception 'DATI: la carta supera il totale'; end if;
  if v_contanti + v_carta < v_tot then raise exception 'IMPORTO_INSUFFICIENTE: mancano % cent', v_tot - v_contanti - v_carta; end if;
  v_resto := v_contanti + v_carta - v_tot;
  insert into cassa.scontrini (conto_id, giornata, tipo, totale_cent, operatore_id) values (c.id, cassa.giornata(), 'vendita', v_tot, o.id) returning id into s;
  update cassa.righe set scontrino_id = s where id = any(ids);
  if v_carta > 0 then insert into cassa.pagamenti (scontrino_id, metodo, importo_cent, riferimento) values (s, 'carta', v_carta, a->>'riferimento'); end if;
  if v_contanti > 0 then insert into cassa.pagamenti (scontrino_id, metodo, importo_cent, resto_cent) values (s, 'contanti', v_contanti, v_resto); end if;
  v_payload := jsonb_build_object(
    'operatore_rt', o.operatore_rt,
    'righe', (select jsonb_agg(jsonb_build_object('d', r.descrizione, 'q', r.quantita, 'p', r.prezzo_cent, 'rep', rp.numero_rt, 'sconto', r.sconto_cent) order by r.creata_il)
                from cassa.righe r join cassa.reparti rp on rp.id = r.reparto_id where r.id = any(ids)),
    'pagamenti', (select jsonb_agg(x) from (
        select jsonb_build_object('tipo', 2, 'indice', 1, 'importo_cent', v_carta, 'descrizione', 'PAGAMENTO ELETTRONICO') x where v_carta > 0
        union all
        select jsonb_build_object('tipo', 0, 'indice', 0, 'importo_cent', v_contanti, 'descrizione', 'CONTANTI') where v_contanti > 0) q),
    'cassetto', v_contanti > 0,
    'totale_cent', v_tot);
  perform cassa.accoda('fiscale', 'fiscale', s, v_payload);
  return jsonb_build_object('scontrino', s, 'totale_cent', v_tot, 'resto_cent', v_resto, 'conto', cassa.conto_json(c.id));
end $$;
create or replace function cassa.op_senza_documento(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare c cassa.conti; ids uuid[]; v_tot int; s uuid; v_causale text := a->>'causale';
begin
  perform cassa.richiedi(o.ruolo, 'responsabile');
  if v_causale not in ('consumo_interno','omaggio','prova') then raise exception 'CAUSALE: scegli consumo_interno, omaggio o prova'; end if;
  c := cassa.conto_aperto((a->>'conto')::uuid);
  ids := cassa.righe_selezionate(c, a);
  select sum(cassa.importo_riga(r)) into v_tot from cassa.righe r where r.id = any(ids);
  insert into cassa.scontrini (conto_id, giornata, tipo, causale, totale_cent, stato, operatore_id, emesso_il)
  values (c.id, cassa.giornata(), 'senza_documento', v_causale, v_tot, 'registrato', o.id, now()) returning id into s;
  update cassa.righe set scontrino_id = s where id = any(ids);
  insert into cassa.movimenti (product_id, quantita, causale, scontrino_id)
    select r.product_id, -r.quantita, v_causale, s from cassa.righe r where r.id = any(ids) and r.product_id is not null;
  perform cassa.chiudi_se_finito(c.id);
  perform cassa.registra(o.id, 'chiusura_senza_documento', 'scontrino', s::text, null, jsonb_build_object('causale', v_causale, 'totale_cent', v_tot));
  return jsonb_build_object('scontrino', s, 'conto', cassa.conto_json(c.id));
end $$;
create or replace function cassa.op_annulla(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare s cassa.scontrini; v_matr text := cassa.cfg('rt_matricola'); n uuid; v_data text;
begin
  perform cassa.richiedi(o.ruolo, 'responsabile');
  select * into s from cassa.scontrini where id = (a->>'scontrino')::uuid for update;
  if not found or s.tipo <> 'vendita' or s.stato <> 'emesso' then raise exception 'DATI: si annulla solo uno scontrino di vendita emesso'; end if;
  if exists (select 1 from cassa.scontrini where riferimento_id = s.id and stato in ('in_coda','emesso')) then raise exception 'DATI: annullo gia richiesto'; end if;
  if v_matr is null or length(v_matr) <> 11 then raise exception 'CONFIGURAZIONE: inserisci la matricola del registratore (rt_matricola)'; end if;
  if coalesce(a->>'motivo','') = '' then raise exception 'MOTIVO: indica il motivo dell annullo'; end if;
  v_data := replace(s.data_rt, '/', '');
  insert into cassa.scontrini (conto_id, giornata, tipo, causale, totale_cent, riferimento_id, operatore_id)
  values (s.conto_id, cassa.giornata(), 'annullo', a->>'motivo', s.totale_cent, s.id, o.id) returning id into n;
  perform cassa.accoda('annullo', 'fiscale', n, jsonb_build_object('operatore_rt', o.operatore_rt,
    'messaggio', format('VOID %s %s %s %s', lpad(s.z_numero::text,4,'0'), lpad(s.numero_rt::text,4,'0'), v_data, v_matr)));
  perform cassa.registra(o.id, 'annullo_richiesto', 'scontrino', s.id::text, null, jsonb_build_object('motivo', a->>'motivo'));
  return jsonb_build_object('annullo', n);
end $$;
create or replace function cassa.op_riprova(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare s cassa.scontrini; j cassa.coda;
begin
  perform cassa.richiedi(o.ruolo, 'cassiere');
  select * into s from cassa.scontrini where id = (a->>'scontrino')::uuid for update;
  if not found or s.stato <> 'errore' then raise exception 'DATI: lo scontrino non e in errore'; end if;
  select * into j from cassa.coda where rif_id = s.id order by id desc limit 1;
  update cassa.scontrini set stato = 'in_coda', errore = null where id = s.id;
  perform cassa.accoda(j.tipo, j.stampante_id, s.id, j.payload);
  perform cassa.registra(o.id, 'riprova_stampa', 'scontrino', s.id::text, null, null);
  return jsonb_build_object('ok', true);
end $$;
create or replace function cassa.op_sblocca(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare s cassa.scontrini;
begin
  perform cassa.richiedi(o.ruolo, 'responsabile');
  select * into s from cassa.scontrini where id = (a->>'scontrino')::uuid for update;
  if not found or s.stato <> 'errore' then raise exception 'DATI: si sblocca solo uno scontrino in errore'; end if;
  update cassa.scontrini set stato = 'annullato', errore = coalesce(errore,'') || ' | tentativo scartato' where id = s.id;
  update cassa.righe set scontrino_id = null where scontrino_id = s.id;
  perform cassa.registra(o.id, 'tentativo_scartato', 'scontrino', s.id::text, to_jsonb(s), jsonb_build_object('motivo', a->>'motivo'));
  return jsonb_build_object('ok', true, 'conto', cassa.conto_json(s.conto_id));
end $$;
create or replace function cassa.totali_giornata(p_g date) returns jsonb language sql stable set search_path = cassa, pg_temp as $$
  with v as (select s.* from cassa.scontrini s where s.giornata = p_g and s.tipo = 'vendita' and s.stato in ('emesso','annullato') and s.numero_rt is not null),
       an as (select s.riferimento_id from cassa.scontrini s where s.giornata = p_g and s.tipo = 'annullo' and s.stato = 'emesso'),
       segno as (select v.id, case when v.id in (select riferimento_id from an) then 0 else 1 end k from v),
       pag as (select p.metodo, sum((p.importo_cent - p.resto_cent) * sg.k) netto from cassa.pagamenti p join segno sg on sg.id = p.scontrino_id group by 1),
       rep as (select r.reparto_id, r.iva, sum(cassa.importo_riga(r) * sg.k) tot from cassa.righe r join segno sg on sg.id = r.scontrino_id group by 1,2)
  select jsonb_build_object(
    'totale_cent', coalesce((select sum(totale_cent * k) from v join segno using (id)), 0),
    'scontrini', (select count(*) from v), 'annulli', (select count(*) from an),
    'contanti_cent', coalesce((select netto from pag where metodo = 'contanti'), 0),
    'elettronico_cent', coalesce((select netto from pag where metodo = 'carta'), 0),
    'per_reparto', coalesce((select jsonb_agg(jsonb_build_object('reparto', reparto_id, 'iva', iva, 'totale_cent', tot)) from rep), '[]'::jsonb),
    'senza_documento', coalesce((select jsonb_agg(jsonb_build_object('causale', causale, 'totale_cent', t)) from
        (select causale, sum(totale_cent) t from cassa.scontrini where giornata = p_g and tipo = 'senza_documento' group by 1) x), '[]'::jsonb)) $$;
create or replace function cassa.op_chiusura(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare g date := cassa.giornata(); t jsonb; ch uuid; v_aperti int; v_contati int := nullif(a->>'contanti_contati_cent','')::int;
begin
  perform cassa.richiedi(o.ruolo, 'cassiere');
  select count(*) into v_aperti from cassa.conti where stato = 'aperto' and exists (select 1 from cassa.righe r where r.conto_id = conti.id and cassa.riga_da_pagare(r));
  if v_aperti > 0 and not coalesce((a->>'forza')::boolean, false) then
    raise exception 'CONTI_APERTI: ci sono % conti aperti con righe da pagare', v_aperti;
  end if;
  if exists (select 1 from cassa.scontrini where stato in ('in_coda','errore') and giornata = g) then
    raise exception 'SCONTRINI_SOSPESI: ci sono scontrini in coda o in errore, risolvili prima';
  end if;
  if exists (select 1 from cassa.chiusure where giornata = g and stato in ('in_coda','fatta')) and not coalesce((a->>'forza')::boolean, false) then
    raise exception 'GIA_CHIUSA: la giornata ha gia una chiusura';
  end if;
  t := cassa.totali_giornata(g);
  insert into cassa.chiusure (giornata, totale_cassa_cent, contanti_teorici_cent, elettronico_cent, contanti_contati_cent, differenza_cent, totali, operatore_id)
  values (g, (t->>'totale_cent')::int, (t->>'contanti_cent')::int, (t->>'elettronico_cent')::int, v_contati,
          case when v_contati is not null then v_contati - (t->>'contanti_cent')::int end, t, o.id) returning id into ch;
  perform cassa.accoda('chiusura', 'fiscale', ch, jsonb_build_object('operatore_rt', o.operatore_rt));
  perform cassa.registra(o.id, 'chiusura_richiesta', 'chiusura', ch::text, null, t);
  return jsonb_build_object('chiusura', ch, 'totali', t, 'differenza_cent', case when v_contati is not null then v_contati - (t->>'contanti_cent')::int end);
end $$;
create or replace function cassa.op_cassetto(o cassa.operatori, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
begin
  perform cassa.richiedi(o.ruolo, 'cassiere');
  if coalesce(a->>'motivo','') = '' then raise exception 'MOTIVO: indica perche apri il cassetto'; end if;
  perform cassa.accoda('configura', 'fiscale', null, jsonb_build_object('azione', 'cassetto', 'operatore_rt', o.operatore_rt));
  perform cassa.registra(o.id, 'apertura_cassetto', 'cassetto', null, null, jsonb_build_object('motivo', a->>'motivo'));
  return jsonb_build_object('ok', true);
end $$;
create or replace function cassa.op_scontrini(o cassa.operatori, a jsonb) returns jsonb language sql stable set search_path = cassa, pg_temp as $$
  select coalesce(jsonb_agg(jsonb_build_object('id', s.id, 'tipo', s.tipo, 'stato', s.stato, 'causale', s.causale,
      'numero', case when s.numero_rt is not null then lpad(s.z_numero::text,4,'0') || '-' || lpad(s.numero_rt::text,4,'0') end,
      'totale_cent', s.totale_cent, 'ora', to_char(s.creato_il at time zone 'Europe/Rome','HH24:MI'), 'errore', s.errore,
      'tavolo', c.tavolo_id, 'operatore', op.nome) order by s.creato_il desc), '[]'::jsonb)
  from cassa.scontrini s left join cassa.conti c on c.id = s.conto_id left join cassa.operatori op on op.id = s.operatore_id
  where s.giornata = coalesce((a->>'giornata')::date, cassa.giornata()) $$;
create or replace function cassa.op_chiusure(o cassa.operatori, a jsonb) returns jsonb language sql stable set search_path = cassa, pg_temp as $$
  select coalesce(jsonb_agg(to_jsonb(ch) - 'operatore_id' order by ch.creata_il desc), '[]'::jsonb)
  from (select * from cassa.chiusure order by creata_il desc limit 30) ch $$;
create or replace function cassa.op_admin(o cassa.operatori, p_azione text, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare v_id uuid;
begin
  perform cassa.richiedi(o.ruolo, 'admin');
  if p_azione = 'operatori' then
    return (select coalesce(jsonb_agg(jsonb_build_object('id', id, 'nome', nome, 'ruolo', ruolo, 'attivo', attivo) order by nome), '[]'::jsonb) from cassa.operatori);
  elsif p_azione = 'operatore_salva' then
    if a ? 'id' then
      update cassa.operatori set nome = coalesce(a->>'nome', nome), ruolo = coalesce(a->>'ruolo', ruolo),
             attivo = coalesce((a->>'attivo')::boolean, attivo),
             pin_hash = case when coalesce(a->>'pin','') <> '' then extensions.crypt(a->>'pin', extensions.gen_salt('bf')) else pin_hash end
       where id = (a->>'id')::uuid returning id into v_id;
    else
      if length(coalesce(a->>'pin','')) < 4 then raise exception 'DATI: PIN di almeno 4 cifre'; end if;
      insert into cassa.operatori (nome, pin_hash, ruolo) values (a->>'nome', extensions.crypt(a->>'pin', extensions.gen_salt('bf')), a->>'ruolo') returning id into v_id;
    end if;
    if exists (select 1 from cassa.operatori x where x.id <> v_id and x.pin_hash = extensions.crypt(coalesce(a->>'pin',''), x.pin_hash)) then
      raise exception 'DATI: PIN gia usato da un altro operatore';
    end if;
    perform cassa.registra(o.id, 'operatore_salvato', 'operatore', v_id::text, null, a - 'pin');
    return jsonb_build_object('id', v_id);
  elsif p_azione = 'prezzo_salva' then
    insert into cassa.prezzi (product_id, listino_id, prezzo_cent, origine) values ((a->>'prodotto')::int, a->>'listino', (a->>'prezzo_cent')::int, 'manuale')
    on conflict (product_id, listino_id) do update set prezzo_cent = excluded.prezzo_cent, origine = 'manuale', aggiornato_il = now();
    perform cassa.registra(o.id, 'prezzo_salvato', 'prodotto', a->>'prodotto', null, a);
    return jsonb_build_object('ok', true);
  elsif p_azione = 'config_salva' then
    if a->>'k' not in ('rt_matricola','ora_cambio_giornata','soglia_sconto_cassiere_cent','stampante_comande_default','stampante_preconto_banco') then raise exception 'DATI: chiave non modificabile'; end if;
    update cassa.config set v = a->>'v' where k = a->>'k';
    perform cassa.registra(o.id, 'config', 'config', a->>'k', null, a);
    return jsonb_build_object('ok', true);
  elsif p_azione = 'stampante_salva' then
    update cassa.stampanti set ip = coalesce(a->>'ip', ip) where id = a->>'id';
    return jsonb_build_object('ok', true);
  elsif p_azione = 'coda' then
    return (select coalesce(jsonb_agg(to_jsonb(q) order by q.id desc), '[]'::jsonb) from (select * from cassa.coda order by id desc limit 50) q);
  end if;
  raise exception 'AZIONE_SCONOSCIUTA: %', p_azione;
end $$;
create or replace function cassa.api(p_azione text, p_tok uuid, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare o cassa.operatori;
begin
  a := coalesce(a, '{}'::jsonb);
  if p_azione = 'login' then return cassa.op_login(a); end if;
  o := cassa.operatore(p_tok);
  case p_azione
    when 'logout' then delete from cassa.sessioni where token = p_tok; return jsonb_build_object('ok', true);
    when 'catalogo' then return cassa.op_catalogo(o, a);
    when 'stato' then return cassa.op_stato(o, a);
    when 'apri' then return cassa.op_apri(o, a);
    when 'conto' then return cassa.conto_json((a->>'conto')::uuid);
    when 'aggiungi' then return cassa.op_aggiungi(o, a);
    when 'quantita' then return cassa.op_quantita(o, a);
    when 'togli' then return cassa.op_togli(o, a);
    when 'sconto' then return cassa.op_sconto(o, a);
    when 'cambia_prezzo' then return cassa.op_cambia_prezzo(o, a);
    when 'comanda' then return cassa.op_comanda(o, a);
    when 'preconto' then return cassa.op_preconto(o, a);
    when 'paga' then return cassa.op_paga(o, a);
    when 'senza_documento' then return cassa.op_senza_documento(o, a);
    when 'annulla' then return cassa.op_annulla(o, a);
    when 'riprova' then return cassa.op_riprova(o, a);
    when 'sblocca' then return cassa.op_sblocca(o, a);
    when 'chiusura' then return cassa.op_chiusura(o, a);
    when 'cassetto' then return cassa.op_cassetto(o, a);
    when 'scontrini' then return cassa.op_scontrini(o, a);
    when 'chiusure' then return cassa.op_chiusure(o, a);
    when 'totali' then return cassa.totali_giornata(coalesce((a->>'giornata')::date, cassa.giornata()));
    else return cassa.op_admin(o, p_azione, a);
  end case;
end $$;
create or replace function cassa.ponte(p_token text, p_azione text, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare j cassa.coda; v_ok boolean; d jsonb; s cassa.scontrini;
begin
  if p_token is null or p_token <> cassa.cfg('ponte_token') then raise exception 'PONTE_NON_AUTORIZZATO'; end if;
  a := coalesce(a, '{}'::jsonb);
  if p_azione = 'stampanti' then
    return (select jsonb_agg(to_jsonb(st)) from cassa.stampanti st where attiva);
  elsif p_azione = 'prendi' then
    return (with presi as (
      update cassa.coda set stato = 'presa', preso_il = now(), tentativi = tentativi + 1
       where id in (select id from cassa.coda where stato = 'in_attesa'
                      or (stato = 'presa' and preso_il < now() - interval '2 minutes' and tipo in ('comanda','preconto','configura'))
                    order by id limit coalesce((a->>'n')::int, 10) for update skip locked)
      returning *)
      select coalesce(jsonb_agg(jsonb_build_object('id', p.id, 'tipo', p.tipo, 'payload', p.payload,
               'stampante', jsonb_build_object('id', st.id, 'tipo', st.tipo, 'devid', st.devid, 'ip', st.ip)) order by p.id), '[]'::jsonb)
        from presi p left join cassa.stampanti st on st.id = p.stampante_id);
  elsif p_azione = 'esito' then
    v_ok := coalesce((a->>'ok')::boolean, false); d := coalesce(a->'dati', '{}'::jsonb);
    update cassa.coda set stato = case when v_ok then 'fatta' else 'errore' end, esito = d, chiuso_il = now()
     where id = (a->>'id')::bigint and stato = 'presa' returning * into j;
    if not found then raise exception 'DATI: lavoro non trovato o non preso'; end if;
    if j.tipo in ('fiscale','annullo') then
      select * into s from cassa.scontrini where id = j.rif_id for update;
      if v_ok then
        update cassa.scontrini set stato = 'emesso', numero_rt = (d->>'numero')::int, z_numero = (d->>'z')::int,
               data_rt = d->>'data', emesso_il = now() where id = s.id;
        if j.tipo = 'fiscale' then
          insert into cassa.movimenti (product_id, quantita, causale, scontrino_id)
            select r.product_id, -r.quantita, 'vendita', s.id from cassa.righe r where r.scontrino_id = s.id and r.product_id is not null;
          perform cassa.chiudi_se_finito(s.conto_id);
        else
          update cassa.scontrini set stato = 'annullato' where id = s.riferimento_id;
          insert into cassa.movimenti (product_id, quantita, causale, scontrino_id)
            select r.product_id, r.quantita, 'annullo', s.id from cassa.righe r where r.scontrino_id = s.riferimento_id and r.product_id is not null;
        end if;
      else
        update cassa.scontrini set stato = 'errore', errore = coalesce(d->>'errore', 'errore stampante') where id = s.id;
      end if;
    elsif j.tipo = 'chiusura' then
      update cassa.chiusure set stato = case when v_ok then 'fatta' else 'errore' end,
             z_numero = (d->>'z')::int, totale_rt_cent = (d->>'totale_cent')::int, errore = d->>'errore' where id = j.rif_id;
    end if;
    return jsonb_build_object('ok', true);
  end if;
  raise exception 'AZIONE_SCONOSCIUTA: %', p_azione;
end $$;
revoke all on all functions in schema cassa from public, anon, authenticated;
revoke usage on schema cassa from public, anon, authenticated;
