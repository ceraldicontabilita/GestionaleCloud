
-- Regola: ogni dato porta la prova (id file Drive, pagina, testo letto). Il netto si legge, non si calcola.
create or replace function gestionale.prova_calcola(
  p_pdf_b64 text, p_md5 text, p_prova jsonb, p_pagina_da int, p_pagina_a int,
  p_valore text, p_valore_sospetto boolean, p_motivo_sospetto text)
returns jsonb language plpgsql stable as $$
declare
  v_md5 text := p_md5;
  v_drive record;
  v_testo text := nullif(p_prova->>'testo_letto','');
  v_motivi text[] := '{}';
  v_stato text;
  v_val_it text; v_val_pt text;
begin
  if v_md5 is null and p_pdf_b64 is not null and length(p_pdf_b64) > 100 then
    begin v_md5 := md5(decode(p_pdf_b64,'base64')); exception when others then v_md5 := null; end;
  end if;
  if v_md5 is not null then
    select drive_id, nome, percorso into v_drive from gestionale.protocollo_drive
     where md5 = v_md5 and rimosso_il is null order by modificato_drive desc nulls last limit 1;
  end if;
  if v_drive.drive_id is null and nullif(p_prova->>'drive_id','') is not null then
    select drive_id, nome, percorso into v_drive from gestionale.protocollo_drive
     where drive_id = p_prova->>'drive_id' and rimosso_il is null;
  end if;

  if v_drive.drive_id is null then v_motivi := v_motivi || 'nessun file Drive con la stessa impronta'; end if;
  if coalesce(p_pagina_da, (p_prova->>'pagina_da')::int) is null then v_motivi := v_motivi || 'pagina non registrata'; end if;
  if v_testo is null then v_motivi := v_motivi || 'testo letto assente'; end if;
  if p_valore_sospetto then v_motivi := v_motivi || coalesce(p_motivo_sospetto,'valore non letto dal documento'); end if;
  if v_testo is not null and p_valore is not null then
    v_val_it := replace(replace(replace(to_char(p_valore::numeric,'FM999G999G990D00'),',','#'),'.',','),'#','.');
    v_val_pt := to_char(p_valore::numeric,'FM999990D00');
    if position(v_val_it in v_testo) = 0 and position(v_val_pt in v_testo) = 0
       and position(replace(v_val_it,'.','') in v_testo) = 0 then
      v_motivi := v_motivi || 'il valore non compare nel testo letto';
      p_valore_sospetto := true;
    end if;
  end if;

  v_stato := case
    when v_drive.drive_id is null then 'senza_origine'
    when p_valore_sospetto then 'valore_non_letto'
    when v_testo is null or coalesce(p_pagina_da, (p_prova->>'pagina_da')::int) is null then 'da_rileggere'
    else 'completa' end;

  return jsonb_strip_nulls(jsonb_build_object(
    'stato', v_stato,
    'drive_id', v_drive.drive_id,
    'drive_nome', v_drive.nome,
    'drive_percorso', v_drive.percorso,
    'impronta_md5', v_md5,
    'pagina_da', coalesce(p_pagina_da, (p_prova->>'pagina_da')::int),
    'pagina_a', coalesce(p_pagina_a, p_pagina_da, (p_prova->>'pagina_a')::int),
    'testo_letto', v_testo,
    'lettore', p_prova->>'lettore',
    'letto_il', p_prova->>'letto_il',
    'motivi', to_jsonb(v_motivi),
    'verificato_il', now()));
end $$;

-- Cedolini dell'app HR
create or replace function hr.prova_cedolino_trg() returns trigger language plpgsql as $$
declare v_sosp boolean; v_mot text;
begin
  v_sosp := (new.doc->>'netto') is null
    or new.doc->>'netto_riverifica_esito' in ('non_ritrovata','netto_non_verificato','confermato_con_acconto')
    or new.doc->>'netto_fonte' = 'nome_file_riconciliato'
    or (new.doc->>'netto_ricostruito' = 'true' and coalesce(new.doc->>'netto_fonte','') not like 'riverifica_pdf%');
  v_mot := case
    when (new.doc->>'netto') is null then 'netto assente'
    when new.doc->>'netto_fonte' = 'nome_file_riconciliato' then 'netto preso dal nome del file'
    when new.doc->>'netto_riverifica_esito' = 'confermato_con_acconto' then 'netto rettificato con acconto'
    when new.doc->>'netto_ricostruito' = 'true' and coalesce(new.doc->>'netto_fonte','') not like 'riverifica_pdf%' then 'netto ricostruito (calcolato)'
    else 'netto non ritrovato nel PDF' end;
  new.doc := new.doc || jsonb_build_object('prova', gestionale.prova_calcola(
    new.doc->>'pdf_data', null,
    coalesce(new.doc->'prova', case when tg_op='UPDATE' then old.doc->'prova' end, '{}'::jsonb),
    null, null, new.doc->>'netto', v_sosp, v_mot));
  return new;
end $$;

-- Cedolini e quietanze del gestionale
create or replace function gestionale.prova_documento_trg() returns trigger language plpgsql as $$
declare v_prev jsonb;
begin
  v_prev := coalesce(new.data->'prova', case when tg_op='UPDATE' then old.data->'prova' end, '{}'::jsonb);
  if new.collection = 'cedolini' then
    new.data := new.data || jsonb_build_object('prova', gestionale.prova_calcola(
      new.data->>'pdf_data', nullif(new.data->>'source_file_hash_md5',''), v_prev,
      nullif(new.data->>'source_page_start','')::int, nullif(new.data->>'source_page_end','')::int,
      new.data->>'netto', (new.data->>'netto') is null, 'netto assente'));
  elsif new.collection = 'quietanze_f24' then
    new.data := new.data || jsonb_build_object('prova', gestionale.prova_calcola(
      null, coalesce(nullif(new.data->>'drive_md5',''), nullif(new.data->>'pdf_hash','')),
      v_prev || jsonb_strip_nulls(jsonb_build_object('drive_id', new.data->>'drive_file_id')),
      null, null, new.data->>'saldo', false, null));
  end if;
  return new;
end $$;

