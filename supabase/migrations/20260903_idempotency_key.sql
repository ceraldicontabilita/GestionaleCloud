-- ============================================================================
-- 20260903_idempotency_key.sql — unicità delle scritture derivate in Postgres
-- Progetto Supabase GestionaleCloud (lohczjdiawjryuopncwc), tabella
-- gestionale.documents (collection text, id text, data jsonb, created_at,
-- updated_at). Riferimento: memoria/AUDIT_COMMERCIALISTA_2026-09-03.md §2, PR 5.
--
-- PROBLEMA: la guardia di idempotenza di app/services/scritture_contabili.py
-- lavora sulla cache in memoria di UN processo; due processi (deploy
-- sovrapposto, riavvio, scheduler + web) hanno scritto entrambi lo stesso
-- corrispettivo: 77 entrate cassa doppie, 58 uscite POS cassa doppie, 56
-- crediti POS banca doppi. Nessun vincolo lato Postgres.
--
-- RIMEDIO: ogni scrittura derivata porta data->>'idempotency_key'
-- (corr:<id>:cassa_entrata | corr:<id>:cassa_uscita:<gestore> |
-- corr:<id>:banca_credito:<gestore>); qui la chiave diventa una colonna
-- generata con INDICE UNICO PARZIALE tra le righe attive, e l'RPC di upsert
-- rifiuta (senza fallire) una riga la cui chiave esiste già con id diverso.
--
-- ORDINE OBBLIGATORIO DI ESECUZIONE
--   0. Deploy del codice applicativo (PR 5): il client tollera sia la
--      vecchia RPC (ritorna integer) sia la nuova (ritorna jsonb).
--   1. Bonifica dei doppioni esistenti, PRIMA di questo file:
--        POST /api/admin/bonifica-prima-nota-doppioni?dry_run=true   (analisi)
--        POST /api/admin/bonifica-prima-nota-doppioni?dry_run=false  (applica)
--      oppure da shell: python -m app.services.bonifica_prima_nota_doppioni [--applica]
--      La bonifica marca le copie più recenti entity_status='deleted' +
--      duplicate_of e assegna idempotency_key alle righe tenute.
--   2. Eseguire questo file per intero (SQL editor di Supabase o
--      `supabase db push`). Il blocco "CONTROLLO" fa FALLIRE la migrazione se
--      restano chiavi doppie tra le righe attive: in quel caso ripetere il
--      punto 1 e rilanciare. Niente viene creato a metà: tutto è in una
--      transazione.
--   3. Verifica finale (in fondo al file, sezione VERIFICA).
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- 1. Colonna generata: la chiave è leggibile e indicizzabile da SQL.
-- ----------------------------------------------------------------------------
alter table gestionale.documents
  add column if not exists idempotency_key text
  generated always as (data ->> 'idempotency_key') stored;

-- ----------------------------------------------------------------------------
-- 2. Predicato "riga attiva": è LO STESSO usato da scritture_contabili.py
--    (FILTRO_MOVIMENTO_ATTIVO) e dalla bonifica. Una riga soft-deleted o
--    archiviata non blocca la ri-creazione della scrittura attiva.
-- ----------------------------------------------------------------------------
create or replace function gestionale.documento_attivo(p_data jsonb)
returns boolean
language sql
immutable
as $$
  select coalesce(p_data ->> 'entity_status', '') <> 'deleted'
     and coalesce(p_data ->> 'status', '') not in ('deleted', 'archived');
$$;

-- ----------------------------------------------------------------------------
-- 3. CONTROLLO: fallisce se la bonifica non è stata eseguita (o è incompleta).
-- ----------------------------------------------------------------------------
do $$
declare
  chiavi_doppie integer;
  esempio text;
begin
  select count(*), min(collection || ' ' || idempotency_key)
    into chiavi_doppie, esempio
  from (
    select collection, idempotency_key
    from gestionale.documents
    where idempotency_key is not null
      and gestionale.documento_attivo(data)
    group by collection, idempotency_key
    having count(*) > 1
  ) doppie;
  if chiavi_doppie > 0 then
    raise exception
      'Migrazione interrotta: % chiavi idempotency_key ancora doppie tra le righe attive (es. %). Eseguire prima POST /api/admin/bonifica-prima-nota-doppioni?dry_run=false, poi rilanciare.',
      chiavi_doppie, esempio;
  end if;
end $$;

-- ----------------------------------------------------------------------------
-- 4. Indice UNICO parziale: una sola riga attiva per (collection, chiave).
--    Vale per ogni collezione (anche `pagamenti`, che già usa
--    idempotency_key con lo stesso significato).
-- ----------------------------------------------------------------------------
create unique index if not exists documents_idempotency_key_uidx
  on gestionale.documents (collection, idempotency_key)
  where idempotency_key is not null and gestionale.documento_attivo(data);

