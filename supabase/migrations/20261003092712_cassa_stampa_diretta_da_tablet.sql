-- Struttura recuperata dal registro Supabase (20261003092712) il 08/10/2026.
-- Escluse copie di prodotti, instradamenti/stampanti legacy e orari applicativi.
-- Conservate soltanto configurazioni strutturali; nessun dato operativo storico.
create or replace function cassa.esito_lavoro(p_id bigint, v_ok boolean, d jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare j cassa.coda; s cassa.scontrini;
begin
  d := coalesce(d, '{}'::jsonb);
  update cassa.coda set stato = case when v_ok then 'fatta' else 'errore' end, esito = d, chiuso_il = now()
   where id = p_id and stato in ('presa','in_attesa') returning * into j;
  if not found then return jsonb_build_object('ok', false, 'motivo', 'lavoro gia chiuso'); end if;
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
end $$;
create or replace function cassa.lavori_json(p_ids bigint[]) returns jsonb language sql stable set search_path = cassa, pg_temp as $$
  select coalesce(jsonb_agg(jsonb_build_object('id', q.id, 'tipo', q.tipo, 'payload', q.payload,
           'stampante', jsonb_build_object('id', st.id, 'tipo', st.tipo, 'devid', st.devid)) order by q.id), '[]'::jsonb)
    from cassa.coda q left join cassa.stampanti st on st.id = q.stampante_id where q.id = any(p_ids) $$;
create or replace function cassa.api(p_azione text, p_tok uuid, a jsonb) returns jsonb language plpgsql set search_path = cassa, pg_temp as $$
declare o cassa.operatori; v_max bigint; r jsonb; ids bigint[];
begin
  a := coalesce(a, '{}'::jsonb);
  if p_azione = 'login' then return cassa.op_login(a); end if;
  o := cassa.operatore(p_tok);
  if p_azione = 'esito' then
    return cassa.esito_lavoro((a->>'id')::bigint, coalesce((a->>'ok')::boolean, false), a->'dati');
  elsif p_azione = 'lavori_pendenti' then
    select array_agg(id) into ids from cassa.coda where stato in ('in_attesa','presa') and creato_il > now() - interval '1 day';
    return jsonb_build_object('lavori', cassa.lavori_json(ids));
  end if;
  select coalesce(max(id), 0) into v_max from cassa.coda;
  case p_azione
    when 'logout' then delete from cassa.sessioni where token = p_tok; r := jsonb_build_object('ok', true);
    when 'catalogo' then r := cassa.op_catalogo(o, a);
    when 'stato' then r := cassa.op_stato(o, a);
    when 'apri' then r := cassa.op_apri(o, a);
    when 'conto' then r := cassa.conto_json((a->>'conto')::uuid);
    when 'aggiungi' then r := cassa.op_aggiungi(o, a);
    when 'quantita' then r := cassa.op_quantita(o, a);
    when 'togli' then r := cassa.op_togli(o, a);
    when 'sconto' then r := cassa.op_sconto(o, a);
    when 'cambia_prezzo' then r := cassa.op_cambia_prezzo(o, a);
    when 'comanda' then r := cassa.op_comanda(o, a);
    when 'preconto' then r := cassa.op_preconto(o, a);
    when 'paga' then r := cassa.op_paga(o, a);
    when 'senza_documento' then r := cassa.op_senza_documento(o, a);
    when 'annulla' then r := cassa.op_annulla(o, a);
    when 'riprova' then r := cassa.op_riprova(o, a);
    when 'sblocca' then r := cassa.op_sblocca(o, a);
    when 'chiusura' then r := cassa.op_chiusura(o, a);
    when 'cassetto' then r := cassa.op_cassetto(o, a);
    when 'scontrini' then r := cassa.op_scontrini(o, a);
    when 'chiusure' then r := cassa.op_chiusure(o, a);
    when 'totali' then r := cassa.totali_giornata(coalesce((a->>'giornata')::date, cassa.giornata()));
    else r := cassa.op_admin(o, p_azione, a);
  end case;
  update cassa.coda set stato = 'presa', preso_il = now() where id > v_max and stato = 'in_attesa' returning id into ids;
  select array_agg(id) into ids from cassa.coda where id > v_max;
  if ids is not null then
    update cassa.coda set stato = 'presa', preso_il = now() where id = any(ids) and stato = 'in_attesa';
    r := coalesce(r, '{}'::jsonb) || jsonb_build_object('lavori', cassa.lavori_json(ids));
  end if;
  return r;
end $$;
revoke all on all functions in schema cassa from public, anon, authenticated;
