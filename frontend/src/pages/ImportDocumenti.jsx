import React, { useState, useCallback, useRef } from 'react';
import { toast } from 'sonner';
import { COLORS, SHADOWS, BORDER_RADIUS } from '../lib/utils';
import api from '../api';
import { PageLayout } from '../components/PageLayout';
import { useConfirm } from '../components/ui/ConfirmDialog';
import { Button, Badge, Card, RowActionButton } from '../components/ds';
import {
  Upload,
  FileText,
  CheckCircle,
  AlertCircle,
  Loader2,
  FolderUp,
  Sparkles,
} from 'lucide-react';

export function classificaEsitoUpload(data = {}) {
  const message = data?.message || '';
  const duplicate =
    data?.action === 'duplicate' ||
    data?.duplicate === true ||
    (data?.imported === 0 && /duplicat/i.test(message));
  const partial = data?.partial === true;
  const failed = data?.success === false && !duplicate && !partial;

  return {
    status: duplicate ? 'duplicate' : partial ? 'partial' : failed ? 'error' : 'success',
    message: duplicate
      ? message || 'Documento duplicato ignorato'
      : failed
        ? message || 'Import non riuscito'
        : partial
          ? message || 'Import parziale: controllare gli errori'
          : message || 'Importato',
  };
}

export function descriviProvaFiscale(data = {}) {
  if (data?.workflow === 'PAGAMENTO_DOCUMENTALE_CANONICO') {
    const match = data?.data?.riconciliazione_fiscale || {};
    const receipt = data?.data?.receipt || {};
    const parts = [];
    if (Number.isFinite(receipt.operation_amount)) parts.push(`Operazione: € ${receipt.operation_amount.toFixed(2)}`);
    if (Number.isFinite(receipt.fee_amount)) parts.push(`Commissione: € ${receipt.fee_amount.toFixed(2)}`);
    if (Number.isFinite(receipt.bank_debit_total)) parts.push(`Addebito: € ${receipt.bank_debit_total.toFixed(2)}`);
    if (match.matched) {
      const cartelle = Array.isArray(match.linked_claim_ids) ? match.linked_claim_ids.length : 0;
      parts.push('Rata collegata', `Cartelle collegate: ${cartelle}`);
    } else {
      parts.push('Collegamento da verificare');
    }
    parts.push(match.bank_verified ? 'Banca verificata' : 'Banca da verificare');
    return parts.join(' • ');
  }
  if (data?.workflow === 'PAGOPA_CBILL_CANONICO') {
    const match = data?.data?.riconciliazione_fiscale || {};
    if (!match.matched) return 'Ricevuta acquisita â€¢ collegamento AdeR da verificare';
    const cartelle = Array.isArray(match.linked_claim_ids) ? match.linked_claim_ids.length : 0;
    return `Rata collegata â€¢ Cartelle collegate: ${cartelle} â€¢ ${match.bank_verified ? 'Banca verificata' : 'Banca da verificare'}`;
  }
  if (data?.workflow !== 'F24_CANONICO') return '';
  const canonical = data?.data || {};
  const parts = [];
  if (canonical?.riconciliazione_ader?.matched) {
    const cartelle = canonical.riconciliazione_ader.linked_claim_ids || [];
    parts.push(`Rata AdeR collegata`);
    parts.push(`Cartelle collegate: ${cartelle.length}`);
  }
  if (Number.isInteger(canonical.righe_tributo)) {
    parts.push(`Righe tributo: ${canonical.righe_tributo}`);
  }
  if (Number.isInteger(canonical.righe_credito)) {
    parts.push(`Crediti: ${canonical.righe_credito}`);
  }
  if (canonical?.validazione?.saldo_quadrato === true) {
    parts.push('Quadratura verificata');
  }
  return parts.join(' • ');
}

/**
 * ImportDocumenti - Pagina SEMPLIFICATA
 *
 * L'utente carica file e il sistema riconosce automaticamente:
 * - F24 → workflow completo tributi + scadenze
 * - Libro Unico (LUL) → buste paga + presenze + anagrafica
 * - Fatture XML → magazzino + prima nota
 * - Estratti Conto → movimenti bancari
 * - Bonifici, Corrispettivi, POS, ecc.
 *
 * NESSUNA SCELTA da parte dell'utente!
 */

