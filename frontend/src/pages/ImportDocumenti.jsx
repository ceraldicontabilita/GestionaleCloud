import React, { useState, useCallback, useRef } from 'react';
import { formatEuro, COLORS } from '../lib/utils';
import api from '../api';
import { PageLayout } from '../components/PageLayout';
import {
  Upload,
  FileText,
  CheckCircle,
  AlertCircle,
  Loader2,
  FolderUp,
  Sparkles,
} from 'lucide-react';

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
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState({ current: 0, total: 0, filename: '' });
  const [results, setResults] = useState([]);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);
  const zipInputRef = useRef(null);

  // Estrazione da ZIP
  const extractFromZip = async file => {
    try {
      const JSZip = (await import('jszip')).default;
      const zip = await JSZip.loadAsync(file);
      const extractedFiles = [];

      for (const [filename, zipEntry] of Object.entries(zip.files)) {
        if (zipEntry.dir) continue;
        const lowerName = filename.toLowerCase();

        // Skip nested zip/rar - extract them too
        if (lowerName.endsWith('.zip')) {
          const nestedContent = await zipEntry.async('blob');
          const nestedFile = new File([nestedContent], filename, { type: 'application/zip' });
          const nestedFiles = await extractFromZip(nestedFile);
          extractedFiles.push(...nestedFiles);
          continue;
        }

        // Get content
        const content = await zipEntry.async('blob');
        const mimeType = lowerName.endsWith('.xml')
          ? 'application/xml'
          : lowerName.endsWith('.pdf')
            ? 'application/pdf'
            : lowerName.endsWith('.csv')
              ? 'text/csv'
              : lowerName.endsWith('.xlsx')
                ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                : 'application/octet-stream';
        const cleanName = filename.split('/').pop();
        extractedFiles.push(new File([content], cleanName, { type: mimeType }));
      }
      return extractedFiles;
    } catch (e) {
      console.error('Errore estrazione ZIP:', e);
      return [file];
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
    let allFiles = [];

    for (const file of incomingFiles) {
      const lowerName = file.name.toLowerCase();
      if (lowerName.endsWith('.zip')) {
        const extracted = await extractFromZip(file);
        allFiles.push(...extracted);
      } else {
        allFiles.push(file);
      }
    }

    const filesWithInfo = allFiles.map(file => ({
      file,
      name: file.name,
      size: file.size,
      status: 'pending',
    }));
    setFiles(prev => [...prev, ...filesWithInfo]);
  };

  const removeFile = index => setFiles(prev => prev.filter((_, i) => i !== index));

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
          headers: { 'Content-Type': 'multipart/form-data' },
        });

        const tipo = res.data?.tipo_rilevato || res.data?.detected_type || 'auto';
        const msg = res.data?.message || 'Importato';

        uploadResults.push({
          file: fileInfo.name,
          tipo,
          status: 'success',
          message: msg,
          workflow: res.data?.workflow,
          details: res.data,
        });
        setFiles(prev => prev.map((f, idx) => (idx === i ? { ...f, status: 'success', tipo } : f)));
      } catch (e) {
        const errMsg = e.response?.data?.detail || e.response?.data?.message || e.message;
        const isDuplicate =
          errMsg.toLowerCase().includes('duplicat') ||
          errMsg.toLowerCase().includes('esiste già') ||
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
  };

  const successCount = results.filter(r => r.status === 'success').length;
  const duplicateCount = results.filter(r => r.status === 'duplicate').length;
  const errorCount = results.filter(r => r.status === 'error').length;

  // Colori per tipo rilevato
  const getTipoColor = tipo => {
    const colors = {
      f24: '#ef4444',
      cedolino: '#8b5cf6',
      fattura: '#ec4899',
      estratto_conto: '#059669',
      estratto_conto_pdf: '#4caf50',
      bonifici: '#06b6d4',
      quietanza_f24: '#ff9800',
      corrispettivi: '#84cc16',
      pos: '#a855f7',
    };
    return colors[tipo] || '#6b7280';
  };

  const getTipoLabel = tipo => {
    const labels = {
      f24: 'F24',
      cedolino: 'Libro Unico',
      fattura: 'Fattura XML',
      estratto_conto: 'Estratto Conto',
      estratto_conto_pdf: 'Estratto PDF',
      bonifici: 'Bonifici',
      quietanza_f24: 'Quietanza F24',
      corrispettivi: 'Corrispettivi',
      pos: 'POS',
      non_riconosciuto: 'Da classificare',
    };
    return labels[tipo] || tipo;
  };

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
            background: '#dbeafe',
            borderRadius: 12,
            border: '1px solid #93c5fd',
            display: 'flex',
            alignItems: 'flex-start',
            gap: 12,
          }}
        >
          <Sparkles size={20} color="#3b82f6" style={{ flexShrink: 0, marginTop: 2 }} />
          <div style={{ fontSize: 13, color: '#1e40af' }}>
            <strong>Riconoscimento Automatico</strong>
            <br />
            Carica qualsiasi documento: F24, Libro Unico, Fatture XML, Estratti Conto, Bonifici,
            ecc.
            <br />
            Il sistema riconosce il tipo e lo elabora con il workflow completo.
          </div>
        </div>

        {/* Area Drop */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          data-testid="drop-zone"
          style={{
            background: dragOver ? '#dbeafe' : 'white',
            border: dragOver ? '3px dashed #3b82f6' : '3px dashed #d1d5db',
            borderRadius: 16,
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
            style={{ marginBottom: 12, opacity: 0.5, color: dragOver ? '#3b82f6' : '#6b7280' }}
          />
          <div style={{ fontSize: 17, fontWeight: 600, color: '#374151', marginBottom: 6 }}>
            {dragOver ? 'Rilascia qui i file' : 'Trascina i file o clicca per selezionare'}
          </div>
          <div style={{ fontSize: 13, color: '#6b7280' }}>
            PDF, Excel, XML, CSV, ZIP • Singoli o multipli
          </div>
        </div>

        {/* Pulsante ZIP (opzionale) */}
        <div style={{ marginBottom: 20, textAlign: 'center' }}>
          <input
            type="file"
            ref={zipInputRef}
            accept=".zip"
            multiple
            onChange={handleZipSelect}
            style={{ display: 'none' }}
            data-testid="zip-file-input"
          />
          <button
            onClick={() => zipInputRef.current?.click()}
            disabled={uploading}
            style={{
              padding: '10px 20px',
              background: '#f59e0b',
              color: 'white',
              border: 'none',
              borderRadius: 8,
              fontWeight: 600,
              cursor: uploading ? 'wait' : 'pointer',
              fontSize: 13,
            }}
            data-testid="upload-zip-btn"
          >
            Carica ZIP
          </button>
          <span style={{ marginLeft: 12, fontSize: 12, color: '#6b7280' }}>
            Supporta ZIP annidati con estrazione automatica
          </span>

          {/* Auto-classify documenti Gmail/PEC */}
          <button
            type="button"
            onClick={async () => {
              try {
                const res = await api.post(
                  '/api/documenti-inbox/auto-classify?solo_non_classificati=false'
                );
                const r = res.data || {};
                const cats = Object.entries(r.classificati || {})
                  .map(([k, v]) => `  ${k}: ${v}`)
                  .join('\n');
                alert(
                  `✓ Auto-classificazione completata\n\n` +
                    `Documenti totali: ${r.totali}\n` +
                    `Non classificabili: ${r.nessuna_categoria}\n` +
                    `Cedolini/CU associati a dipendente: ${r.cedolini_associati}\n` +
                    `F24 creati in f24_tributi: ${r.f24_creati}\n\n` +
                    `Categorie rilevate:\n${cats}`
                );
              } catch (e) {
                alert('Errore: ' + (e.response?.data?.detail || e.message));
              }
            }}
            data-testid="auto-classify-btn"
            title="Scansiona documents_inbox (Gmail/PEC) e classifica automaticamente F24, cedolini, CU, verbali, PEC…"
            style={{
              marginLeft: 14,
              padding: '10px 16px',
              background: '#1d4ed8',
              color: 'white',
              border: 'none',
              borderRadius: 8,
              fontWeight: 600,
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            🧠 Auto-classifica Gmail/PEC
          </button>

          <button
            type="button"
            onClick={async () => {
              try {
                const res = await api.post('/api/documenti-inbox/import-f24-from-inbox');
                const r = res.data || {};
                alert(
                  `✓ Import F24 completato\n\nF24 analizzati: ${r.f24_analizzati}\nTributi creati in f24_tributi: ${r.tributi_creati}`
                );
              } catch (e) {
                alert('Errore: ' + (e.response?.data?.detail || e.message));
              }
            }}
            data-testid="import-f24-btn"
            style={{
              marginLeft: 8,
              padding: '10px 16px',
              background: '#b45309',
              color: 'white',
              border: 'none',
              borderRadius: 8,
              fontWeight: 600,
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            📧 Importa F24 da inbox
          </button>

          <button
            type="button"
            onClick={async () => {
              try {
                const res = await api.post('/api/documenti-inbox/import-dipendenti-from-cu');
                const r = res.data || {};
                alert(
                  `✓ Import dipendenti da CU completato\n\n` +
                    `CU analizzate: ${r.cu_analizzate}\n` +
                    `Dipendenti creati: ${r.dipendenti_creati}\n` +
                    `Già presenti: ${r.gia_presenti}\n` +
                    `Filename non riconosciuti: ${r.non_riconosciuti}`
                );
              } catch (e) {
                alert('Errore: ' + (e.response?.data?.detail || e.message));
              }
            }}
            data-testid="import-dipendenti-cu-btn"
            style={{
              marginLeft: 8,
              padding: '10px 16px',
              background: '#15803d',
              color: 'white',
              border: 'none',
              borderRadius: 8,
              fontWeight: 600,
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            👤 Importa dipendenti da CU
          </button>
        </div>

        {/* Lista File in coda */}
        {files.length > 0 && (
          <div
            style={{
              background: 'white',
              borderRadius: 12,
              overflow: 'hidden',
              marginBottom: 20,
              boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
              border: '1px solid #e5e7eb',
            }}
          >
            <div
              style={{
                padding: 14,
                borderBottom: '1px solid #e5e7eb',
                background: '#f9fafb',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div style={{ fontWeight: 600, fontSize: 14, color: '#374151' }}>
                {files.length} file in coda
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  onClick={handleReset}
                  data-testid="reset-btn"
                  style={{
                    padding: '8px 14px',
                    background: '#fee2e2',
                    color: '#dc2626',
                    border: 'none',
                    borderRadius: 6,
                    cursor: 'pointer',
                    fontWeight: 600,
                    fontSize: 12,
                  }}
                >
                  Svuota
                </button>
                <button
                  onClick={handleUpload}
                  disabled={uploading}
                  data-testid="upload-btn"
                  style={{
                    padding: '8px 20px',
                    background: uploading ? '#9ca3af' : '#3b82f6',
                    color: 'white',
                    border: 'none',
                    borderRadius: 6,
                    cursor: uploading ? 'wait' : 'pointer',
                    fontWeight: 600,
                    fontSize: 12,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  {uploading ? (
                    <>
                      <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />{' '}
                      Elaborazione...
                    </>
                  ) : (
                    <>
                      <Upload size={14} /> Carica Tutti
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Progress bar */}
            {uploading && uploadProgress.total > 0 && (
              <div
                style={{
                  padding: '10px 14px',
                  borderBottom: '1px solid #e5e7eb',
                  background: '#eff6ff',
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
                  <span style={{ fontSize: 12, fontWeight: 600, color: '#1d4ed8' }}>
                    {uploadProgress.filename}
                  </span>
                  <span style={{ fontSize: 11, color: '#6b7280' }}>
                    {uploadProgress.current}/{uploadProgress.total}
                  </span>
                </div>
                <div
                  style={{ height: 6, background: '#dbeafe', borderRadius: 3, overflow: 'hidden' }}
                >
                  <div
                    style={{
                      height: '100%',
                      width: `${(uploadProgress.current / uploadProgress.total) * 100}%`,
                      background: '#1d4ed8',
                      borderRadius: 3,
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
                    borderBottom: '1px solid #f3f4f6',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    background:
                      f.status === 'success'
                        ? '#f0fdf4'
                        : f.status === 'duplicate'
                          ? '#fefce8'
                          : f.status === 'error'
                            ? '#fef2f2'
                            : 'white',
                  }}
                >
                  <div
                    style={{
                      width: 32,
                      height: 32,
                      borderRadius: 6,
                      background:
                        f.status === 'success'
                          ? '#dcfce7'
                          : f.status === 'duplicate'
                            ? '#fef9c3'
                            : f.status === 'error'
                              ? '#fee2e2'
                              : '#f1f5f9',
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
                        color="#3b82f6"
                      />
                    ) : f.status === 'success' ? (
                      <CheckCircle size={16} color="#16a34a" />
                    ) : f.status === 'duplicate' ? (
                      <AlertCircle size={16} color="#ca8a04" />
                    ) : f.status === 'error' ? (
                      <AlertCircle size={16} color="#dc2626" />
                    ) : (
                      <FileText size={16} color="#6b7280" />
                    )}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontWeight: 600,
                        fontSize: 13,
                        color: '#374151',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {f.name}
                    </div>
                    <div style={{ fontSize: 11, color: '#6b7280' }}>
                      {(f.size / 1024).toFixed(1)} KB
                      {f.error && <span style={{ color: '#dc2626' }}> • {f.error}</span>}
                    </div>
                  </div>
                  {/* Badge tipo rilevato (solo dopo upload) */}
                  {f.tipo && (
                    <span
                      style={{
                        padding: '4px 10px',
                        background: `${getTipoColor(f.tipo)}15`,
                        color: getTipoColor(f.tipo),
                        borderRadius: 6,
                        fontSize: 11,
                        fontWeight: 600,
                        border: `1px solid ${getTipoColor(f.tipo)}30`,
                      }}
                    >
                      {getTipoLabel(f.tipo)}
                    </span>
                  )}
                  {f.status === 'pending' && (
                    <button
                      onClick={() => removeFile(idx)}
                      style={{
                        width: 28,
                        height: 28,
                        border: 'none',
                        background: '#fee2e2',
                        borderRadius: 6,
                        cursor: 'pointer',
                        color: '#dc2626',
                        fontSize: 14,
                        flexShrink: 0,
                      }}
                    >
                      ×
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Risultati */}
        {results.length > 0 && (
          <div
            style={{
              background: 'white',
              borderRadius: 12,
              overflow: 'hidden',
              boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
              border: '1px solid #e5e7eb',
            }}
          >
            <div
              style={{
                padding: 14,
                background:
                  successCount === results.length
                    ? '#dcfce7'
                    : errorCount === results.length
                      ? '#fee2e2'
                      : '#fef3c7',
                borderBottom: '1px solid #e5e7eb',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div style={{ fontWeight: 700, fontSize: 15, color: '#374151' }}>
                {errorCount === 0
                  ? 'Import completato!'
                  : successCount === 0
                    ? 'Errore import'
                    : 'Import parziale'}
              </div>
              <div style={{ display: 'flex', gap: 12, fontSize: 13 }}>
                <span style={{ color: '#16a34a' }}>✓ {successCount}</span>
                <span style={{ color: '#ca8a04' }}>⚠ {duplicateCount}</span>
                <span style={{ color: '#dc2626' }}>✕ {errorCount}</span>
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
                        ? '#f0fdf4'
                        : r.status === 'duplicate'
                          ? '#fefce8'
                          : '#fef2f2',
                    borderRadius: 8,
                    marginBottom: 6,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                  }}
                >
                  {r.status === 'success' ? (
                    <CheckCircle size={18} color="#16a34a" />
                  ) : r.status === 'duplicate' ? (
                    <AlertCircle size={18} color="#ca8a04" />
                  ) : (
                    <AlertCircle size={18} color="#dc2626" />
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
                        <span
                          style={{
                            padding: '2px 8px',
                            background: `${getTipoColor(r.tipo)}15`,
                            color: getTipoColor(r.tipo),
                            borderRadius: 4,
                            fontSize: 10,
                            fontWeight: 700,
                          }}
                        >
                          {getTipoLabel(r.tipo)}
                        </span>
                      )}
                      {r.workflow && (
                        <span
                          style={{
                            padding: '2px 8px',
                            background: '#dbeafe',
                            color: '#1d4ed8',
                            borderRadius: 4,
                            fontSize: 10,
                            fontWeight: 700,
                          }}
                        >
                          {r.workflow}
                        </span>
                      )}
                    </div>
                    <div
                      style={{
                        fontSize: 11,
                        color:
                          r.status === 'success'
                            ? '#166534'
                            : r.status === 'duplicate'
                              ? '#92400e'
                              : '#dc2626',
                      }}
                    >
                      {r.message}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div
              style={{
                padding: '10px 14px',
                borderTop: '1px solid #e5e7eb',
                background: '#f9fafb',
              }}
            >
              <button
                onClick={() => setResults([])}
                style={{
                  padding: '6px 14px',
                  background: '#e5e7eb',
                  border: 'none',
                  borderRadius: 6,
                  cursor: 'pointer',
                  fontSize: 12,
                  fontWeight: 500,
                }}
              >
                Chiudi
              </button>
            </div>
          </div>
        )}

        {/* Tips */}
        <div
          style={{
            marginTop: 24,
            padding: 16,
            background: '#f9fafb',
            borderRadius: 10,
            border: '1px solid #e5e7eb',
            fontSize: 12,
            color: '#6b7280',
          }}
        >
          <div style={{ fontWeight: 600, color: '#374151', marginBottom: 8 }}>
            Tipi di documento supportati:
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {[
              { label: 'F24', color: '#ef4444' },
              { label: 'Libro Unico (LUL)', color: '#8b5cf6' },
              { label: 'Fatture XML', color: '#ec4899' },
              { label: 'Estratti Conto', color: '#059669' },
              { label: 'Quietanze F24', color: '#ff9800' },
              { label: 'Bonifici', color: '#06b6d4' },
              { label: 'Corrispettivi', color: '#84cc16' },
              { label: 'POS', color: '#a855f7' },
            ].map(t => (
              <span
                key={t.label}
                style={{
                  padding: '3px 8px',
                  background: `${t.color}10`,
                  color: t.color,
                  borderRadius: 4,
                  fontSize: 11,
                  fontWeight: 600,
                }}
              >
                {t.label}
              </span>
            ))}
          </div>
        </div>
      </div>
    </PageLayout>
  );
}
