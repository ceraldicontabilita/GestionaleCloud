import React, { useState, useEffect, useRef, useCallback } from 'react';
import { toast } from 'sonner';
import {
  formatEuro,
  formatDateIT,
  formatDateGGMM,
  STYLES,
  COLORS,
  BORDER_RADIUS,
  useIsMobile,
} from '../lib/utils';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout } from '../components/PageLayout';
import DocumentViewerModal from '../components/DocumentViewerModal';
import {
  Button,
  Badge,
  Card,
  Input,
  Select,
  Tabs,
  StatCard,
  Table,
  TableWrap,
  Th,
  Td,
  RowActions,
  RowActionButton,
  ListaAdattiva,
} from '../components/ds';

// Palette categorica: colori distintivi per tipo documento (non sono colori di
// stato semantico success/danger/warning/info, quindi restano fuori dalla
// mappatura fissa del design system — servono a distinguere a colpo d'occhio
// le ~10 categorie tra loro, cosa che le varianti di Badge/StatCard non
// permettono di fare con così tante sfumature).
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
  avviso_bonario: {
    bg: '#ffedd5',
    text: '#c2410c',
    icon: '📨',
    label: 'Avvisi Bonari',
  },
  dichiarazione_iva: {
    bg: '#e0e7ff',
    text: '#4338ca',
    icon: '📊',
    label: 'Dichiarazioni IVA',
  },
  satispay: { bg: '#fee7f3', text: '#db2777', icon: '📱', label: 'Satispay' },
  contributi_inps: { bg: '#e0f2fe', text: '#0369a1', icon: '🏛️', label: 'INPS' },
  certificazione_unica: {
    bg: '#ecfccb',
    text: '#4d7c0f',
    icon: '👤',
    label: 'Certificazioni Uniche',
  },
  altro: { bg: '#f1f5f9', text: '#475569', icon: '📄', label: 'Altri' },
};

