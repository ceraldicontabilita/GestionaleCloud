-- Autorizza esplicitamente il DELETE atomico del probe nella guardia globale.

CREATE OR REPLACE FUNCTION public.gc_runtime_health_probe(p_probe_id text)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'pg_catalog'
AS $function$
BEGIN
  PERFORM public.gc_assert_runtime_secret();
  IF coalesce(btrim(p_probe_id), '') = '' THEN
    RAISE invalid_parameter_value USING message = 'probe id mancante';
  END IF;

  INSERT INTO gestionale.documents (collection, id, data)
  VALUES (
    'runtime_health',
    p_probe_id,
    jsonb_build_object('tipo', 'runtime_write_probe')
  )
  ON CONFLICT (collection, id)
  DO UPDATE SET data = excluded.data, updated_at = now();

  PERFORM gestionale.consenti_cancellazione();
  DELETE FROM gestionale.documents
  WHERE collection = 'runtime_health' AND id = p_probe_id;

  RETURN true;
END;
$function$;

REVOKE ALL ON FUNCTION public.gc_runtime_health_probe(text)
  FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.gc_runtime_health_probe(text)
  TO anon, service_role;
