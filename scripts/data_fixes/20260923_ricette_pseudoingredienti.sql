-- RST-0508BF: due righe di riepilogo dell'Excel legacy non sono ingredienti.
-- Migrazione una-tantum dei soli 99 record operativi identificati esattamente.
-- La copia integrale antecedente resta recuperabile nella collection di backup.
begin;

do $$
declare
  record_count integer;
  updated_count integer;
begin
  perform 1
  from lotti.lotti_documents d
  where d.collection = 'ricette'
    and coalesce((d.data->>'ricetta_operativa')::boolean, true)
    and exists (
      select 1 from jsonb_array_elements(coalesce(d.data->'ingredienti_dettaglio', '[]'::jsonb)) x
      where x->>'nome' = 'Peso impasto totale (g)'
    )
  for update;

  select count(*) into record_count
  from lotti.lotti_documents d
  where d.collection = 'ricette'
    and coalesce((d.data->>'ricetta_operativa')::boolean, true)
    and exists (
      select 1 from jsonb_array_elements(coalesce(d.data->'ingredienti_dettaglio', '[]'::jsonb)) x
      where x->>'nome' = 'Peso impasto totale (g)'
    );

  if record_count = 0 then
    return;
  end if;
  if record_count <> 99 then
    raise exception 'Attesi 99 record legacy, trovati %: riesaminare', record_count;
  end if;

  if exists (
    select 1
    from lotti.lotti_documents d
    where d.collection = 'ricette'
      and coalesce((d.data->>'ricetta_operativa')::boolean, true)
      and exists (
        select 1 from jsonb_array_elements(coalesce(d.data->'ingredienti_dettaglio', '[]'::jsonb)) x
        where x->>'nome' = 'Peso impasto totale (g)'
      )
      and (
        (select count(*) from jsonb_array_elements(d.data->'ingredienti_dettaglio') x
         where x->>'nome' in ('Peso impasto totale (g)', 'Pezzi prodotti (n)')) <> 2
        or (select count(*) from jsonb_array_elements(d.data->'ingredienti_dettaglio') x
            where x->>'nome' in ('Peso impasto totale (g)', 'Pezzi prodotti (n)')
              and coalesce((x->>'quantita')::numeric, 0) = 0) <> 2
        or (select count(*) from jsonb_array_elements_text(coalesce(d.data->'ingredienti','[]'::jsonb)) x
            where x in ('Peso impasto totale (g)', 'Pezzi prodotti (n)')) <> 2
      )
  ) then
    raise exception 'Pseudoingredienti diversi dal censimento: nessuna modifica applicata';
  end if;

  insert into lotti.lotti_documents (collection, doc_id, data, created_at, updated_at)
  select 'ricette_backup_20260923_rst0508bf', d.doc_id, d.data, now(), now()
  from lotti.lotti_documents d
  where d.collection = 'ricette'
    and coalesce((d.data->>'ricetta_operativa')::boolean, true)
    and exists (
      select 1 from jsonb_array_elements(d.data->'ingredienti_dettaglio') x
      where x->>'nome' = 'Peso impasto totale (g)'
    );

  with pulite as (
    select d.doc_id,
      (select coalesce(jsonb_agg(x.value order by x.ord), '[]'::jsonb)
       from jsonb_array_elements(d.data->'ingredienti_dettaglio') with ordinality x(value, ord)
       where x.value->>'nome' not in ('Peso impasto totale (g)', 'Pezzi prodotti (n)')) as dettagli,
      (select coalesce(jsonb_agg(to_jsonb(x.value) order by x.ord), '[]'::jsonb)
       from jsonb_array_elements_text(d.data->'ingredienti') with ordinality x(value, ord)
       where x.value not in ('Peso impasto totale (g)', 'Pezzi prodotti (n)')) as nomi
    from lotti.lotti_documents d
    where d.collection = 'ricette'
      and coalesce((d.data->>'ricetta_operativa')::boolean, true)
      and exists (
        select 1 from jsonb_array_elements(d.data->'ingredienti_dettaglio') x
        where x->>'nome' = 'Peso impasto totale (g)'
      )
  )
  update lotti.lotti_documents d
  set data = jsonb_set(jsonb_set(d.data, '{ingredienti_dettaglio}', p.dettagli), '{ingredienti}', p.nomi)
             || jsonb_build_object('bonifica_ingredienti', 'RST-0508BF'),
      updated_at = now()
  from pulite p
  where d.collection = 'ricette' and d.doc_id = p.doc_id;

  get diagnostics updated_count = row_count;
  if updated_count <> 99 then
    raise exception 'Aggiornati % record invece di 99: rollback', updated_count;
  end if;
end $$;

commit;
