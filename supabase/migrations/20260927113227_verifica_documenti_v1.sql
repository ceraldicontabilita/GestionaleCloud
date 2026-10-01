create schema if not exists verifica;
comment on schema verifica is 'Strato di verifica in sola lettura: ricalcola i controlli sui dati estratti dai documenti. Non scrive mai sui dati.';

create or replace function verifica.cf_valido(p text) returns boolean
language plpgsql immutable as $$
declare
  s text := upper(coalesce(trim(p),''));
  dispari int[] := array[1,0,5,7,9,13,15,17,19,21,2,4,18,20,11,3,6,8,12,14,16,10,22,25,24,23];
  tot int := 0; c char; v int; i int; d int;
begin
  if s ~ '^[0-9]{11}$' then
    for i in 1..10 loop
      d := substr(s,i,1)::int;
      if i % 2 = 0 then d := d*2; if d > 9 then d := d-9; end if; end if;
      tot := tot + d;
    end loop;
    return (10 - tot % 10) % 10 = substr(s,11,1)::int;
  end if;
  if s !~ '^[A-Z0-9]{15}[A-Z]$' then return false; end if;
  for i in 1..15 loop
    c := substr(s,i,1);
    v := case when c ~ '[0-9]' then ascii(c)-48 else ascii(c)-65 end;
    if i % 2 = 1 then tot := tot + dispari[v+1]; else tot := tot + v; end if;
  end loop;
  return chr(65 + tot % 26) = substr(s,16,1);
end $$;

create or replace view verifica.cedolini with (security_invoker = on) as
with b as (
  select d.id,
    d.data->>'codice_fiscale' cf,
    (d.data->>'anno')::int anno, (d.data->>'mese')::int mese,
    coalesce(d.data->>'tipo_cedolino','') tipo,
    d.data->>'nome_dipendente' dipendente,
    case when jsonb_typeof(d.data->'totale_competenze')='number' then (d.data->>'totale_competenze')::numeric end competenze,
    case when jsonb_typeof(d.data->'totale_trattenute')='number' then (d.data->>'totale_trattenute')::numeric end trattenute,
    case when jsonb_typeof(d.data->'netto')='number' then (d.data->>'netto')::numeric end netto,
    d.data->>'source_path' file_origine,
    (d.data->>'source_page_start')::int pagina
  from gestionale.documents d where d.collection='cedolini'
), g as (
  select b.*,
    count(*) over w copie,
    row_number() over (partition by cf, anno, mese, tipo order by id) n_copia,
    (min(coalesce(competenze,-1)) over w <> max(coalesce(competenze,-1)) over w
     or min(coalesce(trattenute,-1)) over w <> max(coalesce(trattenute,-1)) over w
     or min(coalesce(netto,-1)) over w <> max(coalesce(netto,-1)) over w) copie_diverse
  from b
  window w as (partition by cf, anno, mese, tipo)
)
select id, dipendente, cf, anno, mese, tipo, competenze, trattenute, netto,
  round(competenze - trattenute - netto, 2) differenza,
  file_origine, pagina, copie, n_copia,
  array_remove(array[
    case when not verifica.cf_valido(cf) then 'codice fiscale non valido' end,
    case when competenze is null or trattenute is null or netto is null then 'campi mancanti' end,
    case when abs(competenze - trattenute - netto) > 1 then 'competenze - trattenute diverso dal netto' end,
    case when netto <= 0 then 'netto zero o negativo' end,
    case when coalesce(file_origine,'')='' then 'senza file di origine' end,
    case when copie_diverse then 'copie con importi diversi' end
  ], null) motivi,
  case
    when n_copia > 1 and not copie_diverse then 'doppione'
    when verifica.cf_valido(cf) and competenze is not null and trattenute is not null and netto is not null
         and abs(competenze - trattenute - netto) <= 1 and netto > 0
         and coalesce(file_origine,'')<>'' and not copie_diverse then 'verificato'
    else 'da_rivedere' end esito
from g;

create or replace view verifica.quietanze_f24 with (security_invoker = on) as
with b as (
  select d.id, d.data dd,
    d.data->>'protocollo_telematico' protocollo,
    left(regexp_replace(coalesce(d.data->>'protocollo_telematico',''),'\D','','g'),17) prot17,
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
  select b.id, b.protocollo, b.prot17, b.cf, b.data_pagamento, b.file, b.drive_id, b.saldo_cents, r.righe, r.netto_righe_cents,
    count(*) over w copie,
    row_number() over (partition by b.prot17 order by b.id) n_copia,
    (min(coalesce(b.saldo_cents,-1)) over w <> max(coalesce(b.saldo_cents,-1)) over w) copie_diverse
  from b join r using (id)
  window w as (partition by b.prot17)
)
select id, protocollo, cf, data_pagamento, file, drive_id,
  round(saldo_cents/100.0,2) saldo, round(netto_righe_cents/100.0,2) somma_righe, righe, copie, n_copia,
  array_remove(array[
    case when righe = 0 then 'nessuna riga tributo letta' end,
    case when righe > 0 and netto_righe_cents <> coalesce(saldo_cents,-1) then 'somma righe diversa dal saldo delega' end,
    case when prot17 !~ '^\d{17}$' then 'protocollo telematico assente o malformato' end,
    case when not verifica.cf_valido(cf) then 'codice fiscale contribuente non valido' end,
    case when data_pagamento is null then 'data di pagamento assente' end,
    case when coalesce(drive_id,'')='' then 'senza file Drive di origine' end,
    case when copie_diverse and prot17 ~ '^\d{17}$' then 'copie con saldi diversi' end
  ], null) motivi,
  case
    when n_copia > 1 and not copie_diverse and prot17 ~ '^\d{17}$' then 'doppione'
    when righe > 0 and netto_righe_cents = saldo_cents and prot17 ~ '^\d{17}$'
         and verifica.cf_valido(cf) and data_pagamento is not null
         and coalesce(drive_id,'')<>'' and not copie_diverse then 'verificato'
    else 'da_rivedere' end esito
from g;

create or replace view verifica.riepilogo with (security_invoker = on) as
select 'cedolini' tipo, esito, count(*) n from verifica.cedolini group by esito
union all
select 'quietanze_f24', esito, count(*) from verifica.quietanze_f24 group by esito;

revoke all on schema verifica from anon, authenticated;

