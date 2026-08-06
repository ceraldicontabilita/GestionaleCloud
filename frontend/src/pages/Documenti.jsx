import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';

import api from '../api';
import { PageLayout } from '../components/PageLayout';
import DocumentViewerModal from '../components/DocumentViewerModal';
import {
  Badge,
  Button,
  Card,
  Input,
  ListaAdattiva,
  RowActions,
  Select,
  StatCard,
} from '../components/ds';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import {
  BORDER_RADIUS,
  COLORS,
  formatDateIT,
  useIsMobile,
} from '../lib/utils';

const PAGE_SIZE = 50;

const CATEGORY_COLORS = {
  f24: { bg: '#dbeafe', text: '#1e40af', icon: '📋', label: 'F24' },
  fattura: { bg: '#dcfce7', text: '#166534', icon: '🧾', label: 'Fattura' },
  fattura_estera_pdf: { bg: '#dcfce7', text: '#166534', icon: '🌍', label: 'Fattura estera' },
  busta_paga: { bg: '#fef3c7', text: '#92400e', icon: '📄', label: 'Cedolino' },
  estratto_conto: { bg: '#f3e8ff', text: '#7c3aed', icon: '🏦', label: 'Estratto conto' },
  quietanza: { bg: '#cffafe', text: '#0e7490', icon: '✅', label: 'Quietanza' },
  bonifico: { bg: '#fce7f3', text: '#be185d', icon: '💸', label: 'Bonifico' },
  cartella_esattoriale: { bg: '#fee2e2', text: '#b91c1c', icon: '⚠️', label: 'Cartella' },
  avviso_bonario: { bg: '#ffedd5', text: '#c2410c', icon: '📨', label: 'Avviso bonario' },
  dichiarazione_iva: { bg: '#e0e7ff', text: '#4338ca', icon: '📊', label: 'Dichiarazione IVA' },
  satispay: { bg: '#fce7f3', text: '#be185d', icon: '📱', label: 'Satispay' },
  contributi_inps: { bg: '#e0f2fe', text: '#0369a1', icon: '🏛️', label: 'INPS' },
  certificazione_unica: { bg: '#ecfccb', text: '#4d7c0f', icon: '👤', label: 'CU' },
  verbale: { bg: '#fee2e2', text: '#b91c1c', icon: '🚗', label: 'Verbale' },
  pagopa: { bg: '#e0f2fe', text: '#0369a1', icon: '🏛️', label: 'PagoPA' },
  paypal: { bg: '#dbeafe', text: '#1e40af', icon: '💳', label: 'PayPal' },
  altro: { bg: '#f1f5f9', text: '#475569', icon: '📄', label: 'Altro' },
};

const STATUS_LABELS = {
  nuovo: { label: 'Da collegare', variant: 'warning' },
  processato: { label: 'Processato', variant: 'success' },
  errore: { label: 'Errore', variant: 'danger' },
};

const SOURCE_LABELS = {
  email: 'Email',
  gmail: 'Gmail',
  pec: 'PEC',
  drive: 'Google Drive',
  google_drive: 'Google Drive',
  upload: 'Caricamento manuale',
  upload_manuale: 'Caricamento manuale',
  upload_ai: 'Estrazione AI',
  scheduler: 'Sincronizzazione automatica',
  non_indicata: 'Fonte non indicata',
};

const ANOMALY_LABELS = {
  identificativo_mancante: 'ID mancante',
  errore_elaborazione: 'Errore elaborazione',
  classificazione_da_verificare: 'Categoria da verificare',
  collegamento_mancante: 'Collegamento mancante',
  duplicato_segnalato: 'Possibile duplicato',
};

const formatBytes = bytes => {
  const value = Number(bytes || 0);
  if (!value) return '—';
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
};

const formatArchiveDate = value => {
  if (!value) return '—';
  const formatted = formatDateIT(value);
  return formatted && formatted !== 'Invalid Date' ? formatted : '—';
};

const sourceLabel = doc => {
  const raw = doc.source_label || doc.fonte || doc.source || (doc.email_from ? 'email' : 'non_indicata');
  return SOURCE_LABELS[String(raw).toLowerCase()] || String(raw).replaceAll('_', ' ');
};

const categoryStyle = doc => CATEGORY_COLORS[doc.category] || CATEGORY_COLORS.altro;

