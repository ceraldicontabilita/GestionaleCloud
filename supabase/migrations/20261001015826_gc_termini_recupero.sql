-- Termini di recupero dei tributi: ingresso unico alla vista verifica.tabulato_tributi_termini.
-- Lo schema verifica non e' leggibile da nessun ruolo applicativo (solo postgres): la
-- funzione gira come proprietario, esige il segreto runtime come le altre gc_* e
-- restituisce le righe della vista in un solo array json.
create or replace function public.gc_termini_recupero()
returns jsonb
language plpgsql
security definer
set search_path to 'pg_catalog'
as $function$
begin
  perform public.gc_assert_runtime_secret();
  return coalesce((
    select jsonb_agg(to_jsonb(t) order by t.codice, t.scadenza, t.periodo)
    from verifica.tabulato_tributi_termini t
  ), '[]'::jsonb);
end;
$function$;

revoke all on function public.gc_termini_recupero() from public, anon, authenticated;
grant execute on function public.gc_termini_recupero() to anon, service_role;
