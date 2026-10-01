
create table if not exists hr.app_cedolini_prima_prova_20260930 as
  select id, doc - 'pdf_data' as doc, now() salvato_il from hr.app_cedolini;
create table if not exists gestionale.documents_prima_prova_20260930 as
  select collection, id, data - 'pdf_data' as data, updated_at, now() salvato_il
  from gestionale.documents where collection in ('cedolini','quietanze_f24');

drop trigger if exists prova_origine on hr.app_cedolini;
create trigger prova_origine before insert or update on hr.app_cedolini
  for each row execute function hr.prova_cedolino_trg();

drop trigger if exists prova_origine on gestionale.documents;
create trigger prova_origine before insert or update on gestionale.documents
  for each row when (new.collection in ('cedolini','quietanze_f24'))
  execute function gestionale.prova_documento_trg();

