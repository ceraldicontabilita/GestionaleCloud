-- Hardening applicato al progetto Supabase GestionaleCloud il 2026-09-11.
--
-- Le RPC public.gc_* restano eseguibili dal ruolo anon perché il runtime
-- server-to-server usa una publishable key per raggiungere PostgREST e aggiunge
-- il segreto applicativo x-gc-api-key. Ogni RPC chiama gc_assert_runtime_secret
-- prima di leggere o modificare dati. Il browser non deve conoscere tale
-- segreto. I privilegi PUBLIC/authenticated non sono necessari e vengono tolti.

alter function gestionale.documento_attivo(jsonb)
  set search_path = pg_catalog;
alter function gestionale.bank_ec_after_write()
  set search_path = pg_catalog;
alter function gestionale.bank_ec_before_write()
  set search_path = pg_catalog;

revoke execute on function public.gc_blob_stats(text) from public, authenticated;
revoke execute on function public.gc_collection_manifest() from public, authenticated;
revoke execute on function public.gc_delete_blobs(text[]) from public, authenticated;
revoke execute on function public.gc_delete_documents(text, text[]) from public, authenticated;
revoke execute on function public.gc_fetch_collection(text, integer, integer) from public, authenticated;
revoke execute on function public.gc_get_blob(text) from public, authenticated;
revoke execute on function public.gc_put_blob(text, text) from public, authenticated;
revoke execute on function public.gc_upsert_documents(text, jsonb) from public, authenticated;

grant execute on function public.gc_blob_stats(text) to anon, service_role;
grant execute on function public.gc_collection_manifest() to anon, service_role;
grant execute on function public.gc_delete_blobs(text[]) to anon, service_role;
grant execute on function public.gc_delete_documents(text, text[]) to anon, service_role;
grant execute on function public.gc_fetch_collection(text, integer, integer) to anon, service_role;
grant execute on function public.gc_get_blob(text) to anon, service_role;
grant execute on function public.gc_put_blob(text, text) to anon, service_role;
grant execute on function public.gc_upsert_documents(text, jsonb) to anon, service_role;
