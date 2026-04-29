import React, { useState, useEffect, useRef, useCallback } from 'react';
import { formatEuro, formatDateIT, STYLES, COLORS, button, badge } from '../lib/utils';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout } from '../components/PageLayout';

const CATEGORY_COLORS = {
  f24: { bg: '#dbeafe', text: '#1e40af', icon: '📋', label: 'F24' },
  fattura: { bg: '#dcfce7', text: '#166534', icon: '🧾', label: 'Fatture' },
  busta_paga: { bg: '#fef3c7', text: '#92400e', icon: '📄', label: 'Buste Paga' },
  estratto_conto: { bg: '#f3e8ff', text: '#7c3aed', icon: '🏦', label: 'Estratti Conto' },
  quietanza: { bg: '#cffafe', text: '#0891b2', icon: '✅', label: 'Quietanze' },
  bonifico: { bg: '#fce7f3', text: '#be185d', icon: '💸', label: 'Bonifici' },
  cartella_esattoriale: {
    bg: '#fee2e2',
    text: '#dc2626',
    icon: '⚠️',
    label: 'Cartelle Esattoriali',
  },
  altro: { bg: '#f1f5f9', text: '#475569', icon: '📄', label: 'Altri' },
};

const STATUS_LABELS = {
  nuovo: { label: 'Nuovo', color: '#1e3a5f', bg: '#dbeafe' },
  processato: { label: 'Processato', color: '#16a34a', bg: '#dcfce7' },
  errore: { label: 'Errore', color: '#dc2626', bg: '#fef2f2' },
};

// Parole chiave predefinite per la ricerca email
const DEFAULT_KEYWORDS = [
  { id: 'f24', label: 'F24', keywords: 'f24,modello f24,tributi' },
  { id: 'fattura', label: 'Fattura', keywords: 'fattura,invoice,ft.' },
  { id: 'busta_paga', label: 'Busta Paga', keywords: 'busta paga,cedolino,lul' },
  { id: 'estratto_conto', label: 'Estratto Conto', keywords: 'estratto conto,movimenti bancari' },
  {
    id: 'cartella_esattoriale',
    label: 'Cartella Esattoriale',
    keywords: 'cartella esattoriale,agenzia entrate riscossione,equitalia,intimazione,ader',
  },
  { id: 'bonifico', label: 'Bonifico', keywords: 'bonifico,sepa,disposizione pagamento' },
];

