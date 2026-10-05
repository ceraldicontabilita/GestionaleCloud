import React, { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../api';
import { PageLayout, PageSection } from '../components/PageLayout';
import ApriOriginale, { VisoreOriginale } from '../components/ApriOriginale';
import { urlOriginale, euroOppure } from '../lib/vista';
import { formatDateIT, COLORS, BORDER_RADIUS } from '../lib/utils';
import { Button, Badge } from '../components/ds';
import ModalFattura from '../components/ModalFattura';
import { toast } from 'sonner';

const ETICHETTE_DOCUMENTO_DRIVE = {
  verbale: 'Verbale', notifica: 'Notifica', quietanza: 'Quietanza', bonifico: 'Bonifico',
  avviso_pagopa: 'Avviso pagoPA', ricevuta: 'Ricevuta di pagamento', presa_in_carico: 'Presa in carico', altro: 'Documento',
};

export default function DettaglioVerbale() {
  const { numeroVerbale, prefisso, numero } = useParams();
  const navigate = useNavigate();
  const verbaleId = prefisso && numero ? `${prefisso}/${numero}` : numeroVerbale;
  const [verbale, setVerbale] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [pdfViewer, setPdfViewer] = useState(null);
  const [fatturaAperta, setFatturaAperta] = useState(false);
  const [pdfUploading, setPdfUploading] = useState(false);
  const [recalculating, setRecalculating] = useState(false);
  const [drivers, setDrivers] = useState([]);
  const [showDriverTools, setShowDriverTools] = useState(false);
  const [selectedDriver, setSelectedDriver] = useState('');
  const [linkingDriver, setLinkingDriver] = useState(false);
  const [correctedAmount, setCorrectedAmount] = useState('');
  const [savingAmount, setSavingAmount] = useState(false);
  const [trasgressore, setTrasgressore] = useState('');
  const [savingTrasgressore, setSavingTrasgressore] = useState(false);
  const pdfInputRef = useRef(null);

  useEffect(() => {
    let alive = true;

    async function load() {
      setLoading(true);
      setError('');
      try {
        const res = await api.get(`/api/verbali-noleggio/dettaglio/${verbaleId}`);
        if (alive) {
          setVerbale(res.data || null);
          setTrasgressore(res.data?.trasgressore || '');
        }
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
    setTrasgressore(res.data?.trasgressore || '');
  };

  const saveTrasgressore = async () => {
    const value = trasgressore.trim();
    if (value.length < 3) return;
    setSavingTrasgressore(true);
    try {
      await api.post(`/api/verbali-noleggio/correggi-trasgressore/${encodeURIComponent(verbaleId)}`, {
        trasgressore: value,
        fonte: 'verifica_documento_operatore',
      });
      await reload();
      toast.success('Trasgressore registrato');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Salvataggio trasgressore non riuscito');
    } finally {
      setSavingTrasgressore(false);
    }
  };

  const openDriverTools = async () => {
    setShowDriverTools(true);
    if (drivers.length > 0) return;
    try {
      const res = await api.get('/api/dipendenti');
      const items = res.data?.dipendenti || res.data;
      setDrivers(Array.isArray(items) ? items : []);
    } catch {
      toast.error('Elenco driver non disponibile');
    }
  };

  // L'originale lo apre l'endpoint unico (DRV-04): il viewer lo scarica per id,
  // il PDF non passa piu' dal payload del verbale.
  const openPdf = (pdf, idx) => {
    const numeroPdf = verbale?.numero_verbale || verbaleId;
    const indice = pdf.indice ?? idx;
    setPdfViewer({
      url: urlOriginale({ tipo: 'verbale', id: numeroPdf, indice }),
      title: pdf.nome || pdf.filename || `Documento verbale ${numeroPdf}`,
    });
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
      toast.success(`PDF riletto: importo ${euroOppure(res.data?.importo)}`);
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
  const fascicolo = verbale?.fascicolo || {};
  const hasStructuredFile = Boolean(verbale?.fascicolo);
  const evidence = [
    {
      key: 'verbale', title: 'Verbale originale',
      present: hasStructuredFile ? fascicolo.verbale?.presente : pdfCount > 0,
      detail: fascicolo.verbale?.documento?.filename || 'PDF originale non ancora collegato',
      document: fascicolo.verbale?.documento || (!hasStructuredFile ? verbale?.pdf_disponibili?.[0] : null),
    },
    {
      key: 'notifica', title: 'Notifica scaricata',
      present: fascicolo.notifica?.presente,
      detail: fascicolo.notifica?.documento?.filename || fascicolo.notifica?.riferimento_archivio || fascicolo.notifica?.data || 'Non presente',
      document: fascicolo.notifica?.documento,
    },
    {
      key: 'banca', title: 'Pagamento in banca',
      present: fascicolo.pagamento_banca?.presente,
      detail: fascicolo.pagamento_banca?.movimento
        ? `${formatDateIT(fascicolo.pagamento_banca.movimento.data_contabile || fascicolo.pagamento_banca.movimento.data) || 'Data non disponibile'} · ${euroOppure(fascicolo.pagamento_banca.movimento.importo == null ? null : Math.abs(fascicolo.pagamento_banca.movimento.importo))} · ${fascicolo.pagamento_banca.movimento.descrizione || 'Movimento bancario'}`
        : 'Nessun movimento bancario collegato',
    },
    {
      key: 'quietanza', title: 'Quietanza PartenoPay / PagoPA',
      present: fascicolo.quietanza?.presente,
      detail: fascicolo.quietanza?.documento?.filename || fascicolo.quietanza?.riferimento_archivio || fascicolo.quietanza?.fonte || 'Non presente',
      document: fascicolo.quietanza?.documento,
    },
  ];

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
          <div><strong>Trasgressore</strong><div>{verbale?.trasgressore || '-'}</div></div>
          <div><strong>Stato</strong><div><Badge variant={stato === 'pagato' ? 'success' : stato === 'sospeso' ? 'warning' : 'neutral'}>{stato}</Badge></div></div>
          <div><strong>Importo</strong><div>{euroOppure(verbale?.importo ?? verbale?.totale)}</div></div>
          <div><strong>PDF disponibili</strong><div>{pdfCount}</div></div>
        </div>
      </PageSection>

      {(verbale?.notifiche_pec || []).length > 0 && (
        <PageSection title="Notifica PEC e termini di ricorso">
          {verbale.notifiche_pec.map((n) => (
            <div key={n.upec_id || n.oggetto} data-testid="notifica-pec" style={{ border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.md, padding: 14, marginBottom: 10 }}>
              <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
                <div><strong>Notificato il</strong><div>{formatDateIT(n.data_notifica) || '-'}</div></div>
                <div><strong>Da</strong><div style={{ overflowWrap: 'anywhere' }}>{n.ente_mittente || '-'}</div></div>
                <div><strong>Pagamento ridotto entro</strong><div>{formatDateIT(n.scadenze?.pagamento_ridotto) || '-'}</div></div>
                <div><strong>Giudice di Pace entro</strong><div>{formatDateIT(n.scadenze?.ricorso_giudice_di_pace) || '-'}</div></div>
                <div><strong>Prefetto entro</strong><div>{formatDateIT(n.scadenze?.ricorso_prefetto) || '-'}</div></div>
              </div>
              <div style={{ marginTop: 8, fontSize: 12, color: COLORS.textMuted }}>
                Copia conforme e relata di notifica sono nel fascicolo qui sotto.
              </div>
            </div>
          ))}
        </PageSection>
      )}

      <PageSection title="Fascicolo del verbale">
        <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
          {evidence.map((item) => (
            <div key={item.key} style={{ border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.md, padding: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                <strong>{item.title}</strong>
                <Badge variant={item.present ? 'success' : 'neutral'}>{item.present ? 'Presente' : 'Mancante'}</Badge>
              </div>
              <div style={{ marginTop: 8, minHeight: 38, fontSize: 13, color: COLORS.textMuted, overflowWrap: 'anywhere' }}>{item.detail}</div>
              {item.document && (
                <Button
                  variant="outline"
                  size="sm"
                  style={{ marginTop: 10 }}
                  onClick={() => openPdf(item.document, item.document.indice || 0)}
                  data-testid={`open-verbale-pdf-${item.document.indice ?? 0}`}
                >
                  Apri documento
                </Button>
              )}
            </div>
          ))}
        </div>
        <div style={{ marginTop: 10, fontSize: 12, color: COLORS.textMuted }}>
          Le quattro prove restano separate: la quietanza non sostituisce il movimento bancario e un movimento bancario non sostituisce la quietanza.
        </div>
      </PageSection>

      {(verbale?.documenti_drive?.length || 0) > 0 && (
        <PageSection title="Documenti collegati (Drive)">
          <div style={{ display: 'grid', gap: 8 }} data-testid="documenti-drive">
            {verbale.documenti_drive.map((d) => (
              <div key={d.drive_id} style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', justifyContent: 'space-between', border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.md, padding: '8px 12px' }}>
                <div style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
                  <Badge variant="neutral">{ETICHETTE_DOCUMENTO_DRIVE[d.tipo] || 'Documento'}</Badge>{' '}
                  <span style={{ fontSize: 13 }}>{d.nome || d.drive_id}</span>
                </div>
                <ApriOriginale driveId={d.drive_id} titolo={d.nome || 'Documento'} documentType="verbale" testId={`apri-drive-${d.drive_id}`} />
              </div>
            ))}
          </div>
        </PageSection>
      )}

      {verbale?.fattura_id && (
        <PageSection title="Fattura collegata">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: 13 }} data-testid="fattura-collegata">
              Fattura {verbale.fattura_numero || verbale.fattura_info?.invoice_number || verbale.fattura_id}
              {verbale.fattura_info?.supplier_name ? ` · ${verbale.fattura_info.supplier_name}` : ''}
            </span>
            <Button variant="outline" size="sm" style={{ minHeight: 44 }} onClick={() => setFatturaAperta(true)} data-testid="apri-fattura-collegata">
              Apri fattura
            </Button>
          </div>
        </PageSection>
      )}

      <PageSection title="Trasgressore indicato nel verbale">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          <input
            value={trasgressore}
            onChange={event => setTrasgressore(event.target.value)}
            placeholder="Ragione sociale o nominativo"
            aria-label="Trasgressore"
            style={{ minWidth: 'min(320px, 100%)', padding: '10px 12px', borderRadius: 8, border: `1px solid ${COLORS.border}` }}
          />
          <Button variant="primary" disabled={savingTrasgressore || trasgressore.trim().length < 3} onClick={saveTrasgressore}>
            {savingTrasgressore ? 'Salvataggio…' : 'Salva trasgressore'}
          </Button>
        </div>
        <div style={{ marginTop: 8, fontSize: 12, color: COLORS.textMuted }}>
          Il trasgressore è l’intestatario indicato nel verbale e non viene usato automaticamente come driver.
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
            {!showDriverTools ? (
              <Button variant="outline" onClick={openDriverTools}>Modifica associazione driver</Button>
            ) : (
              <>
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
              </>
            )}
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

      {fatturaAperta && verbale?.fattura_id && (
        <ModalFattura
          fatturaId={verbale.fattura_id}
          numero={verbale.fattura_numero || verbale.fattura_info?.invoice_number}
          onClose={() => setFatturaAperta(false)}
        />
      )}

      {pdfViewer && (
        <VisoreOriginale
          title={pdfViewer.title}
          url={pdfViewer.url}
          documentType="verbale"
          onClose={() => setPdfViewer(null)}
        />
      )}
    </PageLayout>
  );
}
