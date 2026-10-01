
create or replace view verifica.prove as
  select 'hr.app_cedolini'::text tabella, id record_id, doc->>'nome_dipendente' soggetto,
         (doc->>'anno')::int anno, (doc->>'mese')::int mese, doc->>'netto' valore,
         doc->'prova'->>'stato' stato, doc->'prova'->>'drive_id' drive_id,
         (doc->'prova'->>'pagina_da')::int pagina, doc->'prova'->>'testo_letto' testo_letto,
         doc->'prova'->'motivi' motivi
  from hr.app_cedolini
  union all
  select 'documents.cedolini', id, data->>'nome_dipendente', nullif(data->>'anno','')::int, nullif(data->>'mese','')::int, data->>'netto',
         data->'prova'->>'stato', data->'prova'->>'drive_id', (data->'prova'->>'pagina_da')::int, data->'prova'->>'testo_letto', data->'prova'->'motivi'
  from gestionale.documents where collection='cedolini'
  union all
  select 'documents.quietanze_f24', id, data->>'filename', null, null, data->>'saldo',
         data->'prova'->>'stato', data->'prova'->>'drive_id', (data->'prova'->>'pagina_da')::int, data->'prova'->>'testo_letto', data->'prova'->'motivi'
  from gestionale.documents where collection='quietanze_f24';

-- Solo i dati con prova completa: le somme si fanno da qui
create or replace view verifica.dati_provati as
  select * from verifica.prove where stato = 'completa';

create or replace view verifica.prove_riepilogo as
  select tabella, stato, count(*) n from verifica.prove group by 1,2;

