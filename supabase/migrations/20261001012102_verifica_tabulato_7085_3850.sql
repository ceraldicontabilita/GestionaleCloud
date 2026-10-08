do $$
declare def text;
begin
  def := pg_get_viewdef('verifica.tabulato_tributi'::regclass);
  def := replace(def, '(''7085''::text,''Diritto annuale Camera di commercio''::text,''annuale''::text,6,6,0)',
                      '(''7085''::text,''Tassa annuale vidimazione libri sociali''::text,''annuale''::text,3,3,0), (''3850''::text,''Diritto annuale Camera di commercio''::text,''annuale''::text,6,6,0)');
  def := replace(def, 'WHEN (a.chiave_codice = ''7085''::text) THEN make_date((EXTRACT(year FROM a.rif))::integer, 6, 30)',
                      'WHEN (a.chiave_codice = ''7085''::text) THEN make_date((EXTRACT(year FROM a.rif))::integer, 3, 16) WHEN (a.chiave_codice = ''3850''::text) THEN make_date((EXTRACT(year FROM a.rif))::integer, 6, 30)');
  def := replace(def, 'a.chiave_codice = ANY (ARRAY[''INAIL''::text, ''7085''::text])', 'a.chiave_codice = ANY (ARRAY[''INAIL''::text, ''7085''::text, ''3850''::text])');
  def := replace(def, 'WHEN (q.chiave_codice = ''7085''::text) THEN', 'WHEN (q.chiave_codice = ANY (ARRAY[''7085''::text, ''3850''::text])) THEN');
  def := replace(def, '(c.chiave_codice = ''7085''::text) AND', '(c.chiave_codice = ANY (ARRAY[''7085''::text, ''3850''::text])) AND');
  if position('vidimazione' in def) = 0 or position('ARRAY[''INAIL''::text, ''7085''::text, ''3850''' in def) = 0
     or position('q.chiave_codice = ANY (ARRAY[''7085''' in def) = 0 or position('c.chiave_codice = ANY (ARRAY[''7085''' in def) = 0
     or position('integer, 3, 16)' in def) = 0 then
    raise exception 'sostituzione non riuscita';
  end if;
  execute 'create or replace view verifica.tabulato_tributi with (security_invoker = on) as ' || def;
end $$;

