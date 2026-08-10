import React, { useEffect, useState } from 'react';
import api from '../api';
import { Card, Button, Badge } from './ds';
import DocumentViewerModal from './DocumentViewerModal';

export default function LinkedEvidencePanel({ entityType, entityId }) {
  const [links, setLinks] = useState([]);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  useEffect(() => {
    if (!entityType || !entityId) return;
    api.get(`/api/situazione-fiscale/evidence/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`)
      .then(response => setLinks(response.data?.links || []))
      .catch(requestError => setError(requestError.response?.data?.detail || requestError.message));
  }, [entityType, entityId]);

  return (
    <Card bodyStyle={{ padding: 16 }}>
      <h3 style={{ marginTop: 0 }}>Prove collegate</h3>
      <p style={{ color: '#64748b', fontSize: 13 }}>
        Il collegamento documenta la fonte; da solo non certifica pagamento o correttezza fiscale.
      </p>
      {error && <div role="alert">{String(error)}</div>}
      {!error && links.length === 0 && <div>Nessuna prova collegata.</div>}
      {links.map(link => (
        <div key={link.id} style={{ borderTop: '1px solid #e2e8f0', padding: '12px 0' }}>
          <Badge variant={link.status === 'confirmed' ? 'success' : 'warning'}>{link.status}</Badge>
          {(link.evidence || []).map(item => (
            <div key={item.id} style={{ marginTop: 8 }}>
              <strong>{item.field}</strong>: {String(item.normalized_value ?? item.raw_value ?? '—')}
              {' '}<Button size="sm" variant="secondary" onClick={() => setSelected(item)}>
                Apri pagina {item.page_number}
              </Button>
            </div>
          ))}
        </div>
      ))}
      {selected && (
        <DocumentViewerModal
          title={`Prova: ${selected.field || selected.field_name || 'documento fiscale'}`}
          subtitle={`Pagina ${selected.page_number}`}
          fetchUrl={`/api/fiscal/documents/${encodeURIComponent(selected.document_id)}/content`}
          pageNumber={selected.page_number}
          onClose={() => setSelected(null)}
        />
      )}
    </Card>
  );
}
