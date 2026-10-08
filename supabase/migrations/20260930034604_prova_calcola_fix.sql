
create or replace function gestionale.prova_calcola(
  p_pdf_b64 text, p_md5 text, p_prova jsonb, p_pagina_da int, p_pagina_a int,
  p_valore text, p_valore_sospetto boolean, p_motivo_sospetto text)
returns jsonb language plpgsql stable as $$
declare
  v_md5 text := p_md5;
  d_id text; d_nome text; d_perc text;
  v_testo text := nullif(p_prova->>'testo_letto','');
  v_pag_da int := coalesce(p_pagina_da, nullif(p_prova->>'pagina_da','')::int);
  v_pag_a int := coalesce(p_pagina_a, nullif(p_prova->>'pagina_a','')::int, p_pagina_da);
  v_motivi text[] := '{}';
  v_stato text; v_num numeric; v_it text; v_pt text;
begin
  if v_md5 is null and p_pdf_b64 is not null and length(p_pdf_b64) > 100 then
    begin v_md5 := md5(decode(p_pdf_b64,'base64')); exception when others then v_md5 := null; end;
  end if;
  if v_md5 is not null then
    select drive_id, nome, percorso into d_id, d_nome, d_perc from gestionale.protocollo_drive
     where md5 = v_md5 and rimosso_il is null order by modificato_drive desc nulls last limit 1;
  end if;
  if d_id is null and nullif(p_prova->>'drive_id','') is not null then
    select drive_id, nome, percorso into d_id, d_nome, d_perc from gestionale.protocollo_drive
     where drive_id = p_prova->>'drive_id' and rimosso_il is null limit 1;
  end if;

  if d_id is null then v_motivi := v_motivi || 'nessun file Drive con la stessa impronta'::text; end if;
  if v_pag_da is null then v_motivi := v_motivi || 'pagina non registrata'::text; end if;
  if v_testo is null then v_motivi := v_motivi || 'testo letto assente'::text; end if;
  if p_valore_sospetto then v_motivi := v_motivi || coalesce(p_motivo_sospetto,'valore non letto dal documento'); end if;

  if v_testo is not null and p_valore is not null then
    begin v_num := p_valore::numeric; exception when others then v_num := null; end;
    if v_num is not null then
      v_pt := to_char(v_num,'FM9999990.00');
      v_it := replace(v_pt,'.',',');
      if position(v_it in v_testo) = 0 and position(v_pt in v_testo) = 0
         and position(regexp_replace(v_it,'(\d)(\d{3}),', '\1.\2,') in v_testo) = 0 then
        v_motivi := v_motivi || 'il valore non compare nel testo letto'::text;
        p_valore_sospetto := true;
      end if;
    end if;
  end if;

  v_stato := case
    when d_id is null then 'senza_origine'
    when p_valore_sospetto then 'valore_non_letto'
    when v_testo is null or v_pag_da is null then 'da_rileggere'
    else 'completa' end;

  return jsonb_strip_nulls(jsonb_build_object(
    'stato', v_stato, 'drive_id', d_id, 'drive_nome', d_nome, 'drive_percorso', d_perc,
    'impronta_md5', v_md5, 'pagina_da', v_pag_da, 'pagina_a', v_pag_a,
    'testo_letto', v_testo, 'lettore', p_prova->>'lettore', 'letto_il', p_prova->>'letto_il',
    'motivi', to_jsonb(v_motivi), 'verificato_il', now()));
end $$;

