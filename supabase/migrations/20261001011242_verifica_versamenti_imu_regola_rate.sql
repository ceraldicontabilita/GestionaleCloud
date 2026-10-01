create or replace view verifica.versamenti_tributi with (security_invoker = on) as
with q as (
  select distinct on (coalesce(nullif(regexp_replace(coalesce(d.data->>'protocollo_telematico',''),'\D','','g'),''), d.id),
                      d.data->'totali'->>'saldo_delega_cents')
    d.id, d.data, (d.data->>'data_pagamento')::date dp, d.data->>'protocollo_telematico' prot
  from gestionale.documents d
  where d.collection = 'quietanze_f24'
    and coalesce(d.data->>'codice_fiscale', d.data->'dati_generali'->>'codice_fiscale', '04523831214') = '04523831214'
    and d.data->>'data_pagamento' ~ '^\d{4}-\d{2}-\d{2}'
  order by coalesce(nullif(regexp_replace(coalesce(d.data->>'protocollo_telematico',''),'\D','','g'),''), d.id),
           d.data->'totali'->>'saldo_delega_cents', d.created_at
),
q_rows as (
  select distinct q.id qid, q.dp, q.prot, 'Erario'::text gruppo, r->>'codice_tributo' cod,
         r->>'periodo_riferimento' per, (r->>'importo_debito_cents')::bigint cents
  from q, jsonb_array_elements(coalesce(q.data->'sezione_erario','[]')) r
  where r->>'codice_tributo' in ('1001','1012') and coalesce((r->>'importo_debito_cents')::bigint,0) > 0
    and r->>'periodo_riferimento' ~ '^\d{2}/\d{4}$'
  union
  select distinct q.id, q.dp, q.prot, 'IMU', r->>'codice_tributo',
         right(coalesce(r->>'periodo_riferimento', r->>'periodo_raw', ''), 4), (r->>'importo_debito_cents')::bigint
  from q, jsonb_array_elements(coalesce(q.data->'sezione_tributi_locali','[]') || coalesce(q.data->'sezione_imu','[]')) r
  where r->>'codice_tributo' in ('3918','3930','3925','3916','3914','3912') and coalesce((r->>'importo_debito_cents')::bigint,0) > 0
),
f as (
  select d.id, d.data from gestionale.documents d
  where d.collection = 'f24_unificato'
    and coalesce(d.data->>'motivo_quarantena','') = '' and d.data->>'doppione_di' is null and d.data->>'superato_da' is null
),
f_rows as (
  select distinct f.id fid, 'Erario'::text gruppo, r->>'codice_tributo' cod, r->>'periodo_riferimento' per, (r->>'importo_debito_cents')::bigint cents
  from f, jsonb_array_elements(coalesce(f.data->'sezione_erario','[]')) r
  where r->>'codice_tributo' in ('1001','1012') and r->>'periodo_riferimento' ~ '^\d{2}/\d{4}$'
  union
  select distinct f.id, 'IMU', r->>'codice_tributo', coalesce(r->>'anno', right(r->>'periodo_riferimento',4)), (r->>'importo_debito_cents')::bigint
  from f, jsonb_array_elements(coalesce(f.data->'sezione_tributi_locali','[]') || coalesce(f.data->'sezione_imu','[]')) r
  where r->>'codice_tributo' in ('3918','3930','3925','3916','3914','3912') and coalesce(r->>'anno', right(r->>'periodo_riferimento',4)) ~ '^\d{4}$'
),
er_keys as (
  select '1001'::text cod, to_char(m, 'MM/YYYY') per
  from generate_series(
         (select min(to_date(per,'MM/YYYY')) from (select per from q_rows where cod='1001' union all select per from f_rows where cod='1001') z),
         date_trunc('month', current_date) - interval '1 month', interval '1 month') m
  union select cod, per from q_rows where gruppo='Erario'
  union select cod, per from f_rows where gruppo='Erario'
),
er as (
  select 'Ritenute'::text sezione, k.cod codice, right(k.per,4)::int anno, k.per periodo,
         (to_date(k.per,'MM/YYYY') + interval '1 month' + interval '15 days')::date scadenza,
         (select sum(cents) from q_rows x where x.cod=k.cod and x.per=k.per) pagato_cents,
         (select string_agg(distinct to_char(dp,'DD/MM/YYYY'), ', ') from q_rows x where x.cod=k.cod and x.per=k.per) date_pagamento,
         (select string_agg(distinct prot, ', ') from q_rows x where x.cod=k.cod and x.per=k.per) protocolli,
         exists(select 1 from q_rows x where x.cod=k.cod and x.per=k.per) ha_quietanza,
         exists(select 1 from f_rows y where y.cod=k.cod and y.per=k.per) ha_f24,
         null::text nota
  from er_keys k
),
imu_anni as (
  select generate_series(
           (select min(anno::int) from (select per anno from q_rows where gruppo='IMU' union all select per from f_rows where gruppo='IMU') z),
           extract(year from current_date)::int) anno
),
imu_pag as (
  select a.anno,
    count(distinct x.qid) n_tot,
    count(distinct x.qid) filter (where extract(year from x.dp)=a.anno and extract(month from x.dp)<=8) n_giugno,
    count(distinct x.qid) filter (where extract(year from x.dp)=a.anno and extract(month from x.dp)>=9) n_dicembre,
    count(distinct x.qid) filter (where extract(year from x.dp)>a.anno) n_tardivi,
    sum(x.cents) tot_cents,
    string_agg(distinct to_char(x.dp,'DD/MM/YYYY'), ', ') date_pagamento,
    string_agg(distinct x.prot, ', ') protocolli,
    (select count(distinct fid) from f_rows y where y.gruppo='IMU' and y.per=a.anno::text) n_f24
  from imu_anni a left join q_rows x on x.gruppo='IMU' and x.per=a.anno::text
  group by a.anno
),
imu as (
  select 'IMU'::text sezione, '3918'::text codice, p.anno, r.rata periodo,
         make_date(p.anno, case r.rata when 'acconto' then 6 else 12 end, 16) scadenza,
         p.tot_cents pagato_cents, p.date_pagamento, p.protocolli,
         case r.rata when 'acconto' then p.n_tot >= 1 else p.n_tot >= 2 end ha_quietanza,
         case r.rata when 'acconto' then p.n_f24 >= 1 else p.n_f24 >= 2 end ha_f24,
         nullif(concat_ws('; ',
           case when r.rata='saldo' and p.n_dicembre = 0 and p.n_giugno >= 2 then 'saldo versato insieme all''acconto a giugno' end,
           case when p.n_tardivi > 0 then 'versamenti fatti negli anni successivi (ravvedimento o arretrato)' end,
           case when p.n_tot = 1 then 'un solo versamento trovato per l''anno: copre l''acconto, il saldo risulta scoperto' end
         ), '') nota
  from imu_pag p cross join (values ('acconto'),('saldo')) r(rata)
),
tutto as (select * from er union all select * from imu)
select sezione, codice, anno, periodo, scadenza,
  case
    when scadenza > current_date and not ha_quietanza then 'NON_SCADUTO'
    when ha_quietanza and ha_f24 then 'PAGATO'
    when ha_quietanza then 'PAGATO_SOLO_QUIETANZA'
    when ha_f24 then 'F24_SENZA_QUIETANZA'
    else 'MANCANTE'
  end stato,
  case
    when scadenza > current_date and not ha_quietanza then 'Non ancora scaduto'
    when ha_quietanza and ha_f24 then 'Pagato: F24 e quietanza presenti'
    when ha_quietanza then codice || ' pagata: F24 originale non trovato, ma la quietanza certifica il pagamento'
    when ha_f24 then 'F24 presente ma nessuna quietanza: pagamento NON certificato'
    else 'VERSAMENTO NON TROVATO: né F24 né quietanza'
  end etichetta,
  round(pagato_cents/100.0, 2) pagato, date_pagamento, protocolli, ha_quietanza, ha_f24, nota
from tutto;

