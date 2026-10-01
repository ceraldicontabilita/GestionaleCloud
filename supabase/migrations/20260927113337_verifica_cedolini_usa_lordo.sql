drop view if exists verifica.riepilogo;
drop view if exists verifica.cedolini;

create view verifica.cedolini with (security_invoker = on) as
with b as (
  select d.id,
    d.data->>'codice_fiscale' cf,
    (d.data->>'anno')::int anno, (d.data->>'mese')::int mese,
    coalesce(d.data->>'tipo_cedolino','') tipo,
    d.data->>'nome_dipendente' dipendente,
    case when jsonb_typeof(d.data->'totale_competenze')='number' then (d.data->>'totale_competenze')::numeric end competenze,
    case when jsonb_typeof(d.data->'lordo')='number' then (d.data->>'lordo')::numeric end lordo,
    case when jsonb_typeof(d.data->'totale_trattenute')='number' then (d.data->>'totale_trattenute')::numeric end trattenute,
    case when jsonb_typeof(d.data->'netto')='number' then (d.data->>'netto')::numeric end netto,
    d.data->>'formato' formato,
    d.data->>'source_path' file_origine,
    (d.data->>'source_page_start')::int pagina
  from gestionale.documents d where d.collection='cedolini'
), b2 as (
  select b.*, coalesce(nullif(competenze,0), lordo) base from b
), g as (
  select b2.*,
    count(*) over w copie,
    row_number() over (partition by cf, anno, mese, tipo order by id) n_copia,
    (min(coalesce(base,-1)) over w <> max(coalesce(base,-1)) over w
     or min(coalesce(trattenute,-1)) over w <> max(coalesce(trattenute,-1)) over w
     or min(coalesce(netto,-1)) over w <> max(coalesce(netto,-1)) over w) copie_diverse
  from b2
  window w as (partition by cf, anno, mese, tipo)
)
select id, dipendente, cf, anno, mese, tipo, formato, competenze, lordo, trattenute, netto,
  round(base - trattenute - netto, 2) differenza,
  file_origine, pagina, copie, n_copia,
  array_remove(array[
    case when not verifica.cf_valido(cf) then 'codice fiscale non valido' end,
    case when base is null or trattenute is null or netto is null then 'campi mancanti' end,
    case when abs(base - trattenute - netto) > 1 then 'lordo - trattenute diverso dal netto' end,
    case when netto <= 0 then 'netto zero o negativo' end,
    case when coalesce(file_origine,'')='' then 'senza file di origine' end,
    case when copie_diverse then 'copie con importi diversi' end
  ], null) motivi,
  case
    when n_copia > 1 and not copie_diverse then 'doppione'
    when verifica.cf_valido(cf) and base is not null and trattenute is not null and netto is not null
         and abs(base - trattenute - netto) <= 1 and netto > 0
         and coalesce(file_origine,'')<>'' and not copie_diverse then 'verificato'
    else 'da_rivedere' end esito
from g;

create view verifica.riepilogo with (security_invoker = on) as
select 'cedolini' tipo, esito, count(*) n from verifica.cedolini group by esito
union all
select 'quietanze_f24', esito, count(*) from verifica.quietanze_f24 group by esito;

revoke all on all tables in schema verifica from anon, authenticated;

