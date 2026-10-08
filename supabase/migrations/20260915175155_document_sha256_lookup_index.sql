-- Le pipeline fiscali deduplicano sullo SHA-256 forte con una lettura puntuale.
CREATE INDEX IF NOT EXISTS idx_documents_collection_sha256
    ON gestionale.documents (collection, (data->>'sha256'))
    WHERE coalesce(data->>'sha256', '') <> '';