-- ----------------------------------------------------------------------------
-- 5. RPC di upsert: versione esposta da PostgREST (schema public, quella
--    chiamata dal server: `pgrst.db_schemas` non è impostato, quindi
--    /rest/v1/rpc/gc_upsert_documents risolve public.gc_upsert_documents).
--    Cambia il tipo di ritorno (integer -> jsonb): serve drop + create.
--    Conserva: controllo chiave runtime (public.gc_assert_runtime_secret),
--    validazioni, `item - '_id'`, on conflict (collection, id) do update.
--    Aggiunge: lock consultivo per collezione (controllo + scrittura sono
--    un'unica azione anche tra connessioni diverse), rifiuto delle righe
--    ATTIVE la cui (collection, idempotency_key) esiste già con id diverso
--    — sia in tabella sia nello stesso batch — restituito come elenco jsonb
--    con il documento esistente, così il client riallinea la cache.
-- ----------------------------------------------------------------------------
drop function if exists public.gc_upsert_documents(text, jsonb);

create function public.gc_upsert_documents(p_collection text, p_documents jsonb)
returns jsonb
language plpgsql
security definer
set search_path to 'pg_catalog'
as $function$
declare
  invalid_count integer;
  written integer := 0;
  rejected jsonb := '[]'::jsonb;
begin
  perform public.gc_assert_runtime_secret();
  if coalesce(btrim(p_collection), '') = '' then
    raise invalid_parameter_value using message = 'collezione mancante';
  end if;
  if p_documents is null or jsonb_typeof(p_documents) <> 'array' then
    raise invalid_parameter_value using message = 'documenti non validi';
  end if;

  select count(*)::integer
  into invalid_count
  from jsonb_array_elements(p_documents) item
  where jsonb_typeof(item) <> 'object'
     or coalesce(item ->> '_id', '') = '';

  if invalid_count > 0 then
    raise invalid_parameter_value using message = 'documento senza _id';
  end if;

  -- Serializza gli upsert della stessa collezione tra connessioni diverse:
  -- il controllo "la chiave esiste già?" e la scrittura diventano un'unica
  -- azione, esattamente ciò che la cache di un singolo processo non può
  -- garantire. Rilasciato a fine transazione.
  perform pg_advisory_xact_lock(hashtext('gc_upsert_documents:' || p_collection));

  with incoming as (
    select
      item ->> '_id' as id,
      item - '_id' as data,
      nullif(item ->> 'idempotency_key', '') as idempotency_key,
      ord
    from jsonb_array_elements(p_documents) with ordinality as t(item, ord)
  ),
  attive as (
    select * from incoming
    where idempotency_key is not null and gestionale.documento_attivo(data)
  ),
  -- (a) chiave già usata da una riga ATTIVA in tabella con id diverso
  contro_tabella as (
    select
      i.id as id_rifiutato,
      e.id as id_esistente,
      i.idempotency_key,
      e.data || jsonb_build_object('_id', e.id) as documento_esistente
    from attive i
    join gestionale.documents e
      on e.collection = p_collection
     and e.idempotency_key = i.idempotency_key
     and e.id <> i.id
     and gestionale.documento_attivo(e.data)
  ),
  -- (b) stessa chiave due volte nello stesso batch: sopravvive la prima
  contro_batch as (
    select
      i2.id as id_rifiutato,
      i1.id as id_esistente,
      i2.idempotency_key,
      i1.data || jsonb_build_object('_id', i1.id) as documento_esistente
    from attive i1
    join attive i2
      on i2.idempotency_key = i1.idempotency_key
     and i2.id <> i1.id
     and i1.ord < i2.ord
    where not exists (
      select 1 from contro_tabella c where c.id_rifiutato = i1.id
    )
  ),
  rifiuti as (
    select * from contro_tabella
    union all
    select * from contro_batch
  )
  select coalesce(jsonb_agg(jsonb_build_object(
           'id_rifiutato', r.id_rifiutato,
           'id_esistente', r.id_esistente,
           'idempotency_key', r.idempotency_key,
           'documento_esistente', r.documento_esistente
         )), '[]'::jsonb)
  into rejected
  from rifiuti r;

  insert into gestionale.documents (collection, id, data)
  select p_collection, item ->> '_id', item - '_id'
  from jsonb_array_elements(p_documents) item
  where not exists (
    select 1 from jsonb_array_elements(rejected) r
    where r ->> 'id_rifiutato' = item ->> '_id'
  )
  on conflict (collection, id)
  do update set data = excluded.data, updated_at = now();

  get diagnostics written = row_count;
  return jsonb_build_object('upserted', written, 'rejected', rejected);
end;
$function$;

revoke all on function public.gc_upsert_documents(text, jsonb) from public;
grant execute on function public.gc_upsert_documents(text, jsonb) to anon, service_role;

-- ----------------------------------------------------------------------------
-- 6. Copia nello schema privato `gestionale` (creata dalla migrazione
--    20260901234827 add_private_runtime_rpc, non esposta da PostgREST ma
--    mantenuta allineata). Conserva il suo controllo
--    gestionale._verifica_chiave_runtime() e il suo formato (salva `elem`
--    intero, compreso _id, come faceva). Stessa regola di rifiuto.
-- ----------------------------------------------------------------------------
drop function if exists gestionale.gc_upsert_documents(text, jsonb);

create function gestionale.gc_upsert_documents(p_collection text, p_documents jsonb)
returns jsonb
language plpgsql
security definer
set search_path to 'gestionale', 'public'
as $function$
declare
  written integer := 0;
  rejected jsonb := '[]'::jsonb;
begin
  perform gestionale._verifica_chiave_runtime();
  if p_documents is null or jsonb_typeof(p_documents) <> 'array' then
    raise invalid_parameter_value using message = 'documenti non validi';
  end if;

  perform pg_advisory_xact_lock(hashtext('gc_upsert_documents:' || p_collection));

  with incoming as (
    select
      elem ->> '_id' as id,
      elem as data,
      nullif(elem ->> 'idempotency_key', '') as idempotency_key,
      ord
    from jsonb_array_elements(p_documents) with ordinality as t(elem, ord)
    where elem ->> '_id' is not null
  ),
  attive as (
    select * from incoming
    where idempotency_key is not null and gestionale.documento_attivo(data)
  ),
  contro_tabella as (
    select
      i.id as id_rifiutato,
      e.id as id_esistente,
      i.idempotency_key,
      e.data || jsonb_build_object('_id', e.id) as documento_esistente
    from attive i
    join gestionale.documents e
      on e.collection = p_collection
     and e.idempotency_key = i.idempotency_key
     and e.id <> i.id
     and gestionale.documento_attivo(e.data)
  ),
  contro_batch as (
    select
      i2.id as id_rifiutato,
      i1.id as id_esistente,
      i2.idempotency_key,
      i1.data || jsonb_build_object('_id', i1.id) as documento_esistente
    from attive i1
    join attive i2
      on i2.idempotency_key = i1.idempotency_key
     and i2.id <> i1.id
     and i1.ord < i2.ord
    where not exists (
      select 1 from contro_tabella c where c.id_rifiutato = i1.id
    )
  ),
  rifiuti as (
    select * from contro_tabella
    union all
    select * from contro_batch
  )
  select coalesce(jsonb_agg(jsonb_build_object(
           'id_rifiutato', r.id_rifiutato,
           'id_esistente', r.id_esistente,
           'idempotency_key', r.idempotency_key,
           'documento_esistente', r.documento_esistente
         )), '[]'::jsonb)
  into rejected
  from rifiuti r;

  insert into gestionale.documents (collection, id, data, updated_at)
  select p_collection, elem ->> '_id', elem, now()
  from jsonb_array_elements(p_documents) as elem
  where elem ->> '_id' is not null
    and not exists (
      select 1 from jsonb_array_elements(rejected) r
      where r ->> 'id_rifiutato' = elem ->> '_id'
    )
  on conflict (collection, id)
  do update set data = excluded.data, updated_at = now();

  get diagnostics written = row_count;
  return jsonb_build_object('upserted', written, 'rejected', rejected);
end;
$function$;

grant execute on function gestionale.gc_upsert_documents(text, jsonb)
  to anon, authenticated, service_role;

-- PostgREST deve rileggere le firme (tipo di ritorno cambiato).
notify pgrst, 'reload schema';

commit;

-- ============================================================================
-- VERIFICA (sola lettura, dopo il commit)
-- ============================================================================
-- a) colonna e indice presenti:
--   select indexname from pg_indexes where schemaname='gestionale'
--     and tablename='documents' and indexname='documents_idempotency_key_uidx';
-- b) nessuna chiave doppia attiva (deve restituire 0 righe):
--   select collection, idempotency_key, count(*) from gestionale.documents
--    where idempotency_key is not null and gestionale.documento_attivo(data)
--    group by 1,2 having count(*) > 1;
-- c) righe di Prima Nota derivate da corrispettivi ancora senza chiave
--    (attese 0 dopo la bonifica; se >0 rilanciare la bonifica):
--   select collection, count(*) from gestionale.documents
--    where collection in ('prima_nota_cassa','prima_nota_banca')
--      and coalesce(data->>'corrispettivo_id','') <> ''
--      and gestionale.documento_attivo(data)
--      and idempotency_key is null
--    group by 1;
-- d) la RPC risponde nel nuovo formato (chiamata dal server, log all'avvio):
--    nessun "Supabase ha rifiutato" a ERROR nei log = nessun conflitto.
--
-- ROLLBACK (solo se necessario):
--   drop index if exists gestionale.documents_idempotency_key_uidx;
--   -- le due funzioni vanno ripristinate dalla migrazione 20260903162125
--   -- (gc_runtime_rpcs) e 20260901234827 (add_private_runtime_rpc);
--   alter table gestionale.documents drop column if exists idempotency_key;
--   drop function if exists gestionale.documento_attivo(jsonb);