export default function ImportDocumenti() {
  const confirm = useConfirm();
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState({ current: 0, total: 0, filename: '' });
  const [results, setResults] = useState([]);
  const [previewComplete, setPreviewComplete] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);
  const zipInputRef = useRef(null);

  const previewAndApply = async ({ previewUrl, applyUrl, title, describe }) => {
    try {
      const preview = (await api.post(previewUrl)).data || {};
      const approved = await confirm({
        title,
        message: describe(preview),
        confirmText: 'Conferma operazione',
        cancelText: 'Annulla',
      });
      if (!approved) return null;
      return (await api.post(applyUrl)).data || {};
    } catch (error) {
      toast.error('Operazione non completata', {
        description: error.response?.data?.detail || error.message,
      });
      return null;
    }
  };

  const handleDragOver = useCallback(e => {
    e.preventDefault();
    setDragOver(true);
  }, []);
  const handleDragLeave = useCallback(e => {
    e.preventDefault();
    setDragOver(false);
  }, []);

  const handleDrop = useCallback(async e => {
    e.preventDefault();
    setDragOver(false);
    await processIncomingFiles(Array.from(e.dataTransfer.files));
  }, []);

  const handleFileSelect = async e => {
    await processIncomingFiles(Array.from(e.target.files));
    e.target.value = '';
  };

  const handleZipSelect = async e => {
    await processIncomingFiles(Array.from(e.target.files));
    e.target.value = '';
  };

  const processIncomingFiles = async incomingFiles => {
    // Gli ZIP vengono inviati interi al backend: soltanto il server puo
    // applicare limiti affidabili anti zip-bomb e di dimensione non compressa.
    const filesWithInfo = incomingFiles.map(file => ({
      file,
      name: file.name,
      size: file.size,
      status: 'pending',
    }));
    setFiles(prev => [...prev, ...filesWithInfo]);
    setPreviewComplete(false);
    setResults([]);
  };

  const removeFile = index => {
    setFiles(prev => prev.filter((_, i) => i !== index));
    setPreviewComplete(false);
  };

  const handlePreview = async () => {
    if (files.length === 0) return;
    setUploading(true);
    setUploadProgress({ current: 0, total: files.length, filename: '' });
    let blocked = false;
    const analyzed = [];
    for (let i = 0; i < files.length; i++) {
      const fileInfo = files[i];
      setUploadProgress({ current: i + 1, total: files.length, filename: fileInfo.name });
      try {
        const formData = new FormData();
        formData.append('file', fileInfo.file);
        const res = await api.post('/api/documenti/upload-auto/preview', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        const preview = res.data || {};
        const hasErrors = (preview.blocking_errors || []).length > 0;
        blocked = blocked || hasErrors;
        analyzed.push({
          ...fileInfo,
          status: hasErrors ? 'error' : 'preview',
          tipo: preview.tipo_rilevato,
          preview,
          previewToken: preview.confirmation_token,
          error: hasErrors ? preview.blocking_errors.join('; ') : undefined,
        });
      } catch (e) {
        blocked = true;
        const rawError = e.response?.data?.detail || e.response?.data?.message || e.message;
        analyzed.push({ ...fileInfo, status: 'error', error: String(rawError) });
      }
    }
    setFiles(analyzed);
    setPreviewComplete(!blocked && analyzed.length === files.length);
    setUploading(false);
  };

  // Upload automatico - il backend rileva tutto
  const handleUpload = async () => {
    if (files.length === 0) return;

    setUploading(true);
    setUploadProgress({ current: 0, total: files.length, filename: '' });
    const uploadResults = [];

    for (let i = 0; i < files.length; i++) {
      const fileInfo = files[i];

      setUploadProgress({ current: i + 1, total: files.length, filename: fileInfo.name });
      setFiles(prev => prev.map((f, idx) => (idx === i ? { ...f, status: 'uploading' } : f)));

      try {
        const formData = new FormData();
        formData.append('file', fileInfo.file);

        // Endpoint unico che rileva e processa automaticamente
        const res = await api.post('/api/documenti/upload-auto', formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
            'X-Document-Preview-Token': fileInfo.previewToken,
          },
        });

        const tipo = res.data?.tipo_rilevato || res.data?.detected_type || 'auto';
        const esito = classificaEsitoUpload(res.data);

        uploadResults.push({
          file: fileInfo.name,
          tipo,
          status: esito.status,
          message: esito.message,
          workflow: res.data?.workflow,
          evidenceSummary: descriviProvaFiscale(res.data),
          details: res.data,
        });
        setFiles(prev =>
          prev.map((f, idx) =>
            idx === i ? { ...f, status: esito.status, tipo } : f
          )
        );
      } catch (e) {
        const rawError = e.response?.data?.detail || e.response?.data?.message || e.message;
        const errMsg = typeof rawError === 'string' ? rawError : JSON.stringify(rawError);
        const normalizedError = errMsg.toLowerCase();
        const isDuplicate =
          normalizedError.includes('duplicat') ||
          normalizedError.includes('esiste già') ||
          e.response?.status === 409;
        uploadResults.push({
          file: fileInfo.name,
          tipo: 'errore',
          status: isDuplicate ? 'duplicate' : 'error',
          message: isDuplicate ? 'Duplicato' : errMsg,
        });
        setFiles(prev =>
          prev.map((f, idx) =>
            idx === i ? { ...f, status: isDuplicate ? 'duplicate' : 'error', error: errMsg } : f
          )
        );
      }

      if (i < files.length - 1) await new Promise(r => setTimeout(r, 100));
    }

    setResults(uploadResults);
    setUploading(false);
  };

  const handleReset = () => {
    setFiles([]);
    setResults([]);
    setPreviewComplete(false);
  };

  const canConfirm =
    previewComplete && files.length > 0 && files.every(f => f.previewToken && f.status !== 'error');

  const successCount = results.filter(r => r.status === 'success').length;
  const duplicateCount = results.filter(r => r.status === 'duplicate').length;
  const errorCount = results.filter(r => r.status === 'error').length;
  const partialCount = results.filter(r => r.status === 'partial').length;

  // Variante Badge per tipo rilevato (mappata sui token del design system)
  const getTipoVariant = tipo => {
    const variants = {
      f24: 'danger',
      cedolino: 'accent',
      fattura: 'danger',
      estratto_conto: 'success',
      estratto_conto_pdf: 'success',
      bonifici: 'info',
      pagamenti_buoni: 'info',
      quietanza_f24: 'warning',
      ricevuta_pagopa: 'warning',
      ricevuta_cbill: 'warning',
      ricevuta_mav: 'warning',
      ricevuta_rav: 'warning',
      ricevuta_bollettino_postale: 'warning',
      avviso_pagopa: 'warning',
      nota_rettifica_inps: 'warning',
      esito_pagopa_negativo: 'danger',
      tari_avviso: 'warning',
      tari_istanza_compensazione: 'info',
      ader_sospensione: 'info',
      ader_definizione_agevolata: 'info',
      dimissioni_telematiche: 'accent',
      verbale_codice_strada: 'warning',
      visura_camerale: 'neutral',
      documento_identita: 'neutral',
      corrispettivi: 'success',
      pos: 'accent',
      archivio_zip: 'warning',
    };
    return variants[tipo] || 'neutral';
  };

  const getTipoLabel = tipo => {
    const labels = {
      f24: 'F24',
      cedolino: 'Libro Unico',
      fattura: 'Fattura XML',
      estratto_conto: 'Estratto Conto',
      estratto_conto_pdf: 'Estratto PDF',
      bonifici: 'Bonifici',
      pagamenti_buoni: 'Pagamenti buoni',
      quietanza_f24: 'Quietanza F24',
      ricevuta_pagopa: 'PagoPA / CBILL',
      ricevuta_cbill: 'Ricevuta CBILL',
      ricevuta_mav: 'Pagamento MAV',
      ricevuta_rav: 'Pagamento RAV',
      ricevuta_bollettino_postale: 'Bollettino postale pagato',
      avviso_pagopa: 'Avviso PagoPA (non pagato)',
      nota_rettifica_inps: 'Nota rettifica INPS',
      esito_pagopa_negativo: 'PagoPA non eseguito',
      tari_avviso: 'Avviso TARI',
      tari_istanza_compensazione: 'Istanza TARI',
      ader_sospensione: 'Sospensione AdeR',
      ader_definizione_agevolata: 'Definizione agevolata AdeR',
      dimissioni_telematiche: 'Dimissioni telematiche',
      verbale_codice_strada: 'Verbale Codice della strada',
      visura_camerale: 'Visura camerale',
      documento_identita: 'Documento di identità',
      corrispettivi: 'Corrispettivi',
      pos: 'POS',
      archivio_zip: 'Archivio ZIP',
      non_riconosciuto: 'Da classificare',
    };
    return labels[tipo] || tipo;
  };

  const tipiSupportati = [
    { label: 'F24', variant: 'danger' },
    { label: 'Libro Unico (LUL)', variant: 'accent' },
    { label: 'Fatture XML', variant: 'danger' },
    { label: 'Estratti Conto', variant: 'success' },
    { label: 'Quietanze F24', variant: 'warning' },
    { label: 'Ricevute PagoPA / CBILL', variant: 'warning' },
    { label: 'MAV, RAV e bollettini postali', variant: 'warning' },
    { label: 'Avvisi PagoPA', variant: 'warning' },
    { label: 'Note rettifica INPS', variant: 'warning' },
    { label: 'Verbali e notifiche CdS', variant: 'warning' },
    { label: 'TARI e atti AdeR', variant: 'info' },
    { label: 'Dimissioni telematiche', variant: 'accent' },
    { label: 'Bonifici', variant: 'info' },
    { label: 'Pagamenti buoni CSV', variant: 'info' },
    { label: 'Corrispettivi', variant: 'success' },
    { label: 'POS', variant: 'accent' },
    { label: 'Archivi ZIP', variant: 'warning' },
  ];

  return (
    <PageLayout
      title="Import Documenti"
      icon={<Upload size={22} />}
      description="Carica file e il sistema li elabora automaticamente"
    >
      <div style={{ maxWidth: 900, margin: '0 auto' }}>
        {/* Info Box */}
        <div
          style={{
            marginBottom: 20,
            padding: 16,
            background: COLORS.infoLight,
            borderRadius: BORDER_RADIUS.lg,
            border: `1px solid ${COLORS.info}`,
            display: 'flex',
            alignItems: 'flex-start',
            gap: 12,
          }}
        >
          <Sparkles size={20} color={COLORS.info} style={{ flexShrink: 0, marginTop: 2 }} />
          <div style={{ fontSize: 13, color: COLORS.info }}>
            <strong>Riconoscimento Automatico</strong>
            <br />
            Carica qualsiasi documento: F24, quietanze, PagoPA/CBILL, Libro Unico, Fatture XML,
            Estratti Conto, Bonifici, ecc.
            <br />
            Il sistema riconosce il tipo e lo elabora con il workflow completo.
          </div>
        </div>

        {/* Area Drop */}
        {/* Nota: div nativo (non Card) perché deve portare data-testid="drop-zone" sul nodo esatto */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          data-testid="drop-zone"
          style={{
            background: dragOver ? COLORS.infoLight : COLORS.card,
            border: dragOver ? `3px dashed ${COLORS.info}` : `3px dashed ${COLORS.borderDark}`,
            borderRadius: BORDER_RADIUS.xl,
            padding: 50,
            textAlign: 'center',
            marginBottom: 20,
            transition: 'all 0.2s',
            cursor: 'pointer',
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.xlsx,.xls,.xml,.csv,.zip"
            onChange={handleFileSelect}
            style={{ display: 'none' }}
            data-testid="file-input"
          />
          <FolderUp
            size={56}
            style={{ marginBottom: 12, opacity: 0.5, color: dragOver ? COLORS.info : COLORS.textMuted }}
          />
          <div style={{ fontSize: 17, fontWeight: 600, color: COLORS.gray[700], marginBottom: 6 }}>
            {dragOver ? 'Rilascia qui i file' : 'Trascina i file o clicca per selezionare'}
          </div>
          <div style={{ fontSize: 13, color: COLORS.textMuted }}>
            PDF, Excel, XML, CSV, ZIP • Singoli o multipli
          </div>
        </div>

        {/* Pulsante ZIP (opzionale) */}
        <div
          style={{
            marginBottom: 20,
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 10,
          }}
        >
          <input
            type="file"
            ref={zipInputRef}
            accept=".zip"
            multiple
            onChange={handleZipSelect}
            style={{ display: 'none' }}
            data-testid="zip-file-input"
          />
          <Button
            variant="warning"
            onClick={() => zipInputRef.current?.click()}
            disabled={uploading}
            data-testid="upload-zip-btn"
          >
            Carica ZIP
          </Button>
          <span style={{ fontSize: 12, color: COLORS.textMuted }}>
            ZIP controllati lato server (dimensioni, numero file e duplicati)
          </span>

          {/* Auto-classify documenti Gmail/PEC */}
          <Button
            type="button"
            variant="info"
            onClick={async () => {
              const r = await previewAndApply({
                previewUrl: '/api/documenti-inbox/auto-classify?solo_non_classificati=false&dry_run=true',
                applyUrl: '/api/documenti-inbox/auto-classify?solo_non_classificati=false&dry_run=false',
                title: 'Conferma classificazione documenti',
                describe: p => `Analizzati ${p.totali || 0} documenti; classificabili ${Object.values(p.classificati || {}).reduce((a, b) => a + Number(b || 0), 0)}, da verificare ${p.nessuna_categoria || 0}. Nessuna modifica è stata ancora applicata.`,
              });
              if (r) {
                const cats = Object.entries(r.classificati || {})
                  .map(([k, v]) => `${k}: ${v}`)
                  .join(' • ');
                toast.success('Auto-classificazione completata', {
                  description:
                    `Documenti totali: ${r.totali} • Non classificabili: ${r.nessuna_categoria} • ` +
                    `Cedolini/CU associati a dipendente: ${r.cedolini_associati} • F24 creati in f24_tributi: ${r.f24_creati}` +
                    (cats ? ` • ${cats}` : ''),
                });
              }
            }}
            data-testid="auto-classify-btn"
            title="Scansiona documents_inbox (Gmail/PEC) e classifica automaticamente F24, cedolini, CU, verbali, PEC…"
          >
            🧠 Auto-classifica Gmail/PEC
          </Button>

          <Button
            type="button"
            variant="warning"
            onClick={async () => {
              const r = await previewAndApply({
                previewUrl: '/api/documenti-inbox/import-f24-from-inbox?dry_run=true',
                applyUrl: '/api/documenti-inbox/import-f24-from-inbox?dry_run=false',
                title: 'Conferma proiezione F24',
                describe: p => `Analizzati ${p.f24_analizzati || 0} F24; ${p.tributi_creati || 0} righe tributo proposte. Nessuna riga è stata ancora creata.`,
              });
              if (r) {
                toast.success('Import F24 completato', {
                  description: `F24 analizzati: ${r.f24_analizzati} • Tributi creati in f24_tributi: ${r.tributi_creati}`,
                });
              }
            }}
            data-testid="import-f24-btn"
          >
            📧 Importa F24 da inbox
          </Button>

          <Button
            type="button"
            variant="success"
            onClick={async () => {
              const r = await previewAndApply({
                previewUrl: '/api/documenti-inbox/import-dipendenti-from-cu?dry_run=true',
                applyUrl: '/api/documenti-inbox/import-dipendenti-from-cu?dry_run=false',
                title: 'Conferma proposte dipendenti da CU',
                describe: p => `Analizzate ${p.cu_analizzate || 0} CU; ${p.dipendenti_creati || 0} nuove anagrafiche proposte, ${p.gia_presenti || 0} già presenti. Nessuna anagrafica è stata ancora creata.`,
              });
              if (r) {
                toast.success('Import dipendenti da CU completato', {
                  description:
                    `CU analizzate: ${r.cu_analizzate} • Dipendenti creati: ${r.dipendenti_creati} • ` +
                    `Già presenti: ${r.gia_presenti} • Filename non riconosciuti: ${r.non_riconosciuti}`,
                });
              }
            }}
            data-testid="import-dipendenti-cu-btn"
          >
            👤 Importa dipendenti da CU
          </Button>
        </div>

        {/* Lista File in coda */}
        {files.length > 0 && (
          <Card style={{ marginBottom: 20 }} bodyStyle={{ padding: 0 }}>
            <div
              style={{
                padding: 14,
                borderBottom: `1px solid ${COLORS.border}`,
                background: COLORS.bgAlt,
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div style={{ fontWeight: 600, fontSize: 14, color: COLORS.gray[700] }}>
                {files.length} file in coda
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <Button variant="danger" size="sm" onClick={handleReset} data-testid="reset-btn">
                  Svuota
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={canConfirm ? handleUpload : handlePreview}
                  disabled={uploading}
                  data-testid="upload-btn"
                  iconLeft={
                    uploading ? (
                      <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />
                    ) : (
                      <Upload size={14} />
                    )
                  }
                >
                  {uploading
                    ? 'Elaborazione...'
                    : canConfirm
                      ? 'Conferma importazione'
                      : 'Analizza senza salvare'}
                </Button>
              </div>
            </div>

            {/* Progress bar */}
            {uploading && uploadProgress.total > 0 && (
              <div
                style={{
                  padding: '10px 14px',
                  borderBottom: `1px solid ${COLORS.border}`,
                  background: COLORS.infoLight,
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: 6,
                  }}
                >
                  <span style={{ fontSize: 12, fontWeight: 600, color: COLORS.info }}>
                    {uploadProgress.filename}
                  </span>
                  <span style={{ fontSize: 11, color: COLORS.textMuted }}>
                    {uploadProgress.current}/{uploadProgress.total}
                  </span>
                </div>
                <div
                  style={{
                    height: 6,
                    background: COLORS.infoLight,
                    borderRadius: BORDER_RADIUS.full,
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      height: '100%',
                      width: `${(uploadProgress.current / uploadProgress.total) * 100}%`,
                      background: COLORS.info,
                      borderRadius: BORDER_RADIUS.full,
                      transition: 'width 0.3s ease',
                    }}
                  />
                </div>
              </div>
            )}

            {/* File list */}
            <div style={{ maxHeight: 300, overflow: 'auto' }}>
              {files.map((f, idx) => (
                <div
                  key={idx}
                  data-testid={`file-item-${idx}`}
                  style={{
                    padding: 12,
                    borderBottom: `1px solid ${COLORS.gray[100]}`,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    background:
                      f.status === 'success'
                        ? COLORS.successLight
                        : f.status === 'preview'
                          ? COLORS.infoLight
                        : f.status === 'duplicate' || f.status === 'partial'
                          ? COLORS.warningLight
                          : f.status === 'error'
                            ? COLORS.dangerLight
                            : COLORS.card,
                  }}
                >
                  <div
                    style={{
                      width: 32,
                      height: 32,
                      borderRadius: BORDER_RADIUS.sm,
                      background:
                        f.status === 'success'
                          ? COLORS.successLight
                          : f.status === 'preview'
                            ? COLORS.infoLight
                          : f.status === 'duplicate' || f.status === 'partial'
                            ? COLORS.warningLight
                            : f.status === 'error'
                              ? COLORS.dangerLight
                              : COLORS.bg,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                    }}
                  >
                    {f.status === 'uploading' ? (
                      <Loader2
                        size={16}
                        style={{ animation: 'spin 1s linear infinite' }}
                        color={COLORS.info}
                      />
                    ) : f.status === 'success' ? (
                      <CheckCircle size={16} color={COLORS.success} />
                    ) : f.status === 'preview' ? (
                      <CheckCircle size={16} color={COLORS.info} />
                    ) : f.status === 'duplicate' || f.status === 'partial' ? (
                      <AlertCircle size={16} color={COLORS.warning} />
                    ) : f.status === 'error' ? (
                      <AlertCircle size={16} color={COLORS.danger} />
                    ) : (
                      <FileText size={16} color={COLORS.textMuted} />
                    )}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontWeight: 600,
                        fontSize: 13,
                        color: COLORS.gray[700],
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {f.name}
                    </div>
                    <div style={{ fontSize: 11, color: COLORS.textMuted }}>
                      {(f.size / 1024).toFixed(1)} KB
                      {f.error && <span style={{ color: COLORS.danger }}> • {f.error}</span>}
                    </div>
                    {f.preview && (
                      <div
                        data-testid={`preview-details-${idx}`}
                        style={{ fontSize: 11, color: COLORS.info, marginTop: 3 }}
                      >
                        SHA-256: {f.preview.file?.sha256?.slice(0, 12)}...
                        {Number.isInteger(f.preview.parsed?.righe_tributo)
                          ? ` | Righe tributo: ${f.preview.parsed.righe_tributo}`
                          : ''}
                        {f.preview.validation?.saldo_quadrato === true
                          ? ' | Quadratura verificata'
                          : ''}
                        {f.preview.duplicate ? ' | Duplicato rilevato' : ' | Nuovo'}
                      </div>
                    )}
                  </div>
                  {/* Badge tipo rilevato (solo dopo upload) */}
                  {f.tipo && <Badge variant={getTipoVariant(f.tipo)}>{getTipoLabel(f.tipo)}</Badge>}
                  {f.status === 'pending' && (
                    <RowActionButton variant="danger" onClick={() => removeFile(idx)} title="Rimuovi">
                      ×
                    </RowActionButton>
                  )}
                </div>
              ))}
            </div>
          </Card>
        )}

        {previewComplete && results.length === 0 && (
          <div
            data-testid="preview-summary"
            style={{
              marginBottom: 20,
              padding: 14,
              background: COLORS.infoLight,
              border: `1px solid ${COLORS.info}`,
              borderRadius: BORDER_RADIUS.lg,
              color: COLORS.info,
              fontSize: 13,
            }}
          >
            <strong>Anteprima completata: nessun dato salvato.</strong>{' '}
            Controlla tipo, hash, quadratura e duplicati; poi usa "Conferma importazione".
          </div>
        )}

        {/* Risultati */}
        {/* Nota: div nativo (non Card) perché l'header cambia colore (verde/rosso/ambra)
            in base all'esito complessivo, funzionalità non supportata dall'header di <Card>. */}
        {results.length > 0 && (
          <div
            style={{
              background: COLORS.card,
              borderRadius: BORDER_RADIUS.lg,
              overflow: 'hidden',
              boxShadow: SHADOWS.sm,
              border: `1px solid ${COLORS.border}`,
            }}
          >
            <div
              style={{
                padding: 14,
                background:
                  successCount === results.length
                    ? COLORS.successLight
                    : errorCount === results.length
                      ? COLORS.dangerLight
                      : COLORS.warningLight,
                borderBottom: `1px solid ${COLORS.border}`,
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div style={{ fontWeight: 700, fontSize: 15, color: COLORS.gray[700] }}>
                {partialCount > 0
                  ? 'Import parziale: controllare i dettagli'
                  : duplicateCount === results.length
                  ? 'Nessun nuovo documento: duplicati ignorati'
                  : errorCount === 0 && duplicateCount === 0
                    ? 'Import completato!'
                    : errorCount === 0
                      ? 'Import completato con duplicati ignorati'
                  : successCount === 0
                    ? 'Errore import'
                    : 'Import parziale'}
              </div>
              <div style={{ display: 'flex', gap: 12, fontSize: 13 }}>
                <span style={{ color: COLORS.success }}>✓ {successCount}</span>
                <span style={{ color: COLORS.warning }}>⚠ {duplicateCount + partialCount}</span>
                <span style={{ color: COLORS.danger }}>✕ {errorCount}</span>
              </div>
            </div>
            <div style={{ padding: 14, maxHeight: 250, overflow: 'auto' }}>
              {results.map((r, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: 10,
                    background:
                      r.status === 'success'
                        ? COLORS.successLight
                        : r.status === 'duplicate' || r.status === 'partial'
                          ? COLORS.warningLight
                          : COLORS.dangerLight,
                    borderRadius: BORDER_RADIUS.md,
                    marginBottom: 6,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                  }}
                >
                  {r.status === 'success' ? (
                    <CheckCircle size={18} color={COLORS.success} />
                  ) : r.status === 'duplicate' || r.status === 'partial' ? (
                    <AlertCircle size={18} color={COLORS.warning} />
                  ) : (
                    <AlertCircle size={18} color={COLORS.danger} />
                  )}
                  <div style={{ flex: 1 }}>
                    <div
                      style={{
                        fontWeight: 600,
                        fontSize: 13,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                      }}
                    >
                      {r.file}
                      {r.tipo && r.tipo !== 'errore' && (
                        <Badge variant={getTipoVariant(r.tipo)}>{getTipoLabel(r.tipo)}</Badge>
                      )}
                      {r.workflow && <Badge variant="info">{r.workflow}</Badge>}
                    </div>
                    <div
                      style={{
                        fontSize: 11,
                        color:
                          r.status === 'success'
                            ? COLORS.success
                            : r.status === 'duplicate' || r.status === 'partial'
                              ? COLORS.warning
                              : COLORS.danger,
                      }}
                    >
                      {r.message}
                    </div>
                    {r.evidenceSummary && (
                      <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 3 }}>
                        {r.evidenceSummary}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
            <div
              style={{
                padding: '10px 14px',
                borderTop: `1px solid ${COLORS.border}`,
                background: COLORS.bgAlt,
              }}
            >
              <Button variant="secondary" size="sm" onClick={() => setResults([])}>
                Chiudi
              </Button>
            </div>
          </div>
        )}

        {/* Tips */}
        <Card title="Tipi di documento supportati" style={{ marginTop: 24 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {tipiSupportati.map(t => (
              <Badge key={t.label} variant={t.variant}>
                {t.label}
              </Badge>
            ))}
          </div>
        </Card>
      </div>
    </PageLayout>
  );
}
