do $$
declare def text;
begin
  def := pg_get_viewdef('verifica.versamenti_tributi'::regclass);
  def := replace(def,
    'COALESCE((d.data ->> ''codice_fiscale''::text), ((d.data -> ''dati_generali''::text) ->> ''codice_fiscale''::text), ''04523831214''::text)',
    'COALESCE(NULLIF((d.data ->> ''codice_fiscale''::text), ''''::text), NULLIF(((d.data -> ''dati_generali''::text) ->> ''codice_fiscale''::text), ''''::text), ''04523831214''::text)');
  if position('NULLIF((d.data ->> ''codice_fiscale''' in def) = 0 then raise exception 'sostituzione non riuscita'; end if;
  execute 'create or replace view verifica.versamenti_tributi with (security_invoker = on) as ' || def;
end $$;