// Stati documento: mappati sulle varianti semantiche del design system (Badge).
const STATUS_LABELS = {
  nuovo: { label: 'Nuovo', variant: 'primary' },
  processato: { label: 'Processato', variant: 'success' },
  errore: { label: 'Errore', variant: 'danger' },
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
  const isMobile = useIsMobile();
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
  // Mittente selezionato → documenti NON ASSOCIATI di quel mittente
  const [mittenteSelezionato, setMittenteSelezionato] = useState(null);
  const [documentiMittente, setDocumentiMittente] = useState([]);
  const [loadingMittente, setLoadingMittente] = useState(false);

  const apriMittente = async (nome) => {
    setMittenteSelezionato(nome);
    setLoadingMittente(true);
    try {
      const r = await api.get(
        `/api/documenti-non-associati/lista?categoria=${encodeURIComponent(nome)}&limit=200`
      );
      setDocumentiMittente(r.data?.documenti || []);
    } catch (e) {
      toast.error('Documenti del mittente non caricati: ' + (e.response?.data?.detail || e.message));
      setDocumentiMittente([]);
    } finally {
      setLoadingMittente(false);
    }
  };

  // Load categorie mittente (ricaricabile dal bottone "Aggiorna")
  const loadCategorieMittente = async () => {
    try {
      const r = await api.get('/api/documenti-non-associati/categorie-mittente');
      setCategorieMittente(r.data?.categorie || []);
    } catch (e) {
      // Errore del servizio ≠ "nessun mittente": segnalalo.
      toast.error('Categorie mittente non caricate: ' + (e.response?.data?.detail || e.message));
    }
  };
  useEffect(() => {
    loadCategorieMittente();
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
            toast.success('Download completato', {
              description: `Email controllate: ${stats.emails_checked || 0} • Documenti trovati: ${stats.documents_found || 0} • Nuovi documenti: ${stats.new_documents || 0} • Duplicati saltati: ${stats.duplicates_skipped || 0}`,
            });
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
        toast.error('Errore download', {
          description: res.data.error || 'Errore sconosciuto',
        });
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
      toast.warning('Operazione non disponibile', {
        description: `C'è già un'operazione email in corso: ${currentOperation}. Attendere il completamento.`,
      });
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
        toast.success('Download completato', {
          description: `Email controllate: ${stats.emails_checked} • Documenti trovati: ${stats.documents_found} • Nuovi documenti: ${stats.new_documents} • Duplicati saltati: ${stats.duplicates_skipped}`,
        });
        loadData();
        setDownloading(false);
      }
    } catch (error) {
      const detail = error.response?.data?.detail || error.message;
      if (error.response?.status === 423) {
        toast.warning('Operazione bloccata', { description: detail });
      } else {
        toast.error('Errore download', { description: detail });
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
      toast.success('Documento processato', { description: `Spostato in ${destinazione}` });
      loadData();
    } catch (error) {
      toast.error('Errore', { description: error.response?.data?.detail || error.message });
    }
  };

  const handleDeleteDocument = async docId => {
    try {
      await api.delete(`/api/documenti/documento/${docId}`);
      loadData();
    } catch (error) {
      toast.error('Errore', { description: error.response?.data?.detail || error.message });
    }
  };

  const handleChangeCategory = async (docId, newCategory) => {
    try {
      await api.post(
        `/api/documenti/documento/${docId}/cambia-categoria?nuova_categoria=${newCategory}`
      );
      loadData();
    } catch (error) {
      toast.error('Errore', { description: error.response?.data?.detail || error.message });
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
      toast.error('Errore download', { description: error.message });
    }
  };

  // Visualizza PDF: il download del blob, il loading e la revoca dell'URL
  // sono gestiti dal motore condiviso DocumentViewerModal (fetchUrl).
  const handleViewPdf = doc => {
    setSelectedPdfDoc(doc);
  };

  // Chiudi PDF Viewer
  const closePdfViewer = () => {
    setSelectedPdfDoc(null);
  };

  const formatBytes = bytes => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  // Sfondo riga come nella tabella originale: processato = bgAlt, altrimenti card
  const sfondoRiga = doc => ({ background: doc.processed ? COLORS.bgAlt : COLORS.card });

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

  return (
    <PageLayout
      title="Gestione Documenti"
      icon="📨"
      subtitle="Gestisci documenti email e documenti estratti con AI"
      actions={
        <Button
          variant="secondary"
          onClick={
            activeTab === 'categorie'
              ? loadCategorieMittente
              : activeTab === 'email'
                ? loadData
                : loadAiDocuments
          }
          disabled={loading || aiLoading}
          iconLeft={loading || aiLoading ? '⏳' : '🔄'}
        >
          Aggiorna
        </Button>
      }
    >
      {/* Tab Navigation */}
      <div style={{ marginBottom: 20 }}>
        <Tabs
          items={[
            { key: 'categorie', label: 'Per Mittente', icon: '🏛️' },
            { key: 'email', label: 'Tutti i Documenti', icon: '📧' },
            { key: 'ai', label: 'AI Estratti', icon: '🤖' },
          ]}
          value={activeTab}
          onChange={key => {
            setActiveTab(key);
            if (key === 'ai') loadAiDocuments();
          }}
        />
      </div>

      {/* Tab Categorie Mittente */}
      {activeTab === 'categorie' && mittenteSelezionato && (
        <div style={{ marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
            <Button
              variant="secondary"
              onClick={() => { setMittenteSelezionato(null); setDocumentiMittente([]); }}
            >
              ← Torna ai mittenti
            </Button>
            <h3 style={{ margin: 0 }}>
              Documenti non associati — {mittenteSelezionato}
            </h3>
          </div>
          {loadingMittente ? (
            <div style={{ padding: 24, textAlign: 'center', color: COLORS.textMuted }}>Caricamento…</div>
          ) : documentiMittente.length === 0 ? (
            <div style={{ padding: 24, textAlign: 'center', color: COLORS.textMuted }}>
              Nessun documento non associato per {mittenteSelezionato}.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {documentiMittente.map((d, i) => (
                <div key={d.id || i} style={{ ...STYLES.card, padding: 12 }}>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>
                    {d.filename || d.email_subject || 'Documento'}
                  </div>
                  <div style={{ fontSize: 12, color: COLORS.textMuted }}>
                    {d.email_subject ? `${d.email_subject} · ` : ''}{d.email_from || ''}
                    {d.downloaded_at ? ` · ${formatDate(d.downloaded_at)}` : ''}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab Categorie Mittente — griglia mittenti */}
      {activeTab === 'categorie' && !mittenteSelezionato && (
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
                onClick={() => apriMittente(cat.nome)}
                style={{
                  ...STYLES.card,
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  ':hover': { borderColor: COLORS.primary },
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
                      background: COLORS.infoLight,
                      color: COLORS.info,
                      padding: '4px 12px',
                      borderRadius: BORDER_RADIUS.full,
                      fontWeight: 700,
                      fontSize: 14,
                    }}
                  >
                    {cat.count}
                  </span>
                </div>
                <h3 style={{ margin: '0 0 4px', fontSize: 16, fontWeight: 700, color: COLORS.primary }}>
                  {cat.nome}
                </h3>
                <div style={{ fontSize: 12, color: COLORS.textMuted }}>
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
              background: COLORS.successLight,
              borderRadius: BORDER_RADIUS.lg,
              color: COLORS.success,
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
              <StatCard label="Documenti Totali" value={stats.totale} accent="none" />
              <StatCard label="Da Processare" value={stats.nuovi} accent="info" />
              <StatCard label="Processati" value={stats.processati} accent="success" />
              <StatCard label="Spazio Usato" value={`${stats.spazio_disco_mb} MB`} accent="none" />
            </div>
          )}

          {/* Azione Download Email */}
          <Card style={{ marginBottom: 24, background: COLORS.primary }} bodyStyle={{ padding: 24 }}>
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
                <Button
                  variant="ghost"
                  onClick={() => setShowImportSettings(!showImportSettings)}
                  style={{
                    background: 'rgba(255,255,255,0.2)',
                    color: 'white',
                    border: '1px solid rgba(255,255,255,0.3)',
                  }}
                >
                  ⚙️ Impostazioni
                </Button>
                <Button
                  variant="secondary"
                  size="lg"
                  onClick={handleDownloadFromEmail}
                  disabled={downloading}
                  style={{ color: COLORS.info }}
                  data-testid="btn-download-email"
                >
                  {downloading ? '⏳ Download in corso...' : '📥 Scarica da Email'}
                </Button>
              </div>
            </div>

            {/* Pannello Impostazioni Import */}
            {showImportSettings && (
              <div
                style={{
                  marginTop: 20,
                  padding: 20,
                  background: COLORS.card,
                  borderRadius: BORDER_RADIUS.md,
                  color: COLORS.text,
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
                  <Select
                    value={giorniDownload}
                    onChange={e => setGiorniDownload(Number(e.target.value))}
                    style={{ width: '100%', maxWidth: 300 }}
                  >
                    <option value={10}>Ultimi 10 giorni</option>
                    <option value={30}>Ultimi 30 giorni</option>
                    <option value={60}>Ultimi 60 giorni</option>
                    <option value={90}>Ultimi 90 giorni</option>
                    <option value={180}>Ultimi 6 mesi</option>
                    <option value={365}>Ultimo anno</option>
                    <option value={730}>Ultimi 2 anni</option>
                    <option value={1460}>Dal 2021 (~4 anni)</option>
                  </Select>
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
                      <Button
                        key={kw.id}
                        size="sm"
                        variant={paroleChiaveSelezionate.includes(kw.id) ? 'primary' : 'secondary'}
                        onClick={() => toggleKeyword(kw.id)}
                        style={{ borderRadius: BORDER_RADIUS.full }}
                      >
                        {paroleChiaveSelezionate.includes(kw.id) ? '✓ ' : ''}
                        {kw.label}
                      </Button>
                    ))}
                  </div>

                  {/* Aggiungi nuova parola chiave con varianti */}
                  <div
                    style={{
                      marginBottom: 12,
                      padding: 12,
                      background: COLORS.bgAlt,
                      borderRadius: BORDER_RADIUS.md,
                    }}
                  >
                    <label
                      style={{
                        display: 'block',
                        marginBottom: 8,
                        fontWeight: 'bold',
                        fontSize: 12,
                        color: COLORS.gray[600],
                      }}
                    >
                      ➕ Aggiungi nuova parola chiave personalizzata
                    </label>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                      <Input
                        type="text"
                        value={nuovaParolaChiave}
                        onChange={e => setNuovaParolaChiave(e.target.value)}
                        onKeyPress={e => e.key === 'Enter' && addCustomKeyword()}
                        placeholder="Nome keyword (es: Cartella Esattoriale)"
                        style={{ flex: 1 }}
                      />
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={addCustomKeyword}
                        disabled={!nuovaParolaChiave.trim()}
                      >
                        ➕ Aggiungi
                      </Button>
                    </div>
                    <p style={{ fontSize: 11, color: COLORS.textSubtle, margin: 0 }}>
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
                          color: COLORS.gray[600],
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
                                ? COLORS.successLight
                                : COLORS.card,
                              borderRadius: BORDER_RADIUS.md,
                              border: paroleChiaveSelezionate.includes(kw.id)
                                ? `2px solid ${COLORS.success}`
                                : `1px solid ${COLORS.border}`,
                            }}
                          >
                            <Button
                              size="sm"
                              variant={paroleChiaveSelezionate.includes(kw.id) ? 'success' : 'secondary'}
                              onClick={() => toggleKeyword(kw.id)}
                              style={{
                                width: 24,
                                height: 24,
                                padding: 0,
                                borderRadius: BORDER_RADIUS.sm,
                                borderColor: COLORS.success,
                                color: paroleChiaveSelezionate.includes(kw.id) ? '#fff' : COLORS.success,
                              }}
                            >
                              {paroleChiaveSelezionate.includes(kw.id) ? '✓' : ''}
                            </Button>
                            <div style={{ flex: 1 }}>
                              <div style={{ fontWeight: 'bold', fontSize: 13, color: COLORS.success }}>
                                {kw.label}
                              </div>
                              <div style={{ fontSize: 11, color: COLORS.textMuted }}>
                                Varianti: {kw.keywords}
                              </div>
                            </div>
                            <Button
                              variant="danger"
                              size="sm"
                              onClick={() => removeCustomKeyword(kw.id)}
                              style={{ padding: '4px 8px', fontSize: 11 }}
                            >
                              ✕
                            </Button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <p style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 8 }}>
                    💡 Crea parole chiave personalizzate per categorizzare automaticamente i
                    documenti. Es: &quot;cartella esattoriale&quot; creerà una cartella
                    &quot;Cartelle Esattoriali&quot;.
                  </p>
                </div>

                {paroleChiaveSelezionate.length === 0 && (
                  <div
                    style={{
                      padding: 12,
                      background: COLORS.warningLight,
                      borderRadius: BORDER_RADIUS.md,
                      fontSize: 13,
                      color: COLORS.warning,
                    }}
                  >
                    ⚠️ Nessuna parola chiave selezionata. Verranno scaricati TUTTI gli allegati
                    dalle email.
                  </div>
                )}
              </div>
            )}
          </Card>

          {/* Popup stato download in background */}
          {downloading && taskStatus && (
            <Card
              style={{ marginBottom: 24, border: `2px solid ${COLORS.primary}`, background: COLORS.infoLight }}
              bodyStyle={{ padding: 16 }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: BORDER_RADIUS.full,
                    background: COLORS.primary,
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
                      color: COLORS.info,
                      marginBottom: 4,
                    }}
                  >
                    📧 Download Email in corso...
                  </div>
                  <div style={{ fontSize: 13, color: COLORS.primary }}>
                    {taskStatus.message || 'Elaborazione...'}
                  </div>
                  {taskStatus.status === 'in_progress' && (
                    <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>
                      Puoi continuare a navigare, ti avviseremo al completamento.
                    </div>
                  )}
                </div>
                <Badge variant="info">
                  {taskStatus.status === 'pending'
                    ? '⏳ In attesa'
                    : taskStatus.status === 'in_progress'
                      ? '🔄 In esecuzione'
                      : taskStatus.status === 'completed'
                        ? '✅ Completato'
                        : taskStatus.status === 'error'
                          ? '❌ Errore'
                          : '...'}
                </Badge>
              </div>
            </Card>
          )}

          {/* Filtri */}
          <div style={{ display: 'flex', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 14, color: COLORS.textMuted }}>🔍</span>
              <Select value={filtroCategoria} onChange={e => setFiltroCategoria(e.target.value)}>
                <option value="">Tutte le categorie</option>
                {Object.entries(categories).map(([key, label]) => (
                  <option key={key} value={key}>
                    {CATEGORY_COLORS[key]?.icon} {label}
                  </option>
                ))}
              </Select>
            </div>
            <Select value={filtroStatus} onChange={e => setFiltroStatus(e.target.value)}>
              <option value="">Tutti gli stati</option>
              <option value="nuovo">🔵 Nuovo</option>
              <option value="processato">🟢 Processato</option>
              <option value="errore">🔴 Errore</option>
            </Select>

            {/* Contatori per categoria */}
            {stats?.by_category?.map(cat => (
              <div
                key={cat.category}
                style={{
                  padding: '6px 12px',
                  borderRadius: BORDER_RADIUS.full,
                  background: CATEGORY_COLORS[cat.category]?.bg || COLORS.gray[100],
                  color: CATEGORY_COLORS[cat.category]?.text || COLORS.gray[700],
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
                  <span style={{ marginLeft: 4, color: COLORS.primary }}>({cat.nuovi} nuovi)</span>
                )}
              </div>
            ))}
          </div>

          {/* Lista Documenti */}
          <Card title={`Documenti (${documents.length})`} icon="📄" bodyStyle={{ padding: 16 }}>
            {loading ? (
              <div style={{ textAlign: 'center', padding: 40, color: COLORS.textMuted }}>
                ⏳ Caricamento...
              </div>
            ) : documents.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 40, color: COLORS.textMuted }}>
                <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.3 }}>📧</div>
                <p>Nessun documento trovato</p>
                <p style={{ fontSize: 14 }}>Clicca &quot;Scarica da Email&quot; per iniziare</p>
              </div>
            ) : (
              <ListaAdattiva
                testId="documenti-table"
                dati={documents}
                pageSize={50}
                chiave={(doc, i) => doc.id || i}
                colonne={[
                  {
                    // Su mobile l'icona categoria è nel titolo (vedi Nome File)
                    key: 'category',
                    label: 'Cat.',
                    ruoloCard: 'omesso',
                    render: doc => {
                      const catStyle = CATEGORY_COLORS[doc.category] || CATEGORY_COLORS.altro;
                      return (
                        <span
                          style={{
                            display: 'inline-block',
                            padding: '4px 8px',
                            borderRadius: BORDER_RADIUS.sm,
                            background: catStyle.bg,
                            fontSize: 16,
                          }}
                          title={doc.category_label}
                        >
                          {catStyle.icon}
                        </span>
                      );
                    },
                    tdStyle: sfondoRiga,
                  },
                  {
                    key: 'filename',
                    label: 'Nome File',
                    ruoloCard: 'titolo',
                    render: doc => {
                      const catStyle = CATEGORY_COLORS[doc.category] || CATEGORY_COLORS.altro;
                      return (
                        <>
                          <div style={{ fontWeight: 'bold', color: COLORS.text }}>
                            {isMobile ? `${catStyle.icon} ` : ''}
                            {doc.filename}
                          </div>
                          <div style={{ fontSize: 11, color: COLORS.textSubtle }}>
                            {doc.category_label}
                          </div>
                        </>
                      );
                    },
                    tdStyle: sfondoRiga,
                  },
                  {
                    // Oggetto email lungo: solo desktop, su mobile basta il mittente
                    key: 'email_subject',
                    label: 'Da Email',
                    ruoloCard: 'omesso',
                    render: doc => (
                      <div
                        style={{
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          fontSize: 12,
                          color: COLORS.textMuted,
                        }}
                        title={doc.email_subject}
                      >
                        {doc.email_subject || '-'}
                      </div>
                    ),
                    tdStyle: doc => ({ ...sfondoRiga(doc), maxWidth: 200 }),
                  },
                  {
                    key: 'email_from',
                    label: 'Mittente',
                    ruoloCard: 'sottotitolo',
                    render: doc => doc.email_from?.split('<')[0]?.trim() || '-',
                    tdStyle: doc => ({
                      ...sfondoRiga(doc),
                      fontSize: 12,
                      color: COLORS.textMuted,
                    }),
                  },
                  {
                    key: 'email_date',
                    label: 'Data Email',
                    align: 'center',
                    ruoloCard: 'dettaglio',
                    iconaCard: '📅',
                    // Su mobile solo giorno/mese: la data completa con orario
                    // faceva andare a capo la riga dettagli della card
                    render: doc =>
                      isMobile ? formatDateGGMM(doc.email_date) : formatDate(doc.email_date),
                    tdStyle: doc => ({ ...sfondoRiga(doc), fontSize: 12 }),
                  },
                  {
                    key: 'document_date',
                    label: 'Data Doc.',
                    align: 'center',
                    ruoloCard: 'dettaglio',
                    hideMobile: true, // spesso vuota: su mobile basta la data email
                    render: doc => (doc.document_date ? formatDate(doc.document_date) : '-'),
                    tdStyle: doc => ({
                      ...sfondoRiga(doc),
                      fontSize: 12,
                      color: COLORS.text,
                      fontWeight: 500,
                    }),
                  },
                  {
                    key: 'size_bytes',
                    label: 'Dim.',
                    align: 'right',
                    mono: true,
                    ruoloCard: 'dettaglio',
                    iconaCard: '💾',
                    render: doc => formatBytes(doc.size_bytes),
                    tdStyle: doc => ({ ...sfondoRiga(doc), fontSize: 12 }),
                  },
                  {
                    key: 'status',
                    label: 'Stato',
                    align: 'center',
                    ruoloCard: 'dettaglio',
                    render: doc => {
                      const statusStyle = STATUS_LABELS[doc.status] || STATUS_LABELS.nuovo;
                      return <Badge variant={statusStyle.variant}>{statusStyle.label}</Badge>;
                    },
                    tdStyle: sfondoRiga,
                  },
                  {
                    key: 'azioni',
                    label: 'Azioni',
                    align: 'center',
                    ruoloCard: 'azioni',
                    render: doc => (
                      <RowActions style={{ justifyContent: 'center' }}>
                        {/* Bottone Visualizza PDF */}
                        <Button
                          variant="info"
                          size="sm"
                          onClick={() => handleViewPdf(doc)}
                          title="Visualizza PDF"
                          data-testid={`view-pdf-${doc.id}`}
                        >
                          Vedi
                        </Button>

                        <RowActionButton onClick={() => handleDownloadFile(doc)} title="Scarica file">
                          📥
                        </RowActionButton>

                        {!doc.processed && (
                          <Select
                            onChange={e => {
                              if (e.target.value) {
                                handleProcessDocument(doc, e.target.value);
                                e.target.value = '';
                              }
                            }}
                            style={{ padding: '4px 8px', fontSize: 11, background: COLORS.infoLight }}
                            defaultValue=""
                          >
                            <option value="">Carica in...</option>
                            <option value="f24">F24</option>
                            <option value="fatture">Fatture</option>
                            <option value="buste_paga">Buste Paga</option>
                            <option value="estratto_conto">Estratto Conto</option>
                            <option value="quietanze">Quietanze</option>
                          </Select>
                        )}

                        <Select
                          onChange={e => {
                            if (e.target.value && e.target.value !== doc.category) {
                              handleChangeCategory(doc.id, e.target.value);
                            }
                          }}
                          value={doc.category}
                          style={{ padding: '4px 8px', fontSize: 11 }}
                          title="Cambia categoria"
                        >
                          {Object.entries(categories).map(([key, label]) => (
                            <option key={key} value={key}>
                              {label}
                            </option>
                          ))}
                        </Select>

                        <RowActionButton
                          variant="danger"
                          onClick={() => handleDeleteDocument(doc.id)}
                          title="Elimina"
                        >
                          🗑️
                        </RowActionButton>
                      </RowActions>
                    ),
                    tdStyle: sfondoRiga,
                  },
                ]}
              />
            )}
          </Card>

          {/* Info credenziali */}
          <div
            style={{
              marginTop: 20,
              padding: 16,
              background: COLORS.bgAlt,
              borderRadius: BORDER_RADIUS.md,
              fontSize: 13,
              color: COLORS.textMuted,
            }}
          >
            💡 <strong>Configurazione Email:</strong> Le credenziali email sono configurate nel file
            .env del backend (EMAIL_USER e EMAIL_APP_PASSWORD). Il sistema supporta Gmail con App
            Password.
          </div>
        </>
      ) : activeTab === 'ai' ? (
        /* TAB AI ESTRATTI — solo quando il tab AI è attivo: prima il ramo
           "else" del ternario faceva comparire questo blocco anche sotto il
           tab Categorie (default), sovrapponendo i due moduli. */
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
              <StatCard label="Documenti Totali" value={aiStats.totali?.documenti || 0} accent="primary" />
              <StatCard label="AI Processati" value={aiStats.totali?.ai_processati || 0} accent="success" />
              <StatCard label="Da Processare" value={aiStats.totali?.da_processare || 0} accent="warning" />
            </div>
          )}

          {/* Pulsante Processa Email con AI */}
          <Card style={{ marginBottom: 20, background: COLORS.primary }} bodyStyle={{ padding: 20 }}>
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
              <Button
                variant="secondary"
                size="lg"
                onClick={async () => {
                  setAiLoading(true);
                  try {
                    const res = await api.post(
                      '/api/document-ai/process-all-classified?save_to_gestionale=true'
                    );
                    const r = res.data;
                    toast.success('Processamento completato', {
                      description: `Documenti analizzati: ${r.documenti_analizzati} • Dati estratti: ${r.documenti_estratti} • Salvati nel gestionale: ${r.documenti_salvati} • Duplicati saltati: ${r.documenti_duplicati} • Errori: ${r.errori_estrazione + r.errori_salvataggio}`,
                    });
                    loadAiDocuments();
                  } catch (error) {
                    toast.error('Errore', { description: error.response?.data?.detail || error.message });
                  } finally {
                    setAiLoading(false);
                  }
                }}
                disabled={aiLoading}
                style={{ color: COLORS.purple }}
                data-testid="btn-process-email-ai"
              >
                {aiLoading ? '⏳ Elaborazione...' : '🚀 Processa Allegati Email'}
              </Button>
            </div>
          </Card>

          {/* Upload nuovo documento */}
          <Card style={{ marginBottom: 20 }} bodyStyle={{ padding: 20 }}>
            <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 600, color: COLORS.text }}>
              📤 Carica Documento per Estrazione AI
            </h3>
            <div
              style={{
                border: `2px dashed ${COLORS.border}`,
                borderRadius: BORDER_RADIUS.md,
                padding: 24,
                textAlign: 'center',
                background: COLORS.bgAlt,
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
                      toast.success('Documento estratto con successo', {
                        description: `Tipo: ${res.data.structured_data.document_type} • Salvato in: ${res.data.gestionale_save?.collection || 'extracted_documents'}`,
                      });
                      loadAiDocuments();
                    } else {
                      toast.warning('Estrazione completata con errori', {
                        description: res.data.structured_data?.error || 'Unknown',
                      });
                    }
                  } catch (error) {
                    toast.error('Errore', { description: error.response?.data?.detail || error.message });
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
                <div style={{ fontWeight: 600, color: COLORS.text, marginBottom: 4 }}>
                  Clicca per caricare un documento
                </div>
                <div style={{ fontSize: 12, color: COLORS.textMuted }}>
                  PDF, PNG, JPG (max 20MB) - Il sistema estrarrà automaticamente i dati
                </div>
              </label>
            </div>
          </Card>

          {/* Lista documenti estratti */}
          <Card
            title={`Documenti Estratti con AI (${
              aiDocuments.filter(d => !aiFilterTipo || d.document_type === aiFilterTipo).length
            })`}
            icon="🤖"
            actions={
              <Select value={aiFilterTipo} onChange={e => setAiFilterTipo(e.target.value)}>
                <option value="">Tutti i tipi</option>
                <option value="busta_paga">Busta Paga</option>
                <option value="f24">📋 F24</option>
                <option value="bonifico">💸 Bonifico</option>
                <option value="estratto_conto">🏦 Estratto Conto</option>
                <option value="cartella_esattoriale">⚠️ Cartella Esattoriale</option>
                <option value="fattura">📄 Fattura</option>
              </Select>
            }
            bodyStyle={{ padding: 0 }}
          >
            {aiLoading ? (
              <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>
                ⏳ Caricamento...
              </div>
            ) : aiDocuments.filter(d => !aiFilterTipo || d.document_type === aiFilterTipo)
                .length === 0 ? (
              <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>
                <div style={{ fontSize: 48, marginBottom: 16 }}>🤖</div>
                <div style={{ fontWeight: 600, marginBottom: 8 }}>Nessun documento estratto</div>
                <div style={{ fontSize: 13 }}>
                  Carica un documento PDF per estrarre i dati automaticamente
                </div>
              </div>
            ) : (
              <TableWrap style={{ border: 'none', borderRadius: 0 }}>
                <Table>
                  <thead>
                    <tr>
                      <Th>Tipo</Th>
                      <Th>Descrizione</Th>
                      <Th>Periodo</Th>
                      <Th align="center">OCR</Th>
                      <Th>Data</Th>
                      <Th align="center">Azioni</Th>
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
                          <tr key={idx}>
                            <Td>
                              <span
                                style={{
                                  display: 'inline-block',
                                  padding: '4px 10px',
                                  borderRadius: BORDER_RADIUS.full,
                                  fontSize: 11,
                                  fontWeight: 600,
                                  background: CATEGORY_COLORS[doc.document_type]?.bg || COLORS.gray[100],
                                  color: CATEGORY_COLORS[doc.document_type]?.text || COLORS.gray[700],
                                }}
                              >
                                {CATEGORY_COLORS[doc.document_type]?.icon || '📄'}{' '}
                                {doc.document_type?.toUpperCase().replace('_', ' ')}
                              </span>
                            </Td>
                            <Td>
                              <div style={{ fontWeight: 500, color: COLORS.text, fontSize: 13 }}>
                                {getDescrizione()}
                              </div>
                              <div style={{ fontSize: 11, color: COLORS.textSubtle, marginTop: 2 }}>
                                {doc.filename}
                              </div>
                            </Td>
                            <Td
                              style={{
                                fontSize: 12,
                                color: COLORS.text,
                                fontWeight: 500,
                              }}
                            >
                              {getPeriodo()}
                            </Td>
                            <Td align="center">
                              {doc.ocr_used ? (
                                <span style={{ color: COLORS.warning }}>📷 Sì</span>
                              ) : (
                                <span style={{ color: COLORS.success }}>✓ No</span>
                              )}
                            </Td>
                            <Td style={{ fontSize: 12, color: COLORS.textMuted }}>
                              {doc.created_at
                                ? new Date(doc.created_at).toLocaleDateString('it-IT').replaceAll('/', '-')
                                : '-'}
                            </Td>
                            <Td align="center">
                              <RowActions style={{ justifyContent: 'center' }}>
                                {doc.file_base64 && (
                                  <Button
                                    variant="info"
                                    size="sm"
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
                                        toast.error('PDF non disponibile');
                                      }
                                    }}
                                    title="Visualizza PDF"
                                  >
                                    Vedi
                                  </Button>
                                )}
                                <Button
                                  variant="danger"
                                  size="sm"
                                  onClick={async () => {
                                    try {
                                      await api.delete(
                                        `/api/document-ai/extracted-documents/${doc._id || doc.id}`
                                      );
                                      loadAiDocuments();
                                    } catch (e) {
                                      toast.error('Errore', {
                                        description: e.response?.data?.detail || e.message,
                                      });
                                    }
                                  }}
                                  title="Elimina documento"
                                >
                                  Elimina
                                </Button>
                              </RowActions>
                            </Td>
                          </tr>
                        );
                      })}
                  </tbody>
                </Table>
              </TableWrap>
            )}
          </Card>
        </div>
      ) : null}

      {/* PDF Viewer Modal — motore condiviso "Vedi Documento" */}
      {selectedPdfDoc && (
        <DocumentViewerModal
          title={`📄 ${selectedPdfDoc.filename}`}
          subtitle={`${CATEGORY_COLORS[selectedPdfDoc.category]?.label || selectedPdfDoc.category}${
            selectedPdfDoc.file_size ? ` • ${formatBytes(selectedPdfDoc.file_size)}` : ''
          }`}
          fetchUrl={`/api/documenti/documento/${selectedPdfDoc.id}/download`}
          onClose={closePdfViewer}
          onDownload={() => handleDownloadFile(selectedPdfDoc)}
          maxWidth={1000}
        />
      )}
    </PageLayout>
  );
}