export default function Documenti() {
  const { anno } = useAnnoGlobale();
  const isMobile = useIsMobile();
  const [documents, setDocuments] = useState([]);
  const [categories, setCategories] = useState({});
  const [byStatus, setByStatus] = useState({});
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [page, setPage] = useState(0);
  const [category, setCategory] = useState('');
  const [status, setStatus] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [selectedDocument, setSelectedDocument] = useState(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(0);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => setPage(0), [anno, category, status]);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({
        anno: String(anno),
        limit: String(PAGE_SIZE),
        skip: String(page * PAGE_SIZE),
      });
      if (category) params.set('categoria', category);
      if (status) params.set('status', status);
      if (search) params.set('search', search);

      const response = await api.get(`/api/documenti/lista?${params.toString()}`);
      const data = response.data || {};
      setDocuments(data.documents || []);
      setCategories(data.categories || {});
      setByStatus(data.by_status || {});
      setTotal(Number(data.total || 0));
    } catch (requestError) {
      const detail = requestError.response?.data?.detail || requestError.message || 'Errore sconosciuto';
      setDocuments([]);
      setTotal(0);
      setError(String(detail));
    } finally {
      setLoading(false);
    }
  }, [anno, category, page, search, status]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const rangeStart = total ? page * PAGE_SIZE + 1 : 0;
  const rangeEnd = Math.min(total, (page + 1) * PAGE_SIZE);
  const anomalyCount = useMemo(
    () => documents.filter(doc => (doc.anomalies || []).length > 0).length,
    [documents]
  );

  const downloadDocument = async doc => {
    if (!doc.id) return;
    try {
      const response = await api.get(`/api/documenti/documento/${doc.id}/download`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.download = doc.filename || 'documento.pdf';
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (requestError) {
      toast.error('Documento non scaricabile', {
        description: requestError.response?.data?.detail || requestError.message,
      });
    }
  };

  const resetFilters = () => {
    setCategory('');
    setStatus('');
    setSearchInput('');
    setSearch('');
    setPage(0);
  };

  return (
    <PageLayout
      title="Archivio documenti"
      icon="🗂️"
      subtitle={`Consultazione documentale ${anno}: provenienza, stato, collegamenti e anomalie senza modificare i dati`}
      actions={
        <>
          <Button variant="secondary" onClick={loadData} disabled={loading}>
            {loading ? 'Aggiornamento…' : 'Aggiorna'}
          </Button>
          <Link
            to="/documenti/import"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              minHeight: 38,
              padding: '0 14px',
              borderRadius: BORDER_RADIUS.md,
              background: COLORS.primary,
              color: '#fff',
              fontSize: 13,
              fontWeight: 700,
              textDecoration: 'none',
            }}
          >
            Vai a Carica documenti
          </Link>
        </>
      }
    >
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
          gap: 12,
          marginBottom: 18,
        }}
      >
        <StatCard label={`Documenti ${anno}`} value={total} accent="primary" />
        <StatCard label="Da collegare" value={Number(byStatus.nuovo || 0)} accent="warning" />
        <StatCard label="Processati" value={Number(byStatus.processato || 0)} accent="success" />
        <StatCard label="Errori" value={Number(byStatus.errore || 0)} accent="danger" />
        <StatCard label="Anomalie nella pagina" value={anomalyCount} accent="warning" />
      </div>

      <Card style={{ marginBottom: 18 }} bodyStyle={{ padding: 16 }}>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: isMobile ? '1fr' : 'minmax(240px, 2fr) minmax(180px, 1fr) minmax(160px, 1fr) auto',
            gap: 10,
            alignItems: 'center',
          }}
        >
          <Input
            aria-label="Cerca nell'archivio"
            placeholder="Cerca nome file, mittente, oggetto, fonte o collegamento…"
            value={searchInput}
            onChange={event => setSearchInput(event.target.value)}
          />
          <Select
            aria-label="Filtra categoria"
            value={category}
            onChange={event => setCategory(event.target.value)}
          >
            <option value="">Tutte le categorie</option>
            {Object.entries(categories).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </Select>
          <Select
            aria-label="Filtra stato"
            value={status}
            onChange={event => setStatus(event.target.value)}
          >
            <option value="">Tutti gli stati</option>
            <option value="nuovo">Da collegare</option>
            <option value="processato">Processati</option>
            <option value="errore">Errori</option>
          </Select>
          <Button variant="secondary" onClick={resetFilters}>Azzera filtri</Button>
        </div>
      </Card>

      {error && (
        <div
          role="alert"
          style={{
            marginBottom: 16,
            padding: 14,
            border: `1px solid ${COLORS.danger}`,
            borderRadius: BORDER_RADIUS.md,
            background: COLORS.dangerLight,
            color: COLORS.danger,
          }}
        >
          <strong>Archivio non disponibile.</strong> {error}
          <Button variant="secondary" size="sm" onClick={loadData} style={{ marginLeft: 12 }}>
            Riprova
          </Button>
        </div>
      )}

      <Card
        title={`Documenti ${rangeStart}–${rangeEnd} di ${total}`}
        icon="📄"
        bodyStyle={{ padding: 14 }}
      >
        {loading ? (
          <div style={{ padding: 44, textAlign: 'center', color: COLORS.textMuted }}>
            Caricamento archivio…
          </div>
        ) : documents.length === 0 ? (
          <div style={{ padding: 44, textAlign: 'center', color: COLORS.textMuted }}>
            <div style={{ fontSize: 36, marginBottom: 8 }}>🗂️</div>
            <strong>Nessun documento con questi filtri.</strong>
            <div style={{ marginTop: 6 }}>Azzera i filtri oppure usa la pagina Carica documenti.</div>
          </div>
        ) : (
          <ListaAdattiva
            testId="archivio-documenti-table"
            dati={documents}
            pageSize={PAGE_SIZE}
            chiave={(doc, index) => doc.id || `${doc.filename}-${index}`}
            colonne={[
              {
                key: 'category',
                label: 'Tipo',
                ruoloCard: 'omesso',
                render: doc => {
                  const style = categoryStyle(doc);
                  return (
                    <span
                      title={doc.category_label || style.label}
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 5,
                        padding: '4px 8px',
                        borderRadius: BORDER_RADIUS.full,
                        background: style.bg,
                        color: style.text,
                        fontSize: 12,
                        fontWeight: 700,
                      }}
                    >
                      {style.icon} {style.label}
                    </span>
                  );
                },
              },
              {
                key: 'filename',
                label: 'Documento',
                ruoloCard: 'titolo',
                render: doc => (
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 700, overflowWrap: 'anywhere' }}>
                      {doc.filename || 'Documento senza nome'}
                    </div>
                    {(doc.email_subject || doc.email_from) && (
                      <div style={{ marginTop: 3, fontSize: 11, color: COLORS.textMuted }}>
                        {[doc.email_subject, doc.email_from].filter(Boolean).join(' · ')}
                      </div>
                    )}
                  </div>
                ),
              },
              {
                key: 'source_label',
                label: 'Provenienza',
                ruoloCard: 'sottotitolo',
                render: doc => sourceLabel(doc),
              },
              {
                key: 'archive_date',
                label: 'Data',
                ruoloCard: 'dettaglio',
                iconaCard: '📅',
                render: doc => formatArchiveDate(doc.archive_date),
              },
              {
                key: 'size_bytes',
                label: 'Dimensione',
                ruoloCard: 'dettaglio',
                iconaCard: '💾',
                align: 'right',
                render: doc => formatBytes(doc.size_bytes),
              },
              {
                key: 'status',
                label: 'Stato e collegamento',
                ruoloCard: 'dettaglio',
                render: doc => {
                  const statusStyle = STATUS_LABELS[doc.status] || STATUS_LABELS.nuovo;
                  return (
                    <div style={{ display: 'grid', gap: 4 }}>
                      <Badge variant={statusStyle.variant}>{statusStyle.label}</Badge>
                      {doc.linked_to && (
                        <span style={{ fontSize: 11, color: COLORS.textMuted }}>
                          Collegato a: {String(doc.linked_to).replaceAll('_', ' ')}
                        </span>
                      )}
                      {(doc.anomalies || []).map(anomaly => (
                        <span key={anomaly} style={{ fontSize: 11, color: COLORS.warning }}>
                          ⚠ {ANOMALY_LABELS[anomaly] || anomaly}
                        </span>
                      ))}
                    </div>
                  );
                },
              },
              {
                key: 'actions',
                label: 'Consultazione',
                ruoloCard: 'azioni',
                align: 'center',
                render: doc => (
                  <RowActions style={{ justifyContent: 'center' }}>
                    <Button
                      variant="info"
                      size="sm"
                      disabled={!doc.id}
                      onClick={() => setSelectedDocument(doc)}
                    >
                      Vedi
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={!doc.id}
                      onClick={() => downloadDocument(doc)}
                    >
                      Scarica
                    </Button>
                  </RowActions>
                ),
              },
            ]}
          />
        )}

        {!loading && total > 0 && (
          <div
            aria-label="Paginazione archivio"
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: 12,
              marginTop: 16,
              paddingTop: 14,
              borderTop: `1px solid ${COLORS.border}`,
            }}
          >
            <span style={{ fontSize: 12, color: COLORS.textMuted }}>
              Pagina {page + 1} di {totalPages} · {rangeStart}–{rangeEnd} di {total}
            </span>
            <div style={{ display: 'flex', gap: 8 }}>
              <Button
                variant="secondary"
                size="sm"
                disabled={page === 0}
                onClick={() => setPage(current => Math.max(0, current - 1))}
              >
                Precedente
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={page + 1 >= totalPages}
                onClick={() => setPage(current => current + 1)}
              >
                Successiva
              </Button>
            </div>
          </div>
        )}
      </Card>

      <div
        style={{
          marginTop: 16,
          padding: 14,
          borderRadius: BORDER_RADIUS.md,
          background: COLORS.infoLight,
          color: COLORS.info,
          fontSize: 13,
        }}
      >
        L’Archivio non importa, riclassifica o elimina documenti. Le acquisizioni passano soltanto da
        <strong> Carica documenti</strong>; le anomalie restano visibili e verificabili.
      </div>

      {selectedDocument && (
        <DocumentViewerModal
          title={selectedDocument.filename || 'Documento'}
          subtitle={`${selectedDocument.category_label || categoryStyle(selectedDocument).label} · ${sourceLabel(selectedDocument)}`}
          fetchUrl={`/api/documenti/documento/${selectedDocument.id}/download`}
          onClose={() => setSelectedDocument(null)}
          onDownload={() => downloadDocument(selectedDocument)}
          maxWidth={1000}
        />
      )}
    </PageLayout>
  );
}