export default function Documenti() {
  const { anno } = useAnnoGlobale();
  const [documents, setDocuments] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [filtroCategoria, setFiltroCategoria] = useState('');
  const [filtroStatus, setFiltroStatus] = useState('');
  const [categories, setCategories] = useState({});

  // Impostazioni download
  const [giorniDownload, setGiorniDownload] = useState(10); // ultimi 10 giorni
  const [paroleChiaveSelezionate, setParoleChiaveSelezionate] = useState([]);
  const [nuovaParolaChiave, setNuovaParolaChiave] = useState('');
  const [customKeywords, setCustomKeywords] = useState([]);
  const [showImportSettings, setShowImportSettings] = useState(false);

  // Background download state
  const [backgroundTask, setBackgroundTask] = useState(null);
  const [taskStatus, setTaskStatus] = useState(null);
  const pollingRef = useRef(null);

  // Tab attivo
  const [activeTab, setActiveTab] = useState('categorie');

  // Categorie mittente
  const [categorieMittente, setCategorieMittente] = useState([]);
  const [filtroMittente, setFiltroMittente] = useState('');

  // Load categorie mittente
  useEffect(() => {
    api
      .get('/api/documenti-non-associati/categorie-mittente')
      .then(r => setCategorieMittente(r.data?.categorie || []))
      .catch(() => {});
  }, []);

  // AI Documents
  const [aiDocuments, setAiDocuments] = useState([]);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiStats, setAiStats] = useState(null);
  const [aiFilterTipo, setAiFilterTipo] = useState('');

  // Load AI Documents
  const loadAiDocuments = async () => {
    setAiLoading(true);
    try {
      const res = await api.get('/api/document-ai/extracted-documents?limit=100&include_file=true');
      setAiDocuments(res.data.documents || []);

      // Get stats
      try {
        const statsRes = await api.get('/api/document-ai/classified-documents-stats');
        setAiStats(statsRes.data);
      } catch (e) { /* stats AI non critiche — ignorato */ }
    } catch (error) {
      console.error('Errore caricamento documenti AI:', error);
    } finally {
      setAiLoading(false);
    }
  };

  // Lock status per operazioni email
  const [emailLocked, setEmailLocked] = useState(false);
  const [currentOperation, setCurrentOperation] = useState(null);

  // PDF Viewer
  const [selectedPdfDoc, setSelectedPdfDoc] = useState(null);
  const [pdfLoading, setPdfLoading] = useState(false);

  // Controlla lo stato del lock email
  const checkEmailLock = async () => {
    try {
      const res = await api.get('/api/system/lock-status');
      setEmailLocked(res.data.email_locked);
      setCurrentOperation(res.data.operation);
    } catch (e) {
      console.error('Errore check lock:', e);
    }
  };

  useEffect(() => {
    loadData();
    checkEmailLock(); // Controlla stato lock all'avvio
    // Carica parole chiave personalizzate da MongoDB
    const loadKeywords = async () => {
      try {
        const res = await api.get('/api/settings/user-preferences');
        if (res.data?.document_keywords?.length) {
          setCustomKeywords(res.data.document_keywords);
        }
      } catch (e) {
        console.error('Errore caricamento keywords:', e);
      }
    };
    loadKeywords();

    // Cleanup polling on unmount
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, [filtroCategoria, filtroStatus, anno]);

  // Polling per task in background
  const pollTaskStatus = useCallback(async taskId => {
    try {
      const res = await api.get(`/api/documenti/task/${taskId}`);
      setTaskStatus(res.data);

      if (res.data.status === 'completed') {
        // Stop polling
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        setDownloading(false);
        loadData(); // Ricarica documenti

        // Mostra risultato
        const stats = res.data.result?.stats;
        if (stats) {
          setTimeout(() => {
            alert(
              `✅ Download completato!\n\nEmail controllate: ${stats.emails_checked || 0}\nDocumenti trovati: ${stats.documents_found || 0}\nNuovi documenti: ${stats.new_documents || 0}\nDuplicati saltati: ${stats.duplicates_skipped || 0}`
            );
            setBackgroundTask(null);
            setTaskStatus(null);
          }, 500);
        }
      } else if (res.data.status === 'error') {
        // Stop polling on error
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        setDownloading(false);
        alert(`❌ Errore: ${res.data.error || 'Errore sconosciuto'}`);
        setBackgroundTask(null);
        setTaskStatus(null);
      }
    } catch (error) {
      console.error('Errore polling task:', error);
    }
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filtroCategoria) params.append('categoria', filtroCategoria);
      if (filtroStatus) params.append('status', filtroStatus);
      params.append('limit', '200');

      const [docsRes, statsRes] = await Promise.all([
        api.get(`/api/documenti/lista?${params}`),
        api.get('/api/documenti/statistiche'),
      ]);

      setDocuments(docsRes.data.documents || []);
      setCategories(docsRes.data.categories || {});
      setStats(statsRes.data);
    } catch (error) {
      console.error('Errore caricamento documenti:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadFromEmail = async () => {
    // Costruisci la stringa delle parole chiave
    let keywordsToSearch = [];
    paroleChiaveSelezionate.forEach(id => {
      const preset = DEFAULT_KEYWORDS.find(k => k.id === id);
      if (preset) {
        keywordsToSearch.push(...preset.keywords.split(',').map(k => k.trim()));
      }
    });
    // Aggiungi parole chiave personalizzate
    customKeywords.forEach(kw => {
      if (paroleChiaveSelezionate.includes(kw.id)) {
        keywordsToSearch.push(...kw.keywords.split(',').map(k => k.trim()));
      }
    });

    const keywordsParam = keywordsToSearch.length > 0 ? keywordsToSearch.join(',') : '';

    // Verifica lock email
    if (emailLocked) {
      alert(
        `⚠️ Operazione non disponibile\n\nC'è già un'operazione email in corso: ${currentOperation}\n\nAttendere il completamento.`
      );
      return;
    }

    const message = keywordsParam
      ? `Vuoi scaricare i documenti dalle email degli ultimi ${giorniDownload} giorni?\n\nParole chiave: ${keywordsToSearch.slice(0, 5).join(', ')}${keywordsToSearch.length > 5 ? '...' : ''}\n\nIl download avverrà in background.`
      : `Vuoi scaricare TUTTI i documenti dalle email degli ultimi ${giorniDownload} giorni?\n\n⚠️ Nessuna parola chiave selezionata - verranno scaricati tutti gli allegati.\n\nIl download avverrà in background.`;

    setDownloading(true);
    setTaskStatus({ status: 'pending', message: 'Avvio download...' });

    try {
      // Avvia download in background
      let url = `/api/documenti/scarica-da-email?giorni=${giorniDownload}&background=true`;
      if (keywordsParam) {
        url += `&parole_chiave=${encodeURIComponent(keywordsParam)}`;
      }

      const res = await api.post(url);

      if (res.data.background && res.data.task_id) {
        // Salva task e avvia polling
        setBackgroundTask(res.data.task_id);

        // Polling ogni 2 secondi
        pollingRef.current = setInterval(() => {
          pollTaskStatus(res.data.task_id);
        }, 2000);

        // Prima chiamata immediata
        pollTaskStatus(res.data.task_id);
      } else if (res.data.success) {
        // Fallback sincrono (non dovrebbe accadere)
        const stats = res.data.stats;
        alert(
          `✅ Download completato!\n\nEmail controllate: ${stats.emails_checked}\nDocumenti trovati: ${stats.documents_found}\nNuovi documenti: ${stats.new_documents}\nDuplicati saltati: ${stats.duplicates_skipped}`
        );
        loadData();
        setDownloading(false);
      }
    } catch (error) {
      const detail = error.response?.data?.detail || error.message;
      if (error.response?.status === 423) {
        alert(`⚠️ Operazione bloccata\n\n${detail}`);
      } else {
        alert(`❌ Errore download: ${detail}`);
      }
      setDownloading(false);
      setBackgroundTask(null);
      setTaskStatus(null);
      checkEmailLock(); // Aggiorna stato lock
    }
  };

  const addCustomKeyword = () => {
    if (!nuovaParolaChiave.trim()) return;
    const newKw = {
      id: `custom_${Date.now()}`,
      label: nuovaParolaChiave.trim(),
      keywords: nuovaParolaChiave.trim().toLowerCase(),
      custom: true,
    };
    const updated = [...customKeywords, newKw];
    setCustomKeywords(updated);
    api
      .put('/api/settings/user-preferences', { document_keywords: updated })
      .catch(e => console.error('Errore salvataggio keywords:', e));
    setNuovaParolaChiave('');
  };

  const removeCustomKeyword = id => {
    const updated = customKeywords.filter(k => k.id !== id);
    setCustomKeywords(updated);
    api
      .put('/api/settings/user-preferences', { document_keywords: updated })
      .catch(e => console.error('Errore salvataggio keywords:', e));
    setParoleChiaveSelezionate(prev => prev.filter(p => p !== id));
  };

  const toggleKeyword = id => {
    setParoleChiaveSelezionate(prev =>
      prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id]
    );
  };

  const handleProcessDocument = async (doc, destinazione) => {
    try {
      await api.post(`/api/documenti/documento/${doc.id}/processa?destinazione=${destinazione}`);
      alert(`✅ Documento processato e spostato in ${destinazione}`);
      loadData();
    } catch (error) {
      alert(`❌ Errore: ${error.response?.data?.detail || error.message}`);
    }
  };

  const handleDeleteDocument = async docId => {
    try {
      await api.delete(`/api/documenti/documento/${docId}`);
      loadData();
    } catch (error) {
      alert(`❌ Errore: ${error.response?.data?.detail || error.message}`);
    }
  };

  const handleChangeCategory = async (docId, newCategory) => {
    try {
      await api.post(
        `/api/documenti/documento/${docId}/cambia-categoria?nuova_categoria=${newCategory}`
      );
      loadData();
    } catch (error) {
      alert(`❌ Errore: ${error.response?.data?.detail || error.message}`);
    }
  };

  const handleDownloadFile = async doc => {
    try {
      const response = await api.get(`/api/documenti/documento/${doc.id}/download`, {
        responseType: 'blob',
      });

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', doc.filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (error) {
      alert(`❌ Errore download: ${error.message}`);
    }
  };

  // Visualizza PDF
  const handleViewPdf = async doc => {
    setPdfLoading(true);
    try {
      const response = await api.get(`/api/documenti/documento/${doc.id}/download`, {
        responseType: 'blob',
      });

      const pdfBlob = new Blob([response.data], { type: 'application/pdf' });
      const pdfUrl = window.URL.createObjectURL(pdfBlob);

      setSelectedPdfDoc({
        ...doc,
        pdfUrl,
      });
    } catch (error) {
      alert(`❌ Errore visualizzazione: ${error.message}`);
    } finally {
      setPdfLoading(false);
    }
  };

  // Chiudi PDF Viewer
  const closePdfViewer = () => {
    if (selectedPdfDoc?.pdfUrl) {
      window.URL.revokeObjectURL(selectedPdfDoc.pdfUrl);
    }
    setSelectedPdfDoc(null);
  };

  const formatBytes = bytes => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  const formatDate = dateStr => {
    if (!dateStr) return '-';
    // Usa formatDateIT per avere formato italiano
    const formatted = formatDateIT(dateStr);
    // Aggiungi orario se presente
    if (dateStr.includes('T')) {
      try {
        const d = new Date(dateStr);
        const time = d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
        return `${formatted} ${time}`;
      } catch {
        return formatted;
      }
    }
    return formatted;
  };

  // Styles
  const cardStyle = {
    background: 'white',
    borderRadius: 12,
    boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
    overflow: 'hidden',
  };

  const buttonStyle = (bg, color = 'white') => ({
    padding: '8px 16px',
    background: bg,
    color: color,
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    fontWeight: '600',
    fontSize: 13,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
  });

  const smallButtonStyle = (bg, color = 'white') => ({
    padding: '6px 12px',
    background: bg,
    color: color,
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    fontWeight: '500',
    fontSize: 12,
  });

  return (
    <PageLayout
      title="Gestione Documenti"
      icon="📨"
      subtitle="Gestisci documenti email e documenti estratti con AI"
      actions={
        <button
          onClick={activeTab === 'email' ? loadData : loadAiDocuments}
          disabled={loading || aiLoading}
          style={buttonStyle('#e5e7eb', '#374151')}
        >
          {loading || aiLoading ? '⏳' : '🔄'} Aggiorna
        </button>
      }
    >
      {/* Tab Navigation */}
      <div
        style={{
          display: 'flex',
          gap: 4,
          marginBottom: 20,
          background: '#f1f5f9',
          padding: 4,
          borderRadius: 10,
          width: 'fit-content',
        }}
      >
        <button
          onClick={() => setActiveTab('categorie')}
          style={{
            padding: '10px 20px',
            background: activeTab === 'categorie' ? 'white' : 'transparent',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            fontWeight: activeTab === 'categorie' ? 600 : 400,
            color: activeTab === 'categorie' ? '#059669' : '#6b7280',
            boxShadow: activeTab === 'categorie' ? '0 2px 4px rgba(0,0,0,0.1)' : 'none',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          🏛️ Per Mittente
        </button>
        <button
          onClick={() => setActiveTab('email')}
          style={{
            padding: '10px 20px',
            background: activeTab === 'email' ? 'white' : 'transparent',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            fontWeight: activeTab === 'email' ? 600 : 400,
            color: activeTab === 'email' ? '#1e40af' : '#6b7280',
            boxShadow: activeTab === 'email' ? '0 2px 4px rgba(0,0,0,0.1)' : 'none',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          📧 Tutti i Documenti
        </button>
        <button
          onClick={() => {
            setActiveTab('ai');
            loadAiDocuments();
          }}
          style={{
            padding: '10px 20px',
            background: activeTab === 'ai' ? 'white' : 'transparent',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            fontWeight: activeTab === 'ai' ? 600 : 400,
            color: activeTab === 'ai' ? '#7c3aed' : '#6b7280',
            boxShadow: activeTab === 'ai' ? '0 2px 4px rgba(0,0,0,0.1)' : 'none',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          🤖 AI Estratti
        </button>
      </div>

      {/* Tab Categorie Mittente */}
      {activeTab === 'categorie' && (
        <div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
              gap: 16,
              marginBottom: 24,
            }}
          >
            {categorieMittente.map(cat => (
              <div
                key={cat.nome}
                onClick={() => {
                  setFiltroMittente(cat.nome);
                  setActiveTab('email');
                  loadData();
                }}
                style={{
                  background: 'white',
                  borderRadius: 12,
                  padding: '20px',
                  cursor: 'pointer',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
                  border: '1px solid #e5e7eb',
                  transition: 'all 0.2s',
                  ':hover': { borderColor: '#3b82f6' },
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: 12,
                  }}
                >
                  <span style={{ fontSize: 28 }}>{cat.icon}</span>
                  <span
                    style={{
                      background: '#dbeafe',
                      color: '#1e40af',
                      padding: '4px 12px',
                      borderRadius: 99,
                      fontWeight: 700,
                      fontSize: 14,
                    }}
                  >
                    {cat.count}
                  </span>
                </div>
                <h3 style={{ margin: '0 0 4px', fontSize: 16, fontWeight: 700, color: '#1e3a5f' }}>
                  {cat.nome}
                </h3>
                <div style={{ fontSize: 12, color: '#6b7280' }}>
                  {cat.sample?.slice(0, 2).map((s, i) => (
                    <div
                      key={i}
                      style={{
                        marginTop: 4,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {s.filename || s.email_subject || ''}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Totale */}
          <div
            style={{
              textAlign: 'center',
              padding: 16,
              background: '#f0fdf4',
              borderRadius: 10,
              color: '#059669',
              fontWeight: 700,
            }}
          >
            Totale documenti da mittenti attendibili:{' '}
            {categorieMittente.reduce((s, c) => s + c.count, 0)}
          </div>
        </div>
      )}

      {/* Tab Content Email */}
      {activeTab === 'email' ? (
        <>
          {/* CONTENUTO TAB EMAIL - Statistiche */}
          {stats && (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
                gap: 12,
                marginBottom: 20,
              }}
            >
              <div style={{ ...cardStyle, padding: '10px 12px' }}>
                <div style={{ fontSize: 20, fontWeight: 'bold', color: '#1e293b' }}>
                  {stats.totale}
                </div>
                <div style={{ fontSize: 11, color: '#6b7280' }}>Documenti Totali</div>
              </div>
              <div style={{ ...cardStyle, background: '#dbeafe', padding: '10px 12px' }}>
                <div style={{ fontSize: 20, fontWeight: 'bold', color: '#1e40af' }}>
                  {stats.nuovi}
                </div>
                <div style={{ fontSize: 11, color: '#1e40af' }}>Da Processare</div>
              </div>
              <div style={{ ...cardStyle, background: '#dcfce7', padding: '10px 12px' }}>
                <div style={{ fontSize: 20, fontWeight: 'bold', color: '#166534' }}>
                  {stats.processati}
                </div>
                <div style={{ fontSize: 11, color: '#166534' }}>Processati</div>
              </div>
              <div style={{ ...cardStyle, padding: '10px 12px' }}>
                <div style={{ fontSize: 20, fontWeight: 'bold', color: '#7c3aed' }}>
                  {stats.spazio_disco_mb} MB
                </div>
                <div style={{ fontSize: 11, color: '#6b7280' }}>Spazio Usato</div>
              </div>
            </div>
          )}

          {/* Azione Download Email */}
          <div
            style={{
              ...cardStyle,
              marginBottom: 24,
              background: 'linear-gradient(135deg, #1e40af, #7c3aed)',
            }}
          >
            <div style={{ padding: 24 }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  color: 'white',
                  flexWrap: 'wrap',
                  gap: 16,
                }}
              >
                <div>
                  <div
                    style={{
                      fontSize: 20,
                      fontWeight: 'bold',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                    }}
                  >
                    📧 Scarica Documenti da Email
                  </div>
                  <div style={{ fontSize: 14, opacity: 0.9, marginTop: 4 }}>
                    Controlla la casella email e scarica automaticamente i documenti
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <button
                    onClick={() => setShowImportSettings(!showImportSettings)}
                    style={{
                      ...buttonStyle('rgba(255,255,255,0.2)', 'white'),
                      border: '1px solid rgba(255,255,255,0.3)',
                    }}
                  >
                    ⚙️ Impostazioni
                  </button>
                  <button
                    onClick={handleDownloadFromEmail}
                    disabled={downloading}
                    style={{
                      ...buttonStyle('white', '#1e40af'),
                      padding: '12px 24px',
                    }}
                    data-testid="btn-download-email"
                  >
                    {downloading ? '⏳ Download in corso...' : '📥 Scarica da Email'}
                  </button>
                </div>
              </div>

              {/* Pannello Impostazioni Import */}
              {showImportSettings && (
                <div
                  style={{
                    marginTop: 20,
                    padding: 20,
                    background: 'rgba(255,255,255,0.95)',
                    borderRadius: 12,
                    color: '#1e293b',
                  }}
                >
                  <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 'bold' }}>
                    ⚙️ Impostazioni Importazione
                  </h3>

                  {/* Periodo */}
                  <div style={{ marginBottom: 16 }}>
                    <label
                      style={{
                        display: 'block',
                        marginBottom: 6,
                        fontWeight: 'bold',
                        fontSize: 13,
                      }}
                    >
                      📅 Periodo di ricerca
                    </label>
                    <select
                      value={giorniDownload}
                      onChange={e => setGiorniDownload(Number(e.target.value))}
                      style={{
                        padding: '8px 12px',
                        borderRadius: 6,
                        border: '1px solid #e2e8f0',
                        width: '100%',
                        maxWidth: 300,
                      }}
                    >
                      <option value={10}>Ultimi 10 giorni</option>
                      <option value={30}>Ultimi 30 giorni</option>
                      <option value={60}>Ultimi 60 giorni</option>
                      <option value={90}>Ultimi 90 giorni</option>
                      <option value={180}>Ultimi 6 mesi</option>
                      <option value={365}>Ultimo anno</option>
                      <option value={730}>Ultimi 2 anni</option>
                      <option value={1460}>Dal 2021 (~4 anni)</option>
                    </select>
                  </div>

                  {/* Parole Chiave */}
                  <div style={{ marginBottom: 16 }}>
                    <label
                      style={{
                        display: 'block',
                        marginBottom: 6,
                        fontWeight: 'bold',
                        fontSize: 13,
                      }}
                    >
                      🔍 Parole chiave da cercare nelle email
                    </label>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
                      {DEFAULT_KEYWORDS.map(kw => (
                        <button
                          key={kw.id}
                          onClick={() => toggleKeyword(kw.id)}
                          style={{
                            padding: '6px 12px',
                            borderRadius: 20,
                            border: paroleChiaveSelezionate.includes(kw.id)
                              ? '2px solid #1e3a5f'
                              : '1px solid #e2e8f0',
                            background: paroleChiaveSelezionate.includes(kw.id)
                              ? '#dbeafe'
                              : 'white',
                            color: paroleChiaveSelezionate.includes(kw.id) ? '#1e40af' : '#6b7280',
                            cursor: 'pointer',
                            fontSize: 13,
                            fontWeight: paroleChiaveSelezionate.includes(kw.id) ? 'bold' : 'normal',
                          }}
                        >
                          {paroleChiaveSelezionate.includes(kw.id) ? '✓ ' : ''}
                          {kw.label}
                        </button>
                      ))}
                    </div>

                    {/* Aggiungi nuova parola chiave con varianti */}
                    <div
                      style={{
                        marginBottom: 12,
                        padding: 12,
                        background: '#f8fafc',
                        borderRadius: 8,
                      }}
                    >
                      <label
                        style={{
                          display: 'block',
                          marginBottom: 8,
                          fontWeight: 'bold',
                          fontSize: 12,
                          color: '#475569',
                        }}
                      >
                        ➕ Aggiungi nuova parola chiave personalizzata
                      </label>
                      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                        <input
                          type="text"
                          value={nuovaParolaChiave}
                          onChange={e => setNuovaParolaChiave(e.target.value)}
                          onKeyPress={e => e.key === 'Enter' && addCustomKeyword()}
                          placeholder="Nome keyword (es: Cartella Esattoriale)"
                          style={{
                            flex: 1,
                            padding: '8px 12px',
                            borderRadius: 6,
                            border: '1px solid #e2e8f0',
                            fontSize: 13,
                          }}
                        />
                        <button
                          onClick={addCustomKeyword}
                          disabled={!nuovaParolaChiave.trim()}
                          style={smallButtonStyle('#4f46e5')}
                        >
                          ➕ Aggiungi
                        </button>
                      </div>
                      <p style={{ fontSize: 11, color: '#94a3b8', margin: 0 }}>
                        💡 Ogni keyword può contenere più varianti separate da virgola. Es:
                        &quot;cartella,ader,equitalia&quot;
                      </p>
                    </div>

                    {/* Lista keyword personalizzate esistenti con editor varianti */}
                    {customKeywords.length > 0 && (
                      <div style={{ marginTop: 12 }}>
                        <label
                          style={{
                            display: 'block',
                            marginBottom: 8,
                            fontWeight: 'bold',
                            fontSize: 12,
                            color: '#475569',
                          }}
                        >
                          🏷️ Le tue parole chiave personalizzate
                        </label>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                          {customKeywords.map(kw => (
                            <div
                              key={kw.id}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: 8,
                                padding: 8,
                                background: paroleChiaveSelezionate.includes(kw.id)
                                  ? '#dcfce7'
                                  : '#f0fdf4',
                                borderRadius: 8,
                                border: paroleChiaveSelezionate.includes(kw.id)
                                  ? '2px solid #4caf50'
                                  : '1px solid #e2e8f0',
                              }}
                            >
                              <button
                                onClick={() => toggleKeyword(kw.id)}
                                style={{
                                  width: 24,
                                  height: 24,
                                  borderRadius: 4,
                                  border: '1px solid #4caf50',
                                  background: paroleChiaveSelezionate.includes(kw.id)
                                    ? '#4caf50'
                                    : 'white',
                                  color: paroleChiaveSelezionate.includes(kw.id)
                                    ? 'white'
                                    : '#4caf50',
                                  cursor: 'pointer',
                                  fontSize: 12,
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                }}
                              >
                                {paroleChiaveSelezionate.includes(kw.id) ? '✓' : ''}
                              </button>
                              <div style={{ flex: 1 }}>
                                <div style={{ fontWeight: 'bold', fontSize: 13, color: '#166534' }}>
                                  {kw.label}
                                </div>
                                <div style={{ fontSize: 11, color: '#6b7280' }}>
                                  Varianti: {kw.keywords}
                                </div>
                              </div>
                              <button
                                onClick={() => removeCustomKeyword(kw.id)}
                                style={{
                                  padding: '4px 8px',
                                  borderRadius: 4,
                                  border: 'none',
                                  background: '#fee2e2',
                                  color: '#dc2626',
                                  cursor: 'pointer',
                                  fontSize: 11,
                                }}
                              >
                                ✕
                              </button>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    <p style={{ fontSize: 12, color: '#6b7280', marginTop: 8 }}>
                      💡 Crea parole chiave personalizzate per categorizzare automaticamente i
                      documenti. Es: &quot;cartella esattoriale&quot; creerà una cartella
                      &quot;Cartelle Esattoriali&quot;.
                    </p>
                  </div>

                  {paroleChiaveSelezionate.length === 0 && (
                    <div
                      style={{
                        padding: 12,
                        background: '#fef3c7',
                        borderRadius: 8,
                        fontSize: 13,
                        color: '#92400e',
                      }}
                    >
                      ⚠️ Nessuna parola chiave selezionata. Verranno scaricati TUTTI gli allegati
                      dalle email.
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Popup stato download in background */}
          {downloading && taskStatus && (
            <div
              style={{
                ...cardStyle,
                marginBottom: 24,
                border: '2px solid #1e3a5f',
                background: 'linear-gradient(135deg, #eff6ff, #dbeafe)',
              }}
            >
              <div style={{ padding: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                  <div
                    style={{
                      width: 48,
                      height: 48,
                      borderRadius: '50%',
                      background: '#1e3a5f',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 24,
                    }}
                  >
                    ⏳
                  </div>
                  <div style={{ flex: 1 }}>
                    <div
                      style={{
                        fontWeight: 'bold',
                        fontSize: 16,
                        color: '#1e40af',
                        marginBottom: 4,
                      }}
                    >
                      📧 Download Email in corso...
                    </div>
                    <div style={{ fontSize: 13, color: '#1e3a5f' }}>
                      {taskStatus.message || 'Elaborazione...'}
                    </div>
                    {taskStatus.status === 'in_progress' && (
                      <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
                        Puoi continuare a navigare, ti avviseremo al completamento.
                      </div>
                    )}
                  </div>
                  <div
                    style={{
                      padding: '8px 16px',
                      background: '#dbeafe',
                      borderRadius: 20,
                      fontSize: 12,
                      fontWeight: 'bold',
                      color: '#1e40af',
                    }}
                  >
                    {taskStatus.status === 'pending'
                      ? '⏳ In attesa'
                      : taskStatus.status === 'in_progress'
                        ? '🔄 In esecuzione'
                        : taskStatus.status === 'completed'
                          ? '✅ Completato'
                          : taskStatus.status === 'error'
                            ? '❌ Errore'
                            : '...'}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Filtri */}
          <div style={{ display: 'flex', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 14, color: '#6b7280' }}>🔍</span>
              <select
                value={filtroCategoria}
                onChange={e => setFiltroCategoria(e.target.value)}
                style={{
                  padding: '8px 12px',
                  borderRadius: 6,
                  border: '1px solid #e2e8f0',
                  fontSize: 14,
                }}
              >
                <option value="">Tutte le categorie</option>
                {Object.entries(categories).map(([key, label]) => (
                  <option key={key} value={key}>
                    {CATEGORY_COLORS[key]?.icon} {label}
                  </option>
                ))}
              </select>
            </div>
            <select
              value={filtroStatus}
              onChange={e => setFiltroStatus(e.target.value)}
              style={{
                padding: '8px 12px',
                borderRadius: 6,
                border: '1px solid #e2e8f0',
                fontSize: 14,
              }}
            >
              <option value="">Tutti gli stati</option>
              <option value="nuovo">🔵 Nuovo</option>
              <option value="processato">🟢 Processato</option>
              <option value="errore">🔴 Errore</option>
            </select>

            {/* Contatori per categoria */}
            {stats?.by_category?.map(cat => (
              <div
                key={cat.category}
                style={{
                  padding: '6px 12px',
                  borderRadius: 20,
                  background: CATEGORY_COLORS[cat.category]?.bg || '#f1f5f9',
                  color: CATEGORY_COLORS[cat.category]?.text || '#475569',
                  fontSize: 13,
                  fontWeight: 'bold',
                  cursor: 'pointer',
                }}
                onClick={() =>
                  setFiltroCategoria(cat.category === filtroCategoria ? '' : cat.category)
                }
              >
                {CATEGORY_COLORS[cat.category]?.icon} {cat.category_label}: {cat.count}
                {cat.nuovi > 0 && (
                  <span style={{ marginLeft: 4, color: '#1e3a5f' }}>({cat.nuovi} nuovi)</span>
                )}
              </div>
            ))}
          </div>

          {/* Lista Documenti */}
          <div style={cardStyle}>
            <div
              style={{
                padding: '16px 20px',
                borderBottom: '1px solid #e5e7eb',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <span style={{ fontSize: 18 }}>📄</span>
              <h2 style={{ margin: 0, fontSize: 16 }}>Documenti ({documents.length})</h2>
            </div>
            <div style={{ padding: 16 }}>
              {loading ? (
                <div style={{ textAlign: 'center', padding: 40, color: '#6b7280' }}>
                  ⏳ Caricamento...
                </div>
              ) : documents.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 40, color: '#6b7280' }}>
                  <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.3 }}>📧</div>
                  <p>Nessun documento trovato</p>
                  <p style={{ fontSize: 14 }}>Clicca &quot;Scarica da Email&quot; per iniziare</p>
                </div>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead>
                      <tr style={{ background: '#f8fafc' }}>
                        <th style={{ padding: 12, textAlign: 'left', width: 40 }}>Cat.</th>
                        <th style={{ padding: 12, textAlign: 'left' }}>Nome File</th>
                        <th style={{ padding: 12, textAlign: 'left' }}>Da Email</th>
                        <th style={{ padding: 12, textAlign: 'left' }}>Mittente</th>
                        <th style={{ padding: 12, textAlign: 'center' }}>Data Email</th>
                        <th style={{ padding: 12, textAlign: 'center' }}>Data Doc.</th>
                        <th style={{ padding: 12, textAlign: 'right' }}>Dim.</th>
                        <th style={{ padding: 12, textAlign: 'center' }}>Stato</th>
                        <th style={{ padding: 12, textAlign: 'center' }}>Azioni</th>
                      </tr>
                    </thead>
                    <tbody>
                      {documents.map((doc, idx) => {
                        const catStyle = CATEGORY_COLORS[doc.category] || CATEGORY_COLORS.altro;
                        const statusStyle = STATUS_LABELS[doc.status] || STATUS_LABELS.nuovo;

                        return (
                          <tr
                            key={doc.id || idx}
                            style={{
                              borderBottom: '1px solid #f1f5f9',
                              background: doc.processed ? '#f8fafc' : 'white',
                            }}
                          >
                            <td style={{ padding: 12 }}>
                              <span
                                style={{
                                  display: 'inline-block',
                                  padding: '4px 8px',
                                  borderRadius: 6,
                                  background: catStyle.bg,
                                  fontSize: 16,
                                }}
                                title={doc.category_label}
                              >
                                {catStyle.icon}
                              </span>
                            </td>
                            <td style={{ padding: 12 }}>
                              <div style={{ fontWeight: 'bold', color: '#1e293b' }}>
                                {doc.filename}
                              </div>
                              <div style={{ fontSize: 11, color: '#94a3b8' }}>
                                {doc.category_label}
                              </div>
                            </td>
                            <td style={{ padding: 12, maxWidth: 200 }}>
                              <div
                                style={{
                                  whiteSpace: 'nowrap',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  fontSize: 12,
                                  color: '#6b7280',
                                }}
                                title={doc.email_subject}
                              >
                                {doc.email_subject || '-'}
                              </div>
                            </td>
                            <td style={{ padding: 12, fontSize: 12, color: '#6b7280' }}>
                              {doc.email_from?.split('<')[0]?.trim() || '-'}
                            </td>
                            <td style={{ padding: 12, textAlign: 'center', fontSize: 12 }}>
                              {formatDate(doc.email_date)}
                            </td>
                            <td
                              style={{
                                padding: 12,
                                textAlign: 'center',
                                fontSize: 12,
                                color: '#1e293b',
                                fontWeight: 500,
                              }}
                            >
                              {doc.document_date ? formatDate(doc.document_date) : '-'}
                            </td>
                            <td style={{ padding: 12, textAlign: 'right', fontSize: 12 }}>
                              {formatBytes(doc.size_bytes)}
                            </td>
                            <td style={{ padding: 12, textAlign: 'center' }}>
                              <span
                                style={{
                                  padding: '4px 8px',
                                  borderRadius: 4,
                                  fontSize: 11,
                                  fontWeight: 'bold',
                                  background: statusStyle.bg,
                                  color: statusStyle.color,
                                }}
                              >
                                {statusStyle.label}
                              </span>
                            </td>
                            <td style={{ padding: 12, textAlign: 'center' }}>
                              <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
                                {/* Bottone Visualizza PDF */}
                                <button
                                  onClick={() => handleViewPdf(doc)}
                                  disabled={pdfLoading}
                                  style={{
                                    background: '#dbeafe',
                                    border: 'none',
                                    borderRadius: 4,
                                    padding: '5px 10px',
                                    cursor: 'pointer',
                                    color: '#1e40af',
                                    fontSize: 11,
                                    fontWeight: 500,
                                  }}
                                  title="Visualizza PDF"
                                  data-testid={`view-pdf-${doc.id}`}
                                >
                                  Vedi
                                </button>

                                <button
                                  onClick={() => handleDownloadFile(doc)}
                                  style={{
                                    background: '#f1f5f9',
                                    border: 'none',
                                    borderRadius: 4,
                                    padding: 6,
                                    cursor: 'pointer',
                                  }}
                                  title="Scarica file"
                                >
                                  📥
                                </button>

                                {!doc.processed && (
                                  <select
                                    onChange={e => {
                                      if (e.target.value) {
                                        handleProcessDocument(doc, e.target.value);
                                        e.target.value = '';
                                      }
                                    }}
                                    style={{
                                      padding: '4px 8px',
                                      borderRadius: 4,
                                      border: '1px solid #e2e8f0',
                                      fontSize: 11,
                                      background: '#dbeafe',
                                      cursor: 'pointer',
                                    }}
                                    defaultValue=""
                                  >
                                    <option value="">Carica in...</option>
                                    <option value="f24">F24</option>
                                    <option value="fatture">Fatture</option>
                                    <option value="buste_paga">Buste Paga</option>
                                    <option value="estratto_conto">Estratto Conto</option>
                                    <option value="quietanze">Quietanze</option>
                                  </select>
                                )}

                                <select
                                  onChange={e => {
                                    if (e.target.value && e.target.value !== doc.category) {
                                      handleChangeCategory(doc.id, e.target.value);
                                    }
                                  }}
                                  value={doc.category}
                                  style={{
                                    padding: '4px 8px',
                                    borderRadius: 4,
                                    border: '1px solid #e2e8f0',
                                    fontSize: 11,
                                    cursor: 'pointer',
                                  }}
                                  title="Cambia categoria"
                                >
                                  {Object.entries(categories).map(([key, label]) => (
                                    <option key={key} value={key}>
                                      {label}
                                    </option>
                                  ))}
                                </select>

                                <button
                                  onClick={() => handleDeleteDocument(doc.id)}
                                  style={{
                                    background: '#fef2f2',
                                    border: 'none',
                                    borderRadius: 4,
                                    padding: 6,
                                    cursor: 'pointer',
                                    color: '#dc2626',
                                  }}
                                  title="Elimina"
                                >
                                  🗑️
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>

          {/* Info credenziali */}
          <div
            style={{
              marginTop: 20,
              padding: 16,
              background: '#f8fafc',
              borderRadius: 8,
              fontSize: 13,
              color: '#6b7280',
            }}
          >
            💡 <strong>Configurazione Email:</strong> Le credenziali email sono configurate nel file
            .env del backend (EMAIL_USER e EMAIL_APP_PASSWORD). Il sistema supporta Gmail con App
            Password.
          </div>
        </>
      ) : (
        /* TAB AI ESTRATTI */
        <div>
          {/* Stats AI */}
          {aiStats && (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
                gap: 12,
                marginBottom: 20,
              }}
            >
              <div
                style={{
                  ...cardStyle,
                  padding: '12px 16px',
                  background: 'linear-gradient(135deg, #7c3aed, #a855f7)',
                }}
              >
                <div style={{ fontSize: 24, fontWeight: 'bold', color: 'white' }}>
                  {aiStats.totali?.documenti || 0}
                </div>
                <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.8)' }}>Documenti Totali</div>
              </div>
              <div style={{ ...cardStyle, padding: '12px 16px', background: '#dcfce7' }}>
                <div style={{ fontSize: 24, fontWeight: 'bold', color: '#166534' }}>
                  {aiStats.totali?.ai_processati || 0}
                </div>
                <div style={{ fontSize: 12, color: '#166534' }}>AI Processati</div>
              </div>
              <div style={{ ...cardStyle, padding: '12px 16px', background: '#fef3c7' }}>
                <div style={{ fontSize: 24, fontWeight: 'bold', color: '#92400e' }}>
                  {aiStats.totali?.da_processare || 0}
                </div>
                <div style={{ fontSize: 12, color: '#92400e' }}>Da Processare</div>
              </div>
            </div>
          )}

          {/* Pulsante Processa Email con AI */}
          <div
            style={{
              ...cardStyle,
              padding: 20,
              marginBottom: 20,
              background: 'linear-gradient(135deg, #7c3aed, #a855f7)',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: 16,
              }}
            >
              <div style={{ color: 'white' }}>
                <div
                  style={{
                    fontSize: 18,
                    fontWeight: 'bold',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                  }}
                >
                  🤖 Processa Allegati Email con AI
                </div>
                <div style={{ fontSize: 13, opacity: 0.9, marginTop: 4 }}>
                  Estrae automaticamente i dati dai PDF classificati e li salva nel gestionale
                </div>
              </div>
              <button
                onClick={async () => {
                  setAiLoading(true);
                  try {
                    const res = await api.post(
                      '/api/document-ai/process-all-classified?save_to_gestionale=true'
                    );
                    const r = res.data;
                    alert(
                      `✅ Processamento completato!\n\nDocumenti analizzati: ${r.documenti_analizzati}\nDati estratti: ${r.documenti_estratti}\nSalvati nel gestionale: ${r.documenti_salvati}\nDuplicati saltati: ${r.documenti_duplicati}\nErrori: ${r.errori_estrazione + r.errori_salvataggio}`
                    );
                    loadAiDocuments();
                  } catch (error) {
                    alert(`❌ Errore: ${error.response?.data?.detail || error.message}`);
                  } finally {
                    setAiLoading(false);
                  }
                }}
                disabled={aiLoading}
                style={{
                  ...buttonStyle('white', '#7c3aed'),
                  padding: '12px 24px',
                }}
                data-testid="btn-process-email-ai"
              >
                {aiLoading ? '⏳ Elaborazione...' : '🚀 Processa Allegati Email'}
              </button>
            </div>
          </div>

          {/* Upload nuovo documento */}
          <div style={{ ...cardStyle, padding: 20, marginBottom: 20 }}>
            <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 600, color: '#1e293b' }}>
              📤 Carica Documento per Estrazione AI
            </h3>
            <div
              style={{
                border: '2px dashed #e2e8f0',
                borderRadius: 8,
                padding: 24,
                textAlign: 'center',
                background: '#f8fafc',
              }}
            >
              <input
                type="file"
                accept=".pdf,.png,.jpg,.jpeg"
                onChange={async e => {
                  const file = e.target.files?.[0];
                  if (!file) return;

                  const formData = new FormData();
                  formData.append('file', file);
                  formData.append('save_to_db', 'true');

                  try {
                    setAiLoading(true);
                    const res = await api.post('/api/document-ai/extract', formData, {
                      headers: { 'Content-Type': 'multipart/form-data' },
                    });

                    if (res.data.structured_data?.success) {
                      alert(
                        `✅ Documento estratto con successo!\nTipo: ${res.data.structured_data.document_type}\nSalvato in: ${res.data.gestionale_save?.collection || 'extracted_documents'}`
                      );
                      loadAiDocuments();
                    } else {
                      alert(
                        `⚠️ Estrazione completata con errori: ${res.data.structured_data?.error || 'Unknown'}`
                      );
                    }
                  } catch (error) {
                    alert(`❌ Errore: ${error.response?.data?.detail || error.message}`);
                  } finally {
                    setAiLoading(false);
                    e.target.value = '';
                  }
                }}
                style={{ display: 'none' }}
                id="ai-file-upload"
              />
              <label htmlFor="ai-file-upload" style={{ cursor: 'pointer' }}>
                <div style={{ fontSize: 40, marginBottom: 8 }}>📄</div>
                <div style={{ fontWeight: 600, color: '#1e293b', marginBottom: 4 }}>
                  Clicca per caricare un documento
                </div>
                <div style={{ fontSize: 12, color: '#6b7280' }}>
                  PDF, PNG, JPG (max 20MB) - Il sistema estrarrà automaticamente i dati
                </div>
              </label>
            </div>
          </div>

          {/* Lista documenti estratti */}
          <div style={cardStyle}>
            <div
              style={{
                padding: '16px 20px',
                borderBottom: '1px solid #e2e8f0',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: 12,
              }}
            >
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: '#1e293b' }}>
                🤖 Documenti Estratti con AI (
                {aiDocuments.filter(d => !aiFilterTipo || d.document_type === aiFilterTipo).length})
              </h3>

              {/* Filtro Tipo */}
              <select
                value={aiFilterTipo}
                onChange={e => setAiFilterTipo(e.target.value)}
                style={{
                  padding: '8px 12px',
                  borderRadius: 8,
                  border: '1px solid #e2e8f0',
                  fontSize: 13,
                  background: 'white',
                }}
              >
                <option value="">Tutti i tipi</option>
                <option value="busta_paga">Busta Paga</option>
                <option value="f24">📋 F24</option>
                <option value="bonifico">💸 Bonifico</option>
                <option value="estratto_conto">🏦 Estratto Conto</option>
                <option value="cartella_esattoriale">⚠️ Cartella Esattoriale</option>
                <option value="fattura">📄 Fattura</option>
              </select>
            </div>

            {aiLoading ? (
              <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
                ⏳ Caricamento...
              </div>
            ) : aiDocuments.filter(d => !aiFilterTipo || d.document_type === aiFilterTipo)
                .length === 0 ? (
              <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
                <div style={{ fontSize: 48, marginBottom: 16 }}>🤖</div>
                <div style={{ fontWeight: 600, marginBottom: 8 }}>Nessun documento estratto</div>
                <div style={{ fontSize: 13 }}>
                  Carica un documento PDF per estrarre i dati automaticamente
                </div>
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: '#f8fafc' }}>
                      <th
                        style={{
                          padding: 12,
                          textAlign: 'left',
                          fontWeight: 600,
                          color: '#475569',
                        }}
                      >
                        Tipo
                      </th>
                      <th
                        style={{
                          padding: 12,
                          textAlign: 'left',
                          fontWeight: 600,
                          color: '#475569',
                        }}
                      >
                        Descrizione
                      </th>
                      <th
                        style={{
                          padding: 12,
                          textAlign: 'left',
                          fontWeight: 600,
                          color: '#475569',
                        }}
                      >
                        Periodo
                      </th>
                      <th
                        style={{
                          padding: 12,
                          textAlign: 'center',
                          fontWeight: 600,
                          color: '#475569',
                        }}
                      >
                        OCR
                      </th>
                      <th
                        style={{
                          padding: 12,
                          textAlign: 'left',
                          fontWeight: 600,
                          color: '#475569',
                        }}
                      >
                        Data
                      </th>
                      <th
                        style={{
                          padding: 12,
                          textAlign: 'center',
                          fontWeight: 600,
                          color: '#475569',
                        }}
                      >
                        Azioni
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {aiDocuments
                      .filter(d => !aiFilterTipo || d.document_type === aiFilterTipo)
                      .map((doc, idx) => {
                        // Estrai periodo dai dati
                        const getPeriodo = () => {
                          const data = doc.extracted_data;
                          if (!data) return '-';
                          if (data.periodo?.mese && data.periodo?.anno)
                            return `${data.periodo.mese}/${data.periodo.anno}`;
                          if (data.data_versamento) return formatDateIT(data.data_versamento);
                          if (data.data_operazione) return formatDateIT(data.data_operazione);
                          if (data.data_verbale) return formatDateIT(data.data_verbale);
                          if (data.data_notifica) return formatDateIT(data.data_notifica);
                          if (data.periodo?.da)
                            return `${formatDateIT(data.periodo.da)} - ${data.periodo.a ? formatDateIT(data.periodo.a) : ''}`;
                          if (data.data_fattura) return formatDateIT(data.data_fattura);
                          if (data.data_documento) return formatDateIT(data.data_documento);
                          return '-';
                        };

                        // Funzione per formattare descrizione leggibile
                        const getDescrizione = () => {
                          const data = doc.extracted_data;
                          if (!data) return doc.filename;

                          const tipo = doc.document_type?.toLowerCase();

                          // BUSTA PAGA: "dipendente: VESPA VINCENZO"
                          if (tipo === 'busta_paga') {
                            const nome = data.dipendente?.nome_cognome || data.dipendente || '';
                            return `dipendente: ${nome}`;
                          }

                          // F24: "contribuente: CERALDI GROUP - € 1.234,56"
                          if (tipo === 'f24') {
                            const contribuente =
                              data.contribuente?.denominazione || data.contribuente || '';
                            const importo = data.totale_versato || data.importo_totale || 0;
                            return `contribuente: ${contribuente} - ${formatEuro(Number(importo))}`;
                          }

                          // BONIFICO: "P6325959 : 1 bonifico per totale euro 1.000,00 su Banca 05034 a favore di: Nome"
                          if (tipo === 'bonifico') {
                            const riferimento = data.riferimento || data.cro || '';
                            const importo = data.importo || 0;
                            const beneficiario =
                              data.beneficiario?.denominazione || data.beneficiario || '';
                            const banca = data.banca || '';
                            return `${riferimento} : bonifico ${formatEuro(Number(importo))} ${banca ? `su ${banca}` : ''} a favore di: ${beneficiario}`;
                          }

                          // ESTRATTO CONTO
                          if (tipo === 'estratto_conto') {
                            const banca = data.banca || '';
                            const conto = data.numero_conto || '';
                            return `${banca} - Conto ${conto}`;
                          }

                          // CARTELLA ESATTORIALE
                          if (tipo === 'cartella_esattoriale') {
                            const numero = data.numero_cartella || '';
                            const importo = data.importo_totale || 0;
                            return `Cartella ${numero} - ${formatEuro(Number(importo))}`;
                          }

                          // FATTURA
                          if (tipo === 'fattura') {
                            const numero = data.numero_fattura || '';
                            const fornitore = data.fornitore?.denominazione || data.fornitore || '';
                            const importo = data.importo_totale || 0;
                            return `Fatt. ${numero} - ${fornitore} ${formatEuro(Number(importo))}`;
                          }

                          // Default
                          return doc.filename;
                        };

                        return (
                          <tr key={idx} style={{ borderTop: '1px solid #e2e8f0' }}>
                            <td style={{ padding: 12 }}>
                              <span
                                style={{
                                  display: 'inline-block',
                                  padding: '4px 10px',
                                  borderRadius: 20,
                                  fontSize: 11,
                                  fontWeight: 600,
                                  background: CATEGORY_COLORS[doc.document_type]?.bg || '#f1f5f9',
                                  color: CATEGORY_COLORS[doc.document_type]?.text || '#475569',
                                }}
                              >
                                {CATEGORY_COLORS[doc.document_type]?.icon || '📄'}{' '}
                                {doc.document_type?.toUpperCase().replace('_', ' ')}
                              </span>
                            </td>
                            <td style={{ padding: 12 }}>
                              <div style={{ fontWeight: 500, color: '#1e293b', fontSize: 13 }}>
                                {getDescrizione()}
                              </div>
                              <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>
                                {doc.filename}
                              </div>
                            </td>
                            <td
                              style={{
                                padding: 12,
                                fontSize: 12,
                                color: '#1e293b',
                                fontWeight: 500,
                              }}
                            >
                              {getPeriodo()}
                            </td>
                            <td style={{ padding: 12, textAlign: 'center' }}>
                              {doc.ocr_used ? (
                                <span style={{ color: '#ff9800' }}>📷 Sì</span>
                              ) : (
                                <span style={{ color: '#16a34a' }}>✓ No</span>
                              )}
                            </td>
                            <td style={{ padding: 12, fontSize: 12, color: '#6b7280' }}>
                              {doc.created_at
                                ? new Date(doc.created_at).toLocaleDateString('it-IT')
                                : '-'}
                            </td>
                            <td style={{ padding: 12, textAlign: 'center' }}>
                              <div style={{ display: 'flex', gap: 6, justifyContent: 'center' }}>
                                {doc.file_base64 && (
                                  <button
                                    onClick={() => {
                                      try {
                                        const pdfData = atob(doc.file_base64);
                                        const bytes = new Uint8Array(pdfData.length);
                                        for (let i = 0; i < pdfData.length; i++) {
                                          bytes[i] = pdfData.charCodeAt(i);
                                        }
                                        const blob = new Blob([bytes], { type: 'application/pdf' });
                                        const url = URL.createObjectURL(blob);
                                        setSelectedPdfDoc({ ...doc, pdfUrl: url });
                                      } catch (e) {
                                        alert('PDF non disponibile');
                                      }
                                    }}
                                    style={{
                                      padding: '5px 10px',
                                      background: '#dbeafe',
                                      border: 'none',
                                      borderRadius: 4,
                                      cursor: 'pointer',
                                      fontSize: 11,
                                      fontWeight: 500,
                                      color: '#1e40af',
                                    }}
                                    title="Visualizza PDF"
                                  >
                                    Vedi
                                  </button>
                                )}
                                <button
                                  onClick={async () => {
                                    try {
                                      await api.delete(
                                        `/api/document-ai/extracted-documents/${doc._id || doc.id}`
                                      );
                                      loadAiDocuments();
                                    } catch (e) {
                                      alert(`Errore: ${e.response?.data?.detail || e.message}`);
                                    }
                                  }}
                                  style={{
                                    padding: '5px 10px',
                                    background: '#fee2e2',
                                    border: 'none',
                                    borderRadius: 4,
                                    cursor: 'pointer',
                                    fontSize: 11,
                                    fontWeight: 500,
                                    color: '#dc2626',
                                  }}
                                  title="Elimina documento"
                                >
                                  Elimina
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* PDF Viewer Modal */}
      {selectedPdfDoc && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: 20,
          }}
          onClick={closePdfViewer}
        >
          <div
            style={{
              background: 'white',
              borderRadius: 12,
              width: '90%',
              maxWidth: 1000,
              height: '90vh',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
            }}
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div
              style={{
                padding: '12px 20px',
                borderBottom: '1px solid #e2e8f0',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                background: '#f8fafc',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 20 }}>📄</span>
                <div>
                  <div style={{ fontWeight: 600, color: '#1e293b' }}>{selectedPdfDoc.filename}</div>
                  <div style={{ fontSize: 12, color: '#6b7280' }}>
                    {CATEGORY_COLORS[selectedPdfDoc.category]?.label || selectedPdfDoc.category}
                    {selectedPdfDoc.file_size && ` • ${formatBytes(selectedPdfDoc.file_size)}`}
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  onClick={() => handleDownloadFile(selectedPdfDoc)}
                  style={{
                    background: '#1e3a5f',
                    color: 'white',
                    border: 'none',
                    borderRadius: 6,
                    padding: '8px 16px',
                    cursor: 'pointer',
                    fontSize: 13,
                    fontWeight: 500,
                  }}
                >
                  📥 Scarica
                </button>
                <button
                  onClick={closePdfViewer}
                  style={{
                    background: '#f1f5f9',
                    color: '#6b7280',
                    border: 'none',
                    borderRadius: 6,
                    padding: '8px 16px',
                    cursor: 'pointer',
                    fontSize: 18,
                  }}
                >
                  ✕
                </button>
              </div>
            </div>

            {/* PDF Content */}
            <div style={{ flex: 1, background: '#525659' }}>
              <iframe
                src={selectedPdfDoc.pdfUrl}
                style={{
                  width: '100%',
                  height: '100%',
                  border: 'none',
                }}
                title={selectedPdfDoc.filename}
              />
            </div>
          </div>
        </div>
      )}
    </PageLayout>
  );
}
