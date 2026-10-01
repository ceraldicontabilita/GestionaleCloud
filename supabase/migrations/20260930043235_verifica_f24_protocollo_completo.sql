drop view if exists verifica.riepilogo;
drop view if exists verifica.quietanze_f24;

create view verifica.quietanze_f24 with (security_invoker = on) as
with b as (
  select d.id, d.data dd,
    d.data->>'protocollo_telematico' protocollo,
    regexp_replace(coalesce(d.data->>'protocollo_telematico',''),'\D','','g') prot,
    d.data->>'codice_fiscale' cf,
    d.data->>'data_pagamento' data_pagamento,
    d.data->>'filename' file,
    d.data->>'drive_file_id' drive_id,
    (d.data->'totali'->>'saldo_delega_cents')::bigint saldo_cents
  from gestionale.documents d where d.collection='quietanze_f24'
), r as (
  select b.id, count(x.r) righe,
    coalesce(sum(coalesce((x.r->>'importo_debito_cents')::bigint,0) - coalesce((x.r->>'importo_credito_cents')::bigint,0)),0) netto_righe_cents
  from b left join lateral (
    select jsonb_array_elements(coalesce(b.dd->'sezione_erario','[]')) r union all
    select jsonb_array_elements(coalesce(b.dd->'sezione_inps','[]')) union all
    select jsonb_array_elements(coalesce(b.dd->'sezione_regioni','[]')) union all
    select jsonb_array_elements(coalesce(b.dd->'sezione_tributi_locali','[]')) union all
    select jsonb_array_elements(coalesce(b.dd->'sezione_inail','[]'))
  ) x on true group by b.id
), g as (
  select b.id, b.protocollo, b.prot, b.cf, b.data_pagamento, b.file, b.drive_id, b.saldo_cents, r.righe, r.netto_righe_cents,
    b.prot ~ '^\d{17}(\d{6})?$' prot_ok,
    count(*) over w copie,
    row_number() over (partition by b.prot order by b.id) n_copia,
    (min(coalesce(b.saldo_cents,-1)) over w <> max(coalesce(b.saldo_cents,-1)) over w) copie_diverse
  from b join r using (id)
  window w as (partition by b.prot)
)
select id, protocollo, cf, data_pagamento, file, drive_id,
  round(saldo_cents/100.0,2) saldo, round(netto_righe_cents/100.0,2) somma_righe, righe, copie, n_copia,
  array_remove(array[
    case when righe = 0 then 'nessuna riga tributo letta' end,
    case when righe > 0 and netto_righe_cents <> coalesce(saldo_cents,-1) then 'somma righe diversa dal saldo delega' end,
    case when not prot_ok then 'protocollo telematico assente o malformato' end,
    case when not verifica.cf_valido(cf) then 'codice fiscale contribuente non valido' end,
    case when data_pagamento is null then 'data di pagamento assente' end,
    case when coalesce(drive_id,'')='' then 'senza file Drive di origine' end,
    case when copie_diverse and prot_ok then 'copie con saldi diversi' end
  ], null) motivi,
  case
    when n_copia > 1 and not copie_diverse and prot_ok then 'doppione'
    when righe > 0 and netto_righe_cents = saldo_cents and prot_ok
         and verifica.cf_valido(cf) and data_pagamento is not null
         and coalesce(drive_id,'')<>'' and not copie_diverse then 'verificato'
    else 'da_rivedere' end esito
from g;

create view verifica.riepilogo with (security_invoker = on) as
select 'cedolini' tipo, esito, count(*) n from verifica.cedolini group by esito
union all
select 'quietanze_f24', esito, count(*) from verifica.quietanze_f24 group by esito;

revoke all on all tables in schema verifica from anon, authenticated;

