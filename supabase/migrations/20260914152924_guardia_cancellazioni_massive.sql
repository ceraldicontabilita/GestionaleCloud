-- Guardia contro le cancellazioni di massa eseguite fuori dall'applicazione.
--
-- Il 14/09/2026, fra le 00:44 e le 00:54 UTC, questa istruzione e' stata
-- eseguita quattro volte col ruolo `postgres` (SQL diretto, non l'app):
--
--   delete from gestionale.documents where collection not like 'menu%'
--
-- Ha svuotato 53.172 righe: le collezioni popolate sono passate da 83 a 5.
-- Il re-import successivo ne ha ricostruite 21; le scritture non ricostruibili
-- da fonti esterne (assegni, cespiti, F24, scadenzario, riconciliazioni,
-- partite aperte, libro giornale, piano dei conti, documents_inbox...) sono
-- rimaste a zero.
--
-- L'applicazione NON cancella mai con un filtro: passa sempre dalle funzioni
-- gc_delete_documents / gc_delete_blobs / lotti_delete_* con la lista esplicita
-- degli id (oppure, per lotti_delete_collection, con la collezione dichiarata).
-- La guardia distingue quindi le due cose per ORIGINE, non per numero di righe:
-- nessun limite alle cancellazioni dell'app, blocco totale di quelle a mano.
--
-- Per una manutenzione deliberata da SQL, nella STESSA transazione:
--   begin;
--   select gestionale.consenti_cancellazione();
--   delete from ... ;
--   commit;
--
-- Non tocca autenticazione, RLS, permessi o dati. Reversibile: basta eliminare
-- i trigger `trg_guardia_*`.

-- ---------------------------------------------------------------- sblocco ---
create or replace function gestionale.consenti_cancellazione()
returns void
language sql
security definer
set search_path to pg_catalog
as $$
  select set_config('gestionale.cancellazione_autorizzata', '1', true);
$$;

comment on function gestionale.consenti_cancellazione() is
  'Autorizza le cancellazioni per la transazione corrente. Richiamata dalle funzioni runtime; da SQL va usata solo per manutenzioni deliberate.';

revoke all on function gestionale.consenti_cancellazione() from public;

-- --------------------------------------------------------------- guardie ---
create or replace function gestionale.blocca_delete_non_autorizzata()
returns trigger
language plpgsql
set search_path to pg_catalog
as $$
declare
  righe bigint := 0;
begin
  if coalesce(current_setting('gestionale.cancellazione_autorizzata', true), '') = '1' then
    return null;
  end if;

  select count(*) into righe from righe_cancellate;
  if righe = 0 then
    return null;
  end if;

  raise exception using
    errcode = 'raise_exception',
    message = format(
      'Cancellazione bloccata: %s righe da %I.%I richieste fuori dalle funzioni dell''applicazione',
      righe, tg_table_schema, tg_table_name),
    hint =
      'Le cancellazioni dell''app passano da gc_delete_documents / gc_delete_blobs / lotti_delete_*. '
      'Per una manutenzione deliberata eseguire, nella STESSA transazione: '
      'select gestionale.consenti_cancellazione();';
end;
$$;

create or replace function gestionale.blocca_truncate_non_autorizzato()
returns trigger
language plpgsql
set search_path to pg_catalog
as $$
begin
  if coalesce(current_setting('gestionale.cancellazione_autorizzata', true), '') = '1' then
    return null;
  end if;

  raise exception using
    errcode = 'raise_exception',
    message = format('TRUNCATE bloccato su %I.%I', tg_table_schema, tg_table_name),
    hint =
      'Per una manutenzione deliberata eseguire, nella STESSA transazione: '
      'select gestionale.consenti_cancellazione();';
end;
$$;

-- ------------------------------------------------------- applica i trigger ---
-- gestionale.documents, gestionale.blobs, lotti.lotti_documents e l'intero
-- schema legacy_staging (archivio storico CeraldiFatture: unica copia rimasta
-- dopo la fusione, nessuna applicazione ci scrive).
do $$
declare
  t record;
begin
  for t in
    select n.nspname as schema, c.relname as tabella
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where c.relkind = 'r'
      and (
        (n.nspname = 'gestionale' and c.relname in ('documents', 'blobs'))
        or (n.nspname = 'lotti' and c.relname = 'lotti_documents')
        or n.nspname = 'legacy_staging'
      )
  loop
    execute format('drop trigger if exists trg_guardia_delete on %I.%I', t.schema, t.tabella);
    execute format(
      'create trigger trg_guardia_delete after delete on %I.%I '
      'referencing old table as righe_cancellate '
      'for each statement execute function gestionale.blocca_delete_non_autorizzata()',
      t.schema, t.tabella);

    execute format('drop trigger if exists trg_guardia_truncate on %I.%I', t.schema, t.tabella);
    execute format(
      'create trigger trg_guardia_truncate before truncate on %I.%I '
      'for each statement execute function gestionale.blocca_truncate_non_autorizzato()',
      t.schema, t.tabella);
  end loop;
end;
$$;

-- --------------------------------- le funzioni runtime restano autorizzate ---
-- Unica modifica: una riga di autorizzazione in testa. Logica invariata.

create or replace function public.gc_delete_documents(p_collection text, p_ids text[])
returns integer
language plpgsql
security definer
set search_path to 'pg_catalog'
as $function$
declare
  deleted integer;
begin
  perform public.gc_assert_runtime_secret();
  if coalesce(btrim(p_collection), '') = '' then
    raise invalid_parameter_value using message = 'collezione mancante';
  end if;

  perform gestionale.consenti_cancellazione();

  delete from gestionale.documents d
  where d.collection = p_collection
    and d.id = any(coalesce(p_ids, array[]::text[]));
  get diagnostics deleted = row_count;
  return deleted;
end;
$function$;

create or replace function gestionale.gc_delete_documents(p_collection text, p_ids text[])
returns void
language plpgsql
security definer
set search_path to 'gestionale', 'public'
as $function$
begin
  perform gestionale._verifica_chiave_runtime();
  perform gestionale.consenti_cancellazione();
  delete from gestionale.documents
  where collection = p_collection and id = any(p_ids);
end;
$function$;

create or replace function public.gc_delete_blobs(p_keys text[])
returns integer
language plpgsql
security definer
set search_path to 'pg_catalog'
as $function$
declare removed integer;
begin
  perform public.gc_assert_runtime_secret();
  if p_keys is null then
    return 0;
  end if;

  perform gestionale.consenti_cancellazione();

  -- Un riferimento in meno per ogni chiave (una chiave ripetuta nell'array
  -- vale piu' riferimenti); cancellazione fisica solo a zero riferimenti.
  update gestionale.blobs b
     set refs = b.refs - k.n, updated_at = now()
    from (select key, count(*)::integer as n from unnest(p_keys) as key group by key) k
   where b.key = k.key;
  delete from gestionale.blobs where refs <= 0;
  get diagnostics removed = row_count;
  return removed;
end;
$function$;

create or replace function public.lotti_delete_docs(p_secret text, p_collection text, p_doc_ids jsonb)
returns integer
language plpgsql
security definer
set search_path to 'lotti'
as $function$
declare affected integer;
begin
  perform public.lotti_assert_secret(p_secret);
  perform gestionale.consenti_cancellazione();
  delete from lotti.lotti_documents
   where collection = p_collection
     and doc_id in (select jsonb_array_elements_text(p_doc_ids));
  get diagnostics affected = row_count;
  return affected;
end;
$function$;

create or replace function public.lotti_delete_collection(p_secret text, p_collection text)
returns integer
language plpgsql
security definer
set search_path to 'lotti'
as $function$
declare affected integer;
begin
  perform public.lotti_assert_secret(p_secret);
  perform gestionale.consenti_cancellazione();
  delete from lotti.lotti_documents where collection = p_collection;
  get diagnostics affected = row_count;
  return affected;
end;
$function$;
