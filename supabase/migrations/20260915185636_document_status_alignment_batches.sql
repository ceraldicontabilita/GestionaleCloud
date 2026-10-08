-- Il riallineamento precedente aggiornava l'intero registro in una singola
-- transazione. Un indice parziale e lotti da 250 mantengono ogni RPC breve.

CREATE INDEX IF NOT EXISTS idx_documents_inbox_status_alignment
    ON gestionale.documents (collection, id)
    WHERE collection IN ('documents_inbox', 'documents_inbox__shard_001')
      AND (data @> '{"processed": true}'::jsonb
           OR data @> '{"xml_processed": true}'::jsonb)
      AND (NOT data ? 'status'
           OR data->'status' = 'null'::jsonb
           OR data->>'status' IN ('nuovo', 'da_processare'));

CREATE OR REPLACE FUNCTION public.gc_align_processed_document_status()
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'pg_catalog'
AS $function$
DECLARE affected integer;
BEGIN
  PERFORM public.gc_assert_runtime_secret();

  WITH targets AS MATERIALIZED (
    SELECT d.id
    FROM gestionale.documents d
    WHERE d.collection IN ('documents_inbox', 'documents_inbox__shard_001')
      AND (d.data @> '{"processed": true}'::jsonb
           OR d.data @> '{"xml_processed": true}'::jsonb)
      AND (NOT d.data ? 'status'
           OR d.data->'status' = 'null'::jsonb
           OR d.data->>'status' IN ('nuovo', 'da_processare'))
    ORDER BY d.collection, d.id
    LIMIT 250
    FOR UPDATE SKIP LOCKED
  )
  UPDATE gestionale.documents d
     SET data = jsonb_set(d.data, '{status}', '"processato"'::jsonb, true),
         updated_at = now()
    FROM targets t
   WHERE d.id = t.id;

  GET DIAGNOSTICS affected = ROW_COUNT;
  RETURN affected;
END;
$function$;

REVOKE ALL ON FUNCTION public.gc_align_processed_document_status()
  FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.gc_align_processed_document_status()
  TO anon, service_role;
