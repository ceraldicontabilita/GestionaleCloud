import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../api';
import { PageLayout, PageSection } from '../components/PageLayout';
import DocumentViewerModal from '../components/DocumentViewerModal';
import { formatEuro, COLORS, BORDER_RADIUS } from '../lib/utils';
import { Button, Badge } from '../components/ds';
import { toast } from 'sonner';

export default function DettaglioVerbale() {
  const { numeroVerbale, prefisso, numero } = useParams();
  const navigate = useNavigate();
  const verbaleId = prefisso && numero ? `${prefisso}/${numero}` : numeroVerbale;
  const [verbale, setVerbale] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [openingPdf, setOpeningPdf] = useState(null);
  const [pdfViewer, setPdfViewer] = useState(null);

  useEffect(() => {
    let alive = true;

    async function load() {
      setLoading(true);
      setError('');
      try {
        const res = await api.get(`/api/verbali-noleggio/dettaglio/${verbaleId}`);
        if (alive) setVerbale(res.data || null);
      } catch (e) {
        if (alive) setError(e.response?.data?.detail || e.message || 'Errore caricamento verbale');
      } finally {
        if (alive) setLoading(false);
      }
    }

    load();
    return () => {
      alive = false;
    };
  }, [verbaleId]);

  useEffect(() => () => {
    if (pdfViewer?.src) URL.revokeObjectURL(pdfViewer.src);
  }, [pdfViewer]);

  const openPdf = async (pdf, idx) => {
    const numeroPdf = verbale?.numero_verbale || verbaleId;
    const indice = pdf.indice ?? idx;
    setOpeningPdf(indice);
    try {
      const response = await api.get(
        `/api/verbali-noleggio/pdf/${encodeURIComponent(numeroPdf)}?indice=${indice}`
      );
      const encoded = response.data?.content_base64;
      if (!encoded) {
        toast.error('PDF non disponibile');
        return;
      }
      const raw = atob(encoded);
      const bytes = new Uint8Array(raw.length);
      for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
      const src = URL.createObjectURL(new Blob([bytes], { type: 'application/pdf' }));
      setPdfViewer({
        src,
        filename: pdf.filename || pdf.nome || `verbale_${numeroPdf}.pdf`,
        title: pdf.nome || pdf.filename || `Documento verbale ${numeroPdf}`,
      });
    } catch (e) {
      toast.error(`Errore apertura PDF: ${e.response?.data?.detail || e.message}`);
    } finally {
      setOpeningPdf(null);
    }
  };

  if (loading) {
    return (
      <PageLayout title="Dettaglio verbale" subtitle={`Caricamento verbale ${verbaleId}`}>
        <div style={{ padding: 32, color: COLORS.textMuted }}>Caricamento...</div>
      </PageLayout>
    );
  }

  if (error) {
    return (
      <PageLayout title="Dettaglio verbale" subtitle={`Verbale ${verbaleId}`}>
        <PageSection title="Errore">
          <div style={{ color: COLORS.danger, marginBottom: 16 }}>{error}</div>
          <Button variant="primary" onClick={() => navigate(-1)}>
            Torna indietro
          </Button>
        </PageSection>
      </PageLayout>
    );
  }

  const pdfCount = verbale?.pdf_disponibili?.length || 0;
  const stato = verbale?.stato_pagamento || verbale?.stato || 'n/d';

  return (
    <PageLayout
      title="Dettaglio verbale"
      subtitle={`Verbale ${verbale?.numero_verbale || verbaleId}`}
      actions={
        <Button variant="secondary" onClick={() => navigate(-1)}>
          Indietro
        </Button>
      }
    >
      <PageSection title="Riepilogo">
        <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
          <div><strong>Numero</strong><div>{verbale?.numero_verbale || verbaleId}</div></div>
          <div><strong>Fornitore</strong><div>{verbale?.fornitore || '-'}</div></div>
          <div><strong>Targa</strong><div>{verbale?.targa || '-'}</div></div>
          <div><strong>Stato</strong><div><Badge variant={stato === 'pagato' ? 'success' : stato === 'sospeso' ? 'warning' : 'neutral'}>{stato}</Badge></div></div>
          <div><strong>Importo</strong><div>{formatEuro(verbale?.importo || verbale?.totale || 0)}</div></div>
          <div><strong>PDF disponibili</strong><div>{pdfCount}</div></div>
        </div>
      </PageSection>

      <PageSection title="Note">
        <div style={{ color: COLORS.textMuted, lineHeight: 1.6 }}>
          {verbale?.note || 'Nessuna nota disponibile per questo verbale.'}
        </div>
      </PageSection>

      {pdfCount > 0 && (
        <PageSection title="Documenti PDF">
          <div style={{ display: 'grid', gap: 8 }}>
            {verbale.pdf_disponibili.map((pdf, idx) => (
              <div
                key={pdf.id || idx}
                style={{
                  padding: 12,
                  border: `1px solid ${COLORS.border}`,
                  borderRadius: BORDER_RADIUS.md,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 12,
                }}
              >
                <div>
                  <div style={{ fontWeight: 700 }}>{pdf.nome || pdf.filename || `PDF ${idx + 1}`}</div>
                  <div style={{ fontSize: 12, color: COLORS.textMuted }}>{pdf.descrizione || 'Documento associato al verbale'}</div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={openingPdf === (pdf.indice ?? idx)}
                  onClick={() => openPdf(pdf, idx)}
                  data-testid={`open-verbale-pdf-${pdf.indice ?? idx}`}
                >
                  {openingPdf === (pdf.indice ?? idx) ? 'Apertura…' : 'Apri'}
                </Button>
              </div>
            ))}
          </div>
        </PageSection>
      )}

      {pdfViewer && (
        <DocumentViewerModal
          title={pdfViewer.title}
          src={pdfViewer.src}
          documentType="verbale"
          onDownload={() => {
            const link = document.createElement('a');
            link.href = pdfViewer.src;
            link.download = pdfViewer.filename;
            link.click();
          }}
          onClose={() => setPdfViewer(null)}
        />
      )}
    </PageLayout>
  );
}
