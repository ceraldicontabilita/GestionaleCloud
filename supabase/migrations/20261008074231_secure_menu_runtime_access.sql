-- Prerequisito di rilascio: il backend Menu deve già inviare x-gc-api-key.
-- Nessun dato/immagine viene eliminato; gli URL pubblici del bucket restano tali.
CREATE SCHEMA IF NOT EXISTS gc_private AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA gc_private FROM PUBLIC;
GRANT USAGE ON SCHEMA gc_private TO anon;

CREATE OR REPLACE FUNCTION gc_private.menu_runtime_authorized()
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
BEGIN
  PERFORM public.gc_assert_runtime_secret();
  RETURN true;
END;
$function$;
REVOKE ALL ON FUNCTION gc_private.menu_runtime_authorized() FROM PUBLIC, authenticated;
GRANT EXECUTE ON FUNCTION gc_private.menu_runtime_authorized() TO anon;

DO $migration$
DECLARE
  tab record;
  pol record;
BEGIN
  FOR tab IN
    SELECT c.relname FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'menu' AND c.relkind IN ('r', 'p')
  LOOP
    EXECUTE format('ALTER TABLE menu.%I ENABLE ROW LEVEL SECURITY', tab.relname);
    -- Le policy permissive si combinano con OR: non deve restare una vecchia
    -- policy true che vanifichi il nuovo controllo.
    FOR pol IN SELECT policyname FROM pg_catalog.pg_policies
      WHERE schemaname = 'menu' AND tablename = tab.relname
    LOOP
      EXECUTE format('DROP POLICY %I ON menu.%I', pol.policyname, tab.relname);
    END LOOP;
    EXECUTE format(
      'CREATE POLICY menu_backend_runtime ON menu.%I FOR ALL TO anon '
      'USING ((SELECT gc_private.menu_runtime_authorized())) '
      'WITH CHECK ((SELECT gc_private.menu_runtime_authorized()))', tab.relname);
  END LOOP;
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_views
             WHERE schemaname = 'menu' AND viewname = 'menu_products_disponibili') THEN
    ALTER VIEW menu.menu_products_disponibili SET (security_invoker = true);
  END IF;
END;
$migration$;

DROP POLICY IF EXISTS menu_images_anon_all ON storage.objects;
-- Il nome effettivo della policy storica è rilevato, non dedotto dal file.
DO $storage$
DECLARE pol record;
BEGIN
  FOR pol IN SELECT policyname FROM pg_catalog.pg_policies
    WHERE schemaname = 'storage' AND tablename = 'objects'
      AND (coalesce(qual, '') LIKE '%menu-images%'
           OR coalesce(with_check, '') LIKE '%menu-images%')
  LOOP
    EXECUTE format('DROP POLICY %I ON storage.objects', pol.policyname);
  END LOOP;
END;
$storage$;
CREATE POLICY menu_images_backend_runtime ON storage.objects
FOR ALL TO anon
USING (bucket_id = 'menu-images' AND (SELECT gc_private.menu_runtime_authorized()))
WITH CHECK (bucket_id = 'menu-images' AND (SELECT gc_private.menu_runtime_authorized()));

NOTIFY pgrst, 'reload schema';
