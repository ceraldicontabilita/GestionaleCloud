do $$
declare def text;
begin
  def := pg_get_viewdef('verifica.tabulato_tributi'::regclass);
  def := replace(def,
    'generate_series(date_trunc(''year''::text, (p.primo)::timestamp with time zone), date_trunc(''month''::text, (CURRENT_DATE)::timestamp with time zone),',
    'generate_series(CASE WHEN r.tipo = ''mensile''::text THEN (p.primo)::timestamp with time zone ELSE date_trunc(''year''::text, (p.primo)::timestamp with time zone) END, (date_trunc(''month''::text, (CURRENT_DATE)::timestamp with time zone) - ''1 mon''::interval),');
  if position('ELSE date_trunc(''year''' in def) = 0 then raise exception 'sostituzione non riuscita: %', left(def, 3000); end if;
  execute 'create or replace view verifica.tabulato_tributi with (security_invoker = on) as ' || def;
end $$;

