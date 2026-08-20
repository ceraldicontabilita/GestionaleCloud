import React, { useEffect, useRef, useState } from 'react';
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
  const [pdfUploading, setPdfUploading] = useState(false);
  const [recalculating, setRecalculating] = useState(false);
  const [drivers, setDrivers] = useState([]);
  const [selectedDriver, setSelectedDriver] = useState('');
  const [linkingDriver, setLinkingDriver] = useState(false);
  const [correctedAmount, setCorrectedAmount] = useState('');
  const [savingAmount, setSavingAmount] = useState(false);
  const pdfInputRef = useRef(null);

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

  const reload = async () => {
    const res = await api.get(`/api/verbali-noleggio/dettaglio/${verbaleId}`);
    setVerbale(res.data || null);
  };

  useEffect(() => {
    api.get('/api/dipendenti').then(res => {
      const items = res.data?.dipendenti || res.data;
      setDrivers(Array.isArray(items) ? items : []);
    }).catch(() => {});
  }, []);

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

  const uploadVerbalePdf = async event => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setPdfUploading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      await api.post(`/api/verbali-noleggio/associa-pdf/${encodeURIComponent(verbaleId)}`, form);
      await reload();
      toast.success('PDF del verbale associato e riletto');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Impossibile associare il PDF');
    } finally {
      setPdfUploading(false);
    }
  };

  const recalculateFromPdf = async () => {
    setRecalculating(true);
    try {
      const res = await api.post(`/api/verbali-noleggio/ricalcola-pdf/${encodeURIComponent(verbaleId)}`);
      await reload();
      toast.success(`PDF riletto: importo ${formatEuro(res.data?.importo || 0)}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Rilettura PDF non riuscita');
    } finally {
      setRecalculating(false);
    }
  };

  const linkDriver = async (automatic = false) => {
    if (!verbale?.targa) return;
    if (!automatic && !selectedDriver) return;
    setLinkingDriver(true);
    try {
      const url = automatic
        ? `/api/auto-repair/inferisci-targa-driver-da-fatture?targa=${encodeURIComponent(verbale.targa)}`
        : `/api/auto-repair/collega-targa-driver?targa=${encodeURIComponent(verbale.targa)}&driver_id=${encodeURIComponent(selectedDriver)}`;
      const res = await api.post(url);
      if (res.data?.requires_review) {
        toast.error(res.data.message || 'Associazione non univoca');
      } else {
        await reload();
        toast.success(res.data?.message || 'Driver associato');
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Associazione driver non riuscita');
    } finally {
      setLinkingDriver(false);
    }
  };

  const saveCorrectedAmount = async () => {
    const amount = Number(String(correctedAmount).replace(',', '.'));
    if (!Number.isFinite(amount) || amount <= 0) {
      toast.error('Inserisci un importo valido');
      return;
    }
    setSavingAmount(true);
    try {
      await api.post(`/api/verbali-noleggio/correggi-importo/${encodeURIComponent(verbaleId)}`, {
        importo: amount, fonte: 'verifica_pdf_operatore',
      });
      await reload();
      setCorrectedAmount('');
      toast.success('Importo corretto e registrato nello storico');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Correzione importo non riuscita');
    } finally {
      setSavingAmount(false);
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

      <PageSection title="Documento originale e importo">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
          <input ref={pdfInputRef} data-testid="associate-verbale-pdf-input" type="file" accept="application/pdf" onChange={uploadVerbalePdf} style={{ display: 'none' }} />
          <Button variant="primary" disabled={pdfUploading} onClick={() => pdfInputRef.current?.click()}>
            {pdfUploading ? 'Associazione…' : 'Associa PDF verbale'}
          </Button>
          {pdfCount > 0 && (
            <Button variant="outline" onClick={recalculateFromPdf} disabled={recalculating} data-testid="recalculate-verbale-pdf">
              {recalculating ? 'Rilettura…' : 'Rileggi importo dal PDF'}
            </Button>
          )}
          <input aria-label="Importo corretto dal PDF" inputMode="decimal" placeholder="Es. 51,64" value={correctedAmount} onChange={e => setCorrectedAmount(e.target.value)} style={{ width: 130, padding: '8px 10px' }} />
          <Button variant="success" disabled={!correctedAmount || savingAmount} onClick={saveCorrectedAmount}>
            {savingAmount ? 'Salvataggio…' : 'Salva importo verificato'}
          </Button>
          <span style={{ fontSize: 12, color: COLORS.textMuted }}>
            Il PDF originale è la fonte dell’importo; eventuali conflitti OCR restano tracciati.
          </span>
        </div>
      </PageSection>

      <PageSection title="Associazione targa e driver">
        {!verbale?.targa ? (
          <div style={{ color: COLORS.warning }}>Prima occorre ricavare o inserire la targa dal verbale.</div>
        ) : (
          <div style={{ display: 'grid', gap: 10 }}>
            <div><strong>Targa:</strong> {verbale.targa} · <strong>Driver:</strong> {verbale.driver_nome || verbale.driver || verbale.driver_dettaglio?.nome || 'non associato'}</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              <select value={selectedDriver} onChange={e => setSelectedDriver(e.target.value)} aria-label="Driver per la targa">
                <option value="">Scegli driver…</option>
                {drivers.map(d => <option key={d.id} value={d.id}>{d.nome_completo || d.name || `${d.nome || ''} ${d.cognome || ''}`.trim()}</option>)}
              </select>
              <Button variant="primary" disabled={!selectedDriver || linkingDriver} onClick={() => linkDriver(false)}>Associa alla targa</Button>
              <Button variant="outline" disabled={linkingDriver} onClick={() => linkDriver(true)}>Trova dalla fattura noleggio</Button>
            </div>
            <div style={{ fontSize: 12, color: COLORS.textMuted }}>
              L’automatismo si applica a tutti i verbali della stessa targa solo se una fattura cita in modo univoco targa e driver; più candidati richiedono scelta manuale.
            </div>
          </div>
        )}
      </PageSection>

      <PageSection title="Note">
        <div style={{ color: COLORS.textMuted, lineHeight: 1.6 }}>
          {verbale?.note || 'Nessuna nota disponibile per questo verbale.'}
        </div>
      </PageSection>

      {(verbale?.stato_pratica || verbale?.pagato_documentalmente !== undefined || verbale?.review_questions?.length) && (
        <PageSection title="Stato probatorio e verifiche">
          <div style={{ display: 'grid', gap: 8, fontSize: 13 }}>
            <div><strong>Stato pratica:</strong> {verbale?.stato_pratica || 'APERTO'}</div>
            <div><strong>Pagamento documentale:</strong> {verbale?.pagato_documentalmente ? 'Sì' : 'No'}</div>
            <div><strong>Banca verificata:</strong> {verbale?.banca_verificata ? 'Sì' : 'No'}</div>
            <div><strong>Fonte pagamento:</strong> {verbale?.fonte_pagamento || 'Non collegata'}</div>
            {verbale?.origine === 'AVVISO_PAGOPA' && (
              <div style={{ color: COLORS.warning }}>
                Avviso PagoPA: verbale originale non ancora acquisito. La targa non determina automaticamente il driver.
              </div>
            )}
            {verbale?.review_questions?.length > 0 && (
              <div style={{ marginTop: 6 }}>
                <strong>Domande da confermare</strong>
                <ul style={{ margin: '6px 0 0 18px' }}>
                  {verbale.review_questions.map((item) => <li key={item.key}>{item.question}</li>)}
                </ul>
              </div>
            )}
          </div>
        </PageSection>
      )}

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
