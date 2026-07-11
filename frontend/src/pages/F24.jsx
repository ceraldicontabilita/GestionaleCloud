import React, { useCallback, useEffect, useRef, useState } from 'react';
import api from '../api';
import { PageLayout } from '../components/PageLayout';
import { Button, Badge, Card } from '../components/ds';
import { formatEuro, formatDateIT, COLORS } from '../lib/utils';
import { FileText, RefreshCw, Upload, AlertTriangle } from 'lucide-react';

function normalizeList(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.data)) return payload.data;
  if (Array.isArray(payload?.items)) return payload.items;
  if (Array.isArray(payload?.f24)) return payload.f24;
  return [];
}

function getImporto(item) {
  return (
    item?.importo ??
    item?.totale ??
    item?.saldo ??
    item?.totali?.saldo_netto ??
    item?.totali?.totale_generale ??
    0
  );
}

function getScadenza(item) {
  return (
    item?.scadenza ??
    item?.data_scadenza ??
    item?.dati_generali?.data_scadenza ??
    item?.data_versamento ??
    null
  );
}

function getStato(item) {
  return String(item?.stato_pagamento ?? item?.stato ?? item?.status ?? 'da_verificare').toLowerCase();
}

export default function F24() {
  const fileInputRef = useRef(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await api.get('/api/f24');
      setItems(normalizeList(response.data));
    } catch (err) {
      setItems([]);
      setError(err.response?.data?.detail || err.message || 'Impossibile caricare gli F24.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const uploadFile = async event => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      setError('Caricare un file PDF.');
      return;
    }

    setUploading(true);
    setError('');
    setMessage('');
    const formData = new FormData();
    formData.append('file', file);

    try {
      await api.post('/api/f24/upload-pdf', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setMessage(`F24 ${file.name} caricato correttamente.`);
      await load();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Caricamento F24 non riuscito.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <PageLayout title="F24 e tributi" icon="📄" subtitle="Archivio, scadenze e caricamento documenti F24">
      <div data-testid="f24-page" style={{ display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf,.pdf"
            onChange={uploadFile}
            style={{ display: 'none' }}
            data-testid="f24-file-input"
          />
          <Button
            variant="primary"
            iconLeft={<Upload size={16} />}
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            data-testid="btn-upload-f24"
          >
            {uploading ? 'Caricamento...' : 'Carica F24 PDF'}
          </Button>
          <Button
            variant="secondary"
            iconLeft={<RefreshCw size={16} />}
            onClick={load}
            disabled={loading}
            data-testid="btn-refresh-f24"
          >
            Aggiorna
          </Button>
        </div>

        {message && (
          <div role="status" style={{ padding: 12, borderRadius: 8, background: COLORS.successLight, color: COLORS.success }}>
            {message}
          </div>
        )}
        {error && (
          <div role="alert" style={{ padding: 12, borderRadius: 8, background: COLORS.dangerLight, color: COLORS.danger, display: 'flex', gap: 8, alignItems: 'center' }}>
            <AlertTriangle size={18} />
            <span>{error}</span>
          </div>
        )}

        {loading ? (
          <Card><div style={{ padding: 20 }}>Caricamento F24...</div></Card>
        ) : items.length === 0 ? (
          <Card>
            <div style={{ padding: 24, textAlign: 'center', color: COLORS.textMuted }}>
              <FileText size={32} style={{ marginBottom: 8 }} />
              <div>Nessun F24 presente nell'archivio.</div>
            </div>
          </Card>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 280px), 1fr))', gap: 12 }}>
            {items.map((item, index) => {
              const id = item.id || item._id || item.f24_key || `${index}`;
              const stato = getStato(item);
              const pagato = stato.includes('pagato') || stato === 'paid';
              return (
                <Card key={id}>
                  <div style={{ padding: 16, minWidth: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontWeight: 700, overflowWrap: 'anywhere' }}>
                          {item.descrizione || item.file_name || item.original_filename || item.dati_generali?.file_name || 'F24'}
                        </div>
                        <div style={{ marginTop: 6, fontSize: 13, color: COLORS.textMuted }}>
                          Scadenza: {formatDateIT(getScadenza(item)) || 'non disponibile'}
                        </div>
                      </div>
                      <Badge variant={pagato ? 'success' : 'warning'}>{stato.replaceAll('_', ' ')}</Badge>
                    </div>
                    <div style={{ marginTop: 14, fontSize: 22, fontWeight: 700 }}>{formatEuro(getImporto(item))}</div>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </PageLayout>
  );
}
