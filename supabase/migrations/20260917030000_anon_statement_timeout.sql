-- 17/09/2026 — Le RPC del runtime (gc_fetch_collection*, gc_upsert_documents,
-- lotti_list_collections, ...) vengono eseguite da PostgREST con il ruolo
-- `anon`, che su Supabase nasce con `statement_timeout = 3s`. Con la tabella
-- gestionale.documents a 1 GB (payload XML/PDF) e il compute Micro, una
-- pagina di 500 documenti supera spesso i 3 s: nei log di produzione
-- 272 "canceling statement due to statement timeout" in 17 minuti, che
-- l'applicazione ritenta (pagine più piccole) moltiplicando il carico, e
-- il /health di Lotti rispondeva 500 per lo stesso motivo.
-- 20 s resta sotto il timeout HTTP dei client (60 s) e dà alle letture
-- paginate il tempo di finire invece di ripartire da capo.
alter role anon set statement_timeout = '20s';
-- PostgREST rilegge le impostazioni dei ruoli solo al reload della config.
notify pgrst, 'reload config';
