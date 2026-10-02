-- Collega al protocollo Drive i documenti F24/quietanze che hanno drive_file_id ma non sono ancora collegati
-- (stessa regola di 20260915224500_f24_drive_originals.sql; idempotente).
update gestionale.protocollo_drive p
set collegamento_tipo = d.collection,
    collegamento_id = d.id,
    aggiornato_il = now()
from gestionale.documents d
where d.collection in ('f24_unificato', 'quietanze_f24')
  and d.data->>'drive_file_id' = p.drive_id
  and p.stato = 'attivo'
  and p.collegamento_id is null;
