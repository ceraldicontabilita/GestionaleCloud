-- Lookup puntuali dell'importatore cedolini: niente scansione/materializzazione
-- dell'intera collection per deduplicare un singolo originale.
CREATE INDEX IF NOT EXISTS idx_documents_collection_file_hash
    ON gestionale.documents (collection, (data->>'file_hash'))
    WHERE coalesce(data->>'file_hash', '') <> '';

-- Rende puntuale anche la risoluzione dell'originale Drive e le quadrature.
CREATE INDEX IF NOT EXISTS idx_documents_collection_drive_file_id
    ON gestionale.documents (collection, (data->>'drive_file_id'))
    WHERE coalesce(data->>'drive_file_id', '') <> '';
