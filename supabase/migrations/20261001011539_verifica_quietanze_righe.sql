create or replace view verifica.quietanze_righe with (security_invoker = on) as
with q as (
  select distinct on (coalesce(nullif(regexp_replace(coalesce(d.data->>'protocollo_telematico',''),'\D','','g'),''), d.id),
                      d.data->'totali'->>'saldo_delega_cents')
    d.id, d.data, (d.data->>'data_pagamento')::date dp, d.data->>'protocollo_telematico' prot
  from gestionale.documents d
  where d.collection = 'quietanze_f24'
    and coalesce(nullif(d.data->>'codice_fiscale',''), nullif(d.data->'dati_generali'->>'codice_fiscale',''), '04523831214') = '04523831214'
    and d.data->>'data_pagamento' ~ '^\d{4}-\d{2}-\d{2}'
  order by coalesce(nullif(regexp_replace(coalesce(d.data->>'protocollo_telematico',''),'\D','','g'),''), d.id),
           d.data->'totali'->>'saldo_delega_cents', d.created_at
)
select q.id quietanza_id, q.dp data_pagamento, q.prot protocollo, s.sezione,
  case s.sezione when 'INPS' then coalesce(r->>'causale', r->>'codice_tributo')
                 when 'INAIL' then 'INAIL'
                 else r->>'codice_tributo' end codice,
  coalesce(r->>'codice_regione', r->>'codice_comune', r->>'codice_sede', r->>'codice_ufficio') ente,
  r->>'periodo_riferimento' periodo, r->>'periodo_raw' periodo_raw, r->>'descrizione' descrizione,
  coalesce((r->>'importo_debito_cents')::bigint,0) debito_cents, coalesce((r->>'importo_credito_cents')::bigint,0) credito_cents
from q
cross join lateral (values ('Erario','sezione_erario'),('INPS','sezione_inps'),('Regioni','sezione_regioni'),
                           ('Tributi locali','sezione_tributi_locali'),('INAIL','sezione_inail')) s(sezione, chiave)
cross join lateral jsonb_array_elements(coalesce(q.data->s.chiave,'[]')) r;

