-- Estende le letture puntuali a tutte le impronte documentali canoniche e
-- alle pagine di una singola versione fiscale. Le query applicative filtrano
-- poi gli eventuali altri predicati senza materializzare la collezione.

CREATE INDEX IF NOT EXISTS idx_documents_collection_pdf_hash
    ON gestionale.documents (collection, (data->>'pdf_hash'))
    WHERE coalesce(data->>'pdf_hash', '') <> '';

CREATE INDEX IF NOT EXISTS idx_documents_collection_version_id
    ON gestionale.documents (collection, (data->>'version_id'))
    WHERE coalesce(data->>'version_id', '') <> '';

CREATE OR REPLACE FUNCTION public.gc_fetch_documents_exact(
  p_collection text,
  p_field text,
  p_values text[],
  p_exclude_fields text[] default array[]::text[]
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'pg_catalog'
AS $function$
DECLARE result jsonb;
BEGIN
  PERFORM public.gc_assert_runtime_secret();
  IF coalesce(btrim(p_collection), '') = '' THEN
    RAISE invalid_parameter_value USING message = 'collezione mancante';
  END IF;
  IF p_field NOT IN (
    '_id', 'id', 'idempotency_key', 'sha256', 'file_hash', 'content_hash',
    'pdf_hash', 'version_id'
  ) THEN
    RAISE invalid_parameter_value USING message = 'campo lookup non consentito';
  END IF;
  IF coalesce(array_length(p_values, 1), 0) < 1
     OR coalesce(array_length(p_values, 1), 0) > 500 THEN
    RAISE invalid_parameter_value USING message = 'valori lookup non validi';
  END IF;
  IF coalesce(array_length(p_exclude_fields, 1), 0) > 32 THEN
    RAISE invalid_parameter_value USING message = 'troppe esclusioni';
  END IF;

  SELECT coalesce(jsonb_agg(page.document ORDER BY page.id), '[]'::jsonb)
  INTO result
  FROM (
    SELECT d.id,
           (d.data - coalesce(p_exclude_fields, array[]::text[]))
             || jsonb_build_object('_id', d.id) AS document
    FROM gestionale.documents d
    WHERE d.collection = p_collection
      AND CASE p_field
        WHEN '_id' THEN d.id = ANY(p_values)
        WHEN 'id' THEN d.data->>'id' = ANY(p_values)
        WHEN 'idempotency_key' THEN d.idempotency_key = ANY(p_values)
        WHEN 'sha256' THEN d.data->>'sha256' = ANY(p_values)
        WHEN 'file_hash' THEN d.data->>'file_hash' = ANY(p_values)
        WHEN 'content_hash' THEN d.data->>'content_hash' = ANY(p_values)
        WHEN 'pdf_hash' THEN d.data->>'pdf_hash' = ANY(p_values)
        WHEN 'version_id' THEN d.data->>'version_id' = ANY(p_values)
        ELSE false
      END
    ORDER BY d.id
    LIMIT 500
  ) page;
  RETURN result;
END;
$function$;

REVOKE ALL ON FUNCTION public.gc_fetch_documents_exact(text, text, text[], text[])
  FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.gc_fetch_documents_exact(text, text, text[], text[])
  TO anon, service_role;
