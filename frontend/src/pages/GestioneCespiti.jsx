import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../api';
import { toast } from 'sonner';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout } from '../components/PageLayout';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { useConfirm } from '../components/ui/ConfirmDialog';
import {
  Building2,
  Users,
  Calendar,
  Calculator,
  AlertTriangle,
  Plus,
  Pencil,
  Trash2,
  X,
  Check,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { formatEuro, formatDateIT, useIsMobile } from '../lib/utils';

const MONO = 'ui-monospace, SFMono-Regular, Menlo, monospace';

const styles = {
  container: { padding: 12, maxWidth: 1200, margin: '0 auto' },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  title: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#1e293b',
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  label: { fontSize: 11, fontWeight: '500', color: '#475569', marginBottom: 4, display: 'block' },
  grid2: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 8 },
  grid3: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 8 },
  grid4: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 8 },
  card: {
    background: 'white',
    borderRadius: 8,
    border: '1px solid #e2e8f0',
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
    marginBottom: 12,
  },
  cardContent: { padding: 8 },
  input: { height: 28, fontSize: 12 },
  btn: { minHeight: 40, fontSize: 13 },
  // I call-site passano la tinta di sfondo (statBox) e i colori di
  // etichetta/valore (statLabel/statValue): vanno rispettati, con fallback
  // neutro quando non indicati.
  statBox: (bg = 'white') => ({
    background: bg,
    border: '1px solid #e2e8f0',
    borderLeft: '4px solid #0f2744',
    padding: '8px 10px',
    borderRadius: 8,
    textAlign: 'left',
  }),
  statLabel: (color = '#64748b') => ({
    fontSize: 10,
    color,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  }),
  statValue: (color = '#0f2744') => ({ fontSize: 22, fontWeight: 700, color, fontFamily: MONO }),
  table: { width: '100%', fontSize: 12, borderCollapse: 'collapse' },
  th: {
    padding: '8px',
    textAlign: 'left',
    background: '#f8fafc',
    fontWeight: '600',
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    color: '#64748b',
  },
  thRight: {
    padding: '8px',
    textAlign: 'right',
    background: '#f8fafc',
    fontWeight: '600',
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    color: '#64748b',
  },
  thCenter: {
    padding: '8px',
    textAlign: 'center',
    background: '#f8fafc',
    fontWeight: '600',
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    color: '#64748b',
  },
  td: { padding: '8px', borderBottom: '1px solid #f1f5f9', fontSize: 13 },
  tdRight: {
    padding: '8px',
    borderBottom: '1px solid #f1f5f9',
    textAlign: 'right',
    fontSize: 13,
    fontFamily: MONO,
  },
  tdCenter: {
    padding: '8px',
    borderBottom: '1px solid #f1f5f9',
    textAlign: 'center',
    fontSize: 13,
  },
  row: { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  icon: { width: 12, height: 12 },
  iconMd: { width: 16, height: 16 },
  iconLg: { width: 20, height: 20 },
  small: { fontSize: 11, color: '#64748b' },
  urgentBox: {
    background: '#fef2f2',
    border: '1px solid #fecaca',
    borderRadius: 8,
    padding: 8,
    marginBottom: 12,
  },
  formCard: {
    background: 'white',
    border: '1px solid #e2e8f0',
    borderRadius: 8,
    padding: 8,
    marginBottom: 12,
  },
};

export default function GestioneCespiti() {
  const isMobile = useIsMobile();
  const { anno } = useAnnoGlobale();
  const confirm = useConfirm();
  // URL Tab Support
  const navigate = useNavigate();
  const location = useLocation();

  const getTabFromPath = () => {
    const path = location.pathname;
    const match = path.match(/\/contabilita\/cespiti\/([\w-]+)/);
    return match ? match[1] : 'cespiti';
  };

  const [activeTab, setActiveTab] = useState(getTabFromPath());

  const handleTabChange = tabId => {
    setActiveTab(tabId);
    navigate(`/contabilita/cespiti/${tabId}`);
  };

  useEffect(() => {
    const tab = getTabFromPath();
    if (tab !== activeTab) setActiveTab(tab);
  }, [location.pathname]);
  const [loading, setLoading] = useState(false);
  const [cespiti, setCespiti] = useState([]);
  const [riepilogoCespiti, setRiepilogoCespiti] = useState(null);
  const [verificaAmmortamenti, setVerificaAmmortamenti] = useState(null);
  const [errorePagina, setErrorePagina] = useState('');
  const [categorie, setCategorie] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [nuovoCespite, setNuovoCespite] = useState({
    descrizione: '',
    categoria: '',
    data_acquisto: '',
    data_entrata_funzione: '',
    valore_acquisto: '',
    fornitore: '',
  });
  const [riepilogoTFR, setRiepilogoTFR] = useState(null);
  const [registroTFRAperto, setRegistroTFRAperto] = useState(null); // dipendente_id espanso
  const [registroTFRDettaglio, setRegistroTFRDettaglio] = useState(null);
  const [registroTFRLoading, setRegistroTFRLoading] = useState(false);
  const [scadenzario, setScadenzario] = useState(null);
  const [urgenti, setUrgenti] = useState(null);
  const [editingCespite, setEditingCespite] = useState(null);
  const [editData, setEditData] = useState({});

  useEffect(() => {
    const controller = new AbortController();
    if (activeTab === 'cespiti') {
      loadCespiti(controller.signal);
      loadCategorie(controller.signal);
    } else if (activeTab === 'tfr') {
      loadTFR(controller.signal);
    } else if (activeTab === 'scadenzario') {
      loadScadenzario(controller.signal);
    }
    return () => controller.abort();
  }, [activeTab, anno]);

  const richiestaGet = (url, signal) => (signal ? api.get(url, { signal }) : api.get(url));

  const loadCespiti = async signal => {
    try {
      setLoading(true);
      setErrorePagina('');
      const [c, r, v] = await Promise.all([
        richiestaGet('/api/cespiti/?attivi=true', signal),
        richiestaGet('/api/cespiti/riepilogo', signal),
        richiestaGet(`/api/cespiti/verifica/${anno}`, signal),
      ]);
      setCespiti(c.data);
      setRiepilogoCespiti(r.data);
      setVerificaAmmortamenti(v.data);
    } catch (e) {
      if (signal?.aborted) return;
      console.error(e);
      setErrorePagina(e.response?.data?.detail || e.message || 'Errore caricamento cespiti');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  };
  const loadCategorie = async signal => {
    try {
      const r = await richiestaGet('/api/cespiti/categorie', signal);
      setCategorie(r.data.categorie);
    } catch (e) {
      if (signal?.aborted) return;
      console.error(e);
      setErrorePagina(e.response?.data?.detail || e.message || 'Errore caricamento categorie');
    }
  };
  const loadTFR = async signal => {
    try {
      setLoading(true);
      setErrorePagina('');
      const r = await richiestaGet(`/api/tfr/riepilogo-aziendale?anno=${anno}`, signal);
      setRiepilogoTFR(r.data);
    } catch (e) {
      if (signal?.aborted) return;
      console.error(e);
      setErrorePagina(e.response?.data?.detail || e.message || 'Errore caricamento TFR');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  };
  const toggleRegistroTFR = async dipendenteId => {
    if (registroTFRAperto === dipendenteId) {
      setRegistroTFRAperto(null);
      setRegistroTFRDettaglio(null);
      return;
    }
    setRegistroTFRAperto(dipendenteId);
    setRegistroTFRDettaglio(null);
    try {
      setRegistroTFRLoading(true);
      const r = await api.get(`/api/tfr/situazione/${dipendenteId}`);
      setRegistroTFRDettaglio(r.data);
    } catch (e) {
      toast.error('Errore: ' + (e.response?.data?.detail || e.message));
    } finally {
      setRegistroTFRLoading(false);
    }
  };

  const loadScadenzario = async signal => {
    try {
      setLoading(true);
      setErrorePagina('');
      const [s, u] = await Promise.all([
        richiestaGet(`/api/scadenzario-fornitori/?anno=${anno}`, signal),
        richiestaGet('/api/scadenzario-fornitori/urgenti', signal),
      ]);
      setScadenzario(s.data);
      setUrgenti(u.data);
    } catch (e) {
      if (signal?.aborted) return;
      console.error(e);
      setErrorePagina(e.response?.data?.detail || e.message || 'Errore caricamento scadenzario');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  };

  const handleCreaCespite = async () => {
    if (
      !nuovoCespite.descrizione ||
      !nuovoCespite.categoria ||
      !nuovoCespite.data_acquisto ||
      !nuovoCespite.data_entrata_funzione ||
      !nuovoCespite.valore_acquisto
    )
      return toast.warning('Campi obbligatori');
    try {
      await api.post('/api/cespiti/', {
        ...nuovoCespite,
        valore_acquisto: parseFloat(nuovoCespite.valore_acquisto),
      });
      setShowForm(false);
      setNuovoCespite({
        descrizione: '',
        categoria: '',
        data_acquisto: '',
        data_entrata_funzione: '',
        valore_acquisto: '',
        fornitore: '',
      });
      loadCespiti();
    } catch (e) {
      toast.error('Errore: ' + (e.response?.data?.detail || e.message));
    }
  };

  const handleCalcolaAmm = async () => {
    try {
      setLoading(true);
      const preview = await api.get(`/api/cespiti/calcolo/${anno}`);
      if (preview.data.num_da_verificare > 0) {
        toast.error(
          `${preview.data.num_da_verificare} cespiti senza entrata in funzione confermata`
        );
        return;
      }
      if (preview.data.num_cespiti === 0) {
        toast.info('Nessuna quota da registrare.');
        return;
      }
      const oggi = new Date();
      const fineEsercizio = new Date(Number(anno), 11, 31, 0, 0, 0);
      if (oggi < fineEsercizio) {
        toast.info(
          `Anteprima ${anno}: ${preview.data.num_cespiti} cespiti, ${formatEuro(preview.data.totale_ammortamenti)}. Registrazione definitiva dal 31/12/${anno}.`
        );
        return;
      }
      const ok = await confirm({
        title: `Registra ammortamenti ${anno}`,
        message: `Registrare definitivamente ${preview.data.num_cespiti} quote per ${formatEuro(preview.data.totale_ammortamenti)}?`,
        variant: 'danger',
      });
      if (!ok) return;
      const r = await api.post(`/api/cespiti/registra/${anno}?conferma=true`);
      toast.success(r?.data?.messaggio);
      loadCespiti();
    } catch (e) {
      toast.error('Errore: ' + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  };

  const handleScanFatture = async () => {
    try {
      setLoading(true);
      const preview = await api.post('/api/cespiti/scan-fatture?soglia_valore=200&dry_run=true');
      if (preview.data.num_potenziali_cespiti === 0) {
        toast.info('Nessun nuovo cespite trovato nelle fatture XML.');
        return;
      }
      const ok = await confirm({
        title: 'Importa proposte da fatture XML',
        message: `${preview.data.num_potenziali_cespiti} proposte per ${formatEuro(preview.data.valore_totale)}. Saranno inserite come da verificare, senza ammortamento automatico.`,
      });
      if (!ok) return;
      const r = await api.post('/api/cespiti/scan-fatture?soglia_valore=200&dry_run=false');
      if (r.data.cespiti_creati > 0) {
        toast.success(r?.data?.messaggio, {
          description: `Valore totale: EUR ${r?.data?.valore_totale?.toLocaleString('it-IT')}`,
        });
      } else {
        toast.info('Nessun nuovo cespite trovato nelle fatture XML.');
      }
      loadCespiti();
    } catch (e) {
      toast.error('Errore scan: ' + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  };

  const handleEditCespite = cespite => {
    setEditingCespite(cespite.id);
    setEditData({
      descrizione: cespite.descrizione,
      fornitore: cespite.fornitore || '',
      note: cespite.note || '',
      valore_acquisto: cespite.valore_acquisto,
      data_acquisto: cespite.data_acquisto,
      data_entrata_funzione: cespite.data_entrata_funzione || '',
    });
  };

  const handleSaveEdit = async () => {
    try {
      const originale = cespiti.find(c => c.id === editingCespite);
      const payload = {
        descrizione: editData.descrizione,
        fornitore: editData.fornitore,
        note: editData.note,
        data_entrata_funzione: editData.data_entrata_funzione,
      };
      if (!originale?.piano_ammortamento?.length) {
        payload.valore_acquisto = editData.valore_acquisto;
        payload.data_acquisto = editData.data_acquisto;
      }
      await api.put(`/api/cespiti/${editingCespite}`, payload);
      setEditingCespite(null);
      setEditData({});
      loadCespiti();
    } catch (e) {
      toast.error('Errore: ' + (e.response?.data?.detail || e.message));
    }
  };

  const handleCancelEdit = () => {
    setEditingCespite(null);
    setEditData({});
  };

  const handleDeleteCespite = async cespite => {
    const ok = await confirm({
      title: 'Archivia cespite',
      message: `Archiviare il cespite "${cespite.descrizione || cespite.nome || ''}"? Il record resterà nello storico di audit.`,
      variant: 'danger',
    });
    if (!ok) return;
    try {
      await api.delete(`/api/cespiti/${cespite.id}`);
      loadCespiti();
    } catch (e) {
      toast.error('Errore: ' + (e.response?.data?.detail || e.message));
    }
  };

  const fmt = v =>
    v != null
      ? new Intl.NumberFormat('it-IT', {
          style: 'currency',
          currency: 'EUR',
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        }).format(v)
      : '-';

  return (
    <PageLayout>
      {errorePagina && (
        <div role="alert" style={{ ...styles.urgentBox, color: '#991b1b' }}>
          <strong>Errore di caricamento:</strong> {errorePagina}
        </div>
      )}
      {/* handleTabChange (non setActiveTab): il cambio tab deve aggiornare
          anche l'URL (/cespiti/{tab}), altrimenti deep-link e tasto indietro
          non riflettono mai la tab attiva. */}
      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList style={{ height: 32 }}>
          <TabsTrigger value="cespiti" style={{ fontSize: 12, height: 28, padding: '0 12px' }}>
            <Building2 style={styles.icon} />
            Cespiti
          </TabsTrigger>
          <TabsTrigger value="tfr" style={{ fontSize: 12, height: 28, padding: '0 12px' }}>
            <Users style={styles.icon} />
            TFR
          </TabsTrigger>
          <TabsTrigger value="scadenzario" style={{ fontSize: 12, height: 28, padding: '0 12px' }}>
            <Calendar style={styles.icon} />
            Scadenzario
          </TabsTrigger>
        </TabsList>

        {/* CESPITI */}
        <TabsContent value="cespiti" style={{ marginTop: 8 }}>
          {verificaAmmortamenti && verificaAmmortamenti.stato !== 'coerente' && (
            <div role="alert" data-testid="verifica-ammortamenti" style={styles.urgentBox}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                <AlertTriangle style={{ ...styles.iconMd, color: '#b91c1c', flexShrink: 0 }} />
                <div style={{ fontSize: 12, color: '#7f1d1d' }}>
                  <strong>Verifica ammortamenti {anno}:</strong>{' '}
                  {verificaAmmortamenti.cespiti_ammortizzati}/{verificaAmmortamenti.cespiti_attivi}{' '}
                  cespiti con quota registrata.
                  {verificaAmmortamenti.entrata_funzione_da_verificare > 0 && (
                    <span>
                      {' '}
                      {verificaAmmortamenti.entrata_funzione_da_verificare} beni richiedono la
                      conferma della data di entrata in funzione.
                    </span>
                  )}
                  {verificaAmmortamenti.critiche?.length > 0 && (
                    <span> Differenza contabile: {fmt(verificaAmmortamenti.differenza)}.</span>
                  )}
                  {verificaAmmortamenti.coefficienti_oltre_massimo > 0 && (
                    <span>
                      {' '}
                      {verificaAmmortamenti.coefficienti_oltre_massimo} beni hanno un coefficiente
                      superiore al massimo fiscale; richiedono rettifica controllata.
                    </span>
                  )}
                  <div style={{ marginTop: 4, color: '#64748b' }}>
                    Controllo in sola lettura: nessuna scrittura viene generata aprendo la pagina.
                  </div>
                </div>
              </div>
            </div>
          )}
          {riepilogoCespiti && (
            <div style={{ ...styles.grid4, marginBottom: 12 }}>
              <div style={styles.statBox('#eff6ff')}>
                <p style={styles.statLabel('#2563eb')}>Cespiti</p>
                <p style={styles.statValue('#1e40af')}>{riepilogoCespiti?.totali?.num_cespiti}</p>
              </div>
              <div style={styles.statBox('#f0fdf4')}>
                <p style={styles.statLabel('#16a34a')}>Val. Acq.</p>
                <p style={styles.statValue('#166534')}>
                  {fmt(riepilogoCespiti.totali.valore_acquisto)}
                </p>
              </div>
              <div style={styles.statBox('#fffbeb')}>
                <p style={styles.statLabel('#d97706')}>Fondo</p>
                <p style={styles.statValue('#b45309')}>
                  {fmt(riepilogoCespiti.totali.fondo_ammortamento)}
                </p>
              </div>
              <div style={styles.statBox('#faf5ff')}>
                <p style={styles.statLabel()}>Netto</p>
                <p style={styles.statValue()}>
                  {fmt(riepilogoCespiti.totali.valore_netto_contabile)}
                </p>
              </div>
              <div style={styles.statBox('#fef2f2')}>
                <p style={styles.statLabel('#dc2626')}>Da verificare</p>
                <p style={styles.statValue('#b91c1c')}>
                  {riepilogoCespiti.totali.entrata_funzione_da_verificare || 0}
                </p>
              </div>
            </div>
          )}
          <div style={{ ...styles.row, marginBottom: 8 }}>
            <Button onClick={() => setShowForm(!showForm)} size="sm" style={styles.btn}>
              <Plus style={styles.icon} />
              Nuovo
            </Button>
            <Button onClick={handleCalcolaAmm} variant="outline" size="sm" style={styles.btn}>
              <Calculator style={styles.icon} />
              Verifica Ammort. {anno}
            </Button>
            <Button
              onClick={handleScanFatture}
              variant="outline"
              size="sm"
              style={styles.btn}
              data-testid="scan-fatture-btn"
            >
              Scan Fatture XML
            </Button>
          </div>
          <div style={{ ...styles.small, marginBottom: 8 }}>
            Coefficienti massimi: DM 31/12/1988, Gruppo XIX. L'ammortamento parte dall'entrata in
            funzione (art. 102 TUIR); software e diritti seguono l'art. 103. Le proposte da XML non
            vengono ammortizzate finché la data non è confermata.
          </div>
          {showForm && (
            <div style={styles.formCard}>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                  gap: 8,
                  marginBottom: 8,
                }}
              >
                <div>
                  <label style={styles.label}>Descrizione*</label>
                  <Input
                    value={nuovoCespite.descrizione}
                    onChange={e =>
                      setNuovoCespite({ ...nuovoCespite, descrizione: e.target.value })
                    }
                    style={styles.input}
                    placeholder="Es: Forno"
                  />
                </div>
                <div>
                  <label style={styles.label}>Categoria*</label>
                  <Select
                    value={nuovoCespite.categoria}
                    onValueChange={v => setNuovoCespite({ ...nuovoCespite, categoria: v })}
                  >
                    <SelectTrigger style={{ height: 28, fontSize: 12 }}>
                      <SelectValue placeholder="..." />
                    </SelectTrigger>
                    <SelectContent>
                      {categorie.map(c => (
                        <SelectItem key={c.codice} value={c.codice}>
                          {c.descrizione} ({c.coefficiente}%)
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <label style={styles.label}>Data Acq.*</label>
                  <Input
                    type="date"
                    value={nuovoCespite.data_acquisto}
                    onChange={e =>
                      setNuovoCespite({ ...nuovoCespite, data_acquisto: e.target.value })
                    }
                    style={styles.input}
                  />
                </div>
                <div>
                  <label style={styles.label}>Entrata in funzione*</label>
                  <Input
                    type="date"
                    value={nuovoCespite.data_entrata_funzione}
                    min={nuovoCespite.data_acquisto || undefined}
                    onChange={e =>
                      setNuovoCespite({ ...nuovoCespite, data_entrata_funzione: e.target.value })
                    }
                    style={styles.input}
                  />
                </div>
                <div>
                  <label style={styles.label}>Valore*</label>
                  <Input
                    type="number"
                    value={nuovoCespite.valore_acquisto}
                    onChange={e =>
                      setNuovoCespite({ ...nuovoCespite, valore_acquisto: e.target.value })
                    }
                    style={styles.input}
                    placeholder="0"
                  />
                </div>
              </div>
              <div style={styles.row}>
                <Button onClick={handleCreaCespite} size="sm" style={styles.btn}>
                  Salva
                </Button>
                <Button
                  onClick={() => setShowForm(false)}
                  variant="outline"
                  size="sm"
                  style={styles.btn}
                >
                  Annulla
                </Button>
              </div>
            </div>
          )}
          <div style={styles.card}>
            <div style={styles.cardContent}>
              {loading ? (
                <div style={{ textAlign: 'center', padding: 8, ...styles.small }}>
                  Caricamento...
                </div>
              ) : cespiti.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 8, ...styles.small }}>
                  Nessun cespite
                </div>
              ) : isMobile ? (
                <div data-testid="cespiti-mobile-cards" style={{ display: 'grid', gap: 8 }}>
                  {cespiti.map(c => (
                    <div
                      key={c.id}
                      style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 10 }}
                    >
                      {editingCespite === c.id ? (
                        <div style={{ display: 'grid', gap: 8 }}>
                          <Input
                            aria-label="Descrizione cespite"
                            value={editData.descrizione}
                            onChange={e =>
                              setEditData({ ...editData, descrizione: e.target.value })
                            }
                          />
                          <Input
                            aria-label="Data entrata in funzione"
                            type="date"
                            min={editData.data_acquisto || undefined}
                            value={editData.data_entrata_funzione}
                            onChange={e =>
                              setEditData({ ...editData, data_entrata_funzione: e.target.value })
                            }
                          />
                          <div style={styles.row}>
                            <Button size="sm" onClick={handleSaveEdit}>
                              Salva
                            </Button>
                            <Button size="sm" variant="outline" onClick={handleCancelEdit}>
                              Annulla
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <div style={{ fontWeight: 700 }}>{c.descrizione}</div>
                          <div style={{ ...styles.small, marginTop: 2 }}>{c.categoria}</div>
                          <div style={{ ...styles.grid2, marginTop: 8 }}>
                            <div>
                              <span style={styles.small}>Valore</span>
                              <br />
                              {fmt(c.valore_acquisto)}
                            </div>
                            <div>
                              <span style={styles.small}>Residuo</span>
                              <br />
                              {fmt(c.valore_residuo)}
                            </div>
                            <div>
                              <span style={styles.small}>Entrata funzione</span>
                              <br />
                              {c.data_entrata_funzione ? (
                                formatDateIT(c.data_entrata_funzione)
                              ) : (
                                <strong style={{ color: '#b91c1c' }}>Da verificare</strong>
                              )}
                            </div>
                            <div>
                              <span style={styles.small}>Max fiscale</span>
                              <br />
                              {c.coefficiente_ammortamento}%
                            </div>
                          </div>
                          <div style={{ ...styles.row, marginTop: 8 }}>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleEditCespite(c)}
                            >
                              <Pencil style={styles.icon} /> Modifica
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleDeleteCespite(c)}
                              disabled={c.piano_ammortamento?.length > 0}
                            >
                              Archivia
                            </Button>
                          </div>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table style={styles.table}>
                    <thead>
                      <tr>
                        <th style={styles.th}>Descrizione</th>
                        <th style={styles.th}>Categoria</th>
                        <th style={styles.th}>Entrata funzione</th>
                        <th style={styles.thCenter}>Max %</th>
                        <th style={styles.thRight}>Valore</th>
                        <th style={styles.thRight}>Fondo</th>
                        <th style={styles.thRight}>Residuo</th>
                        <th style={{ ...styles.thCenter, width: 80 }}>Azioni</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cespiti.map(c => (
                        <tr key={c.id}>
                          {editingCespite === c.id ? (
                            <>
                              <td style={styles.td}>
                                <Input
                                  value={editData.descrizione}
                                  onChange={e =>
                                    setEditData({ ...editData, descrizione: e.target.value })
                                  }
                                  style={{ height: 24, fontSize: 11 }}
                                />
                              </td>
                              <td style={{ ...styles.td, color: '#475569' }}>{c.categoria}</td>
                              <td style={styles.td}>
                                <Input
                                  type="date"
                                  value={editData.data_entrata_funzione}
                                  min={editData.data_acquisto || undefined}
                                  onChange={e =>
                                    setEditData({
                                      ...editData,
                                      data_entrata_funzione: e.target.value,
                                    })
                                  }
                                  style={{ height: 24, fontSize: 11, width: 132 }}
                                />
                              </td>
                              <td style={styles.tdCenter}>{c.coefficiente_ammortamento}%</td>
                              <td style={styles.tdRight}>
                                <Input
                                  type="number"
                                  value={editData.valore_acquisto}
                                  disabled={c.piano_ammortamento?.length > 0}
                                  onChange={e =>
                                    setEditData({
                                      ...editData,
                                      valore_acquisto: parseFloat(e.target.value),
                                    })
                                  }
                                  style={{
                                    height: 24,
                                    fontSize: 11,
                                    width: 80,
                                    textAlign: 'right',
                                  }}
                                />
                              </td>
                              <td style={{ ...styles.tdRight, color: '#d97706' }}>
                                {fmt(c.fondo_ammortamento)}
                              </td>
                              <td style={{ ...styles.tdRight, fontWeight: '600' }}>
                                {fmt(c.valore_residuo)}
                              </td>
                              <td style={styles.tdCenter}>
                                <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    style={{ height: 24, width: 24, padding: 0 }}
                                    onClick={handleSaveEdit}
                                  >
                                    <Check style={{ width: 12, height: 12, color: '#16a34a' }} />
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    style={{ height: 24, width: 24, padding: 0 }}
                                    onClick={handleCancelEdit}
                                  >
                                    <X style={{ width: 12, height: 12, color: '#64748b' }} />
                                  </Button>
                                </div>
                              </td>
                            </>
                          ) : (
                            <>
                              <td style={{ ...styles.td, fontWeight: '500' }}>{c.descrizione}</td>
                              <td style={{ ...styles.td, color: '#475569' }}>{c.categoria}</td>
                              <td style={styles.td}>
                                {c.data_entrata_funzione ? (
                                  formatDateIT(c.data_entrata_funzione)
                                ) : (
                                  <span style={{ color: '#b91c1c', fontWeight: 600 }}>
                                    Da verificare
                                  </span>
                                )}
                              </td>
                              <td style={styles.tdCenter}>{c.coefficiente_ammortamento}%</td>
                              <td style={styles.tdRight}>{fmt(c.valore_acquisto)}</td>
                              <td style={{ ...styles.tdRight, color: '#d97706' }}>
                                {fmt(c.fondo_ammortamento)}
                              </td>
                              <td style={{ ...styles.tdRight, fontWeight: '600' }}>
                                {fmt(c.valore_residuo)}
                              </td>
                              <td style={styles.tdCenter}>
                                <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    style={{ height: 24, width: 24, padding: 0 }}
                                    onClick={() => handleEditCespite(c)}
                                    title="Modifica"
                                  >
                                    <Pencil style={{ width: 12, height: 12, color: '#0f2744' }} />
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    style={{ height: 24, width: 24, padding: 0 }}
                                    onClick={() => handleDeleteCespite(c)}
                                    title="Archivia"
                                    disabled={c.piano_ammortamento?.length > 0}
                                  >
                                    <Trash2 style={{ width: 12, height: 12, color: '#dc2626' }} />
                                  </Button>
                                </div>
                              </td>
                            </>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </TabsContent>

        {/* TFR */}
        <TabsContent value="tfr" style={{ marginTop: 8 }}>
          {riepilogoTFR && (
            <>
              <div style={{ ...styles.grid3, marginBottom: 12 }}>
                <div style={styles.statBox('#eef2ff')}>
                  <p style={styles.statLabel()}>Fondo TFR</p>
                  <p style={styles.statValue()}>{fmt(riepilogoTFR.totale_fondo_tfr)}</p>
                </div>
                <div style={styles.statBox('#f0fdf4')}>
                  <p style={styles.statLabel('#16a34a')}>Accantonato {anno}</p>
                  <p style={styles.statValue('#166534')}>
                    {fmt(riepilogoTFR.accantonamenti_anno.totale_accantonato)}
                  </p>
                </div>
                <div style={styles.statBox('#fef2f2')}>
                  <p style={styles.statLabel('#dc2626')}>Liquidato {anno}</p>
                  <p style={styles.statValue('#b91c1c')}>
                    {fmt(riepilogoTFR.liquidazioni_anno.totale_netto)}
                  </p>
                </div>
              </div>
              <div style={styles.card}>
                <div style={{ padding: '4px 8px', borderBottom: '1px solid #f1f5f9' }}>
                  <span style={{ fontSize: 12, fontWeight: '600' }}>
                    Registro TFR per Dipendente
                  </span>
                  <span style={{ ...styles.small, marginLeft: 8 }}>
                    (clicca per il dettaglio mese per mese, estratto dai cedolini)
                  </span>
                </div>
                <div style={styles.cardContent}>
                  {riepilogoTFR?.dettaglio_dipendenti?.length === 0 ? (
                    <div style={{ ...styles.small, textAlign: 'center' }}>Nessun TFR</div>
                  ) : (
                    <div>
                      {riepilogoTFR.dettaglio_dipendenti.map((d, i) => (
                        <div key={i} style={{ marginBottom: 4 }}>
                          <div
                            onClick={() => toggleRegistroTFR(d.dipendente_id)}
                            data-testid={`tfr-riga-dipendente-${d.dipendente_id}`}
                            style={{
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                              padding: '6px 8px',
                              background: '#f8fafc',
                              borderRadius: 4,
                              fontSize: 12,
                              cursor: 'pointer',
                            }}
                          >
                            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                              {registroTFRAperto === d.dipendente_id ? (
                                <ChevronDown style={styles.icon} />
                              ) : (
                                <ChevronRight style={styles.icon} />
                              )}
                              {d.nome}
                            </span>
                            <span
                              style={{ fontWeight: 'bold', color: '#0f2744', fontFamily: MONO }}
                            >
                              {fmt(d.tfr_accantonato)}
                            </span>
                          </div>
                          {registroTFRAperto === d.dipendente_id && (
                            <div
                              style={{
                                padding: '6px 8px 6px 24px',
                                background: '#fff',
                                border: '1px solid #f1f5f9',
                                borderTop: 'none',
                                borderRadius: '0 0 4px 4px',
                              }}
                            >
                              {registroTFRLoading ? (
                                <div style={styles.small}>Caricamento...</div>
                              ) : !registroTFRDettaglio?.accantonamenti?.length ? (
                                <div style={styles.small}>
                                  Nessun accantonamento mensile registrato.
                                </div>
                              ) : (
                                <div style={{ overflowX: 'auto' }}>
                                  <table style={styles.table}>
                                    <thead>
                                      <tr>
                                        <th style={styles.th}>Periodo</th>
                                        <th style={styles.thRight}>Quota mese</th>
                                        <th style={styles.thRight}>Rivalutazione</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {registroTFRDettaglio.accantonamenti.map((a, j) => (
                                        <tr key={j}>
                                          <td style={styles.td}>{a.periodo}</td>
                                          <td style={styles.tdRight}>{fmt(a.quota_mese)}</td>
                                          <td style={styles.tdRight}>
                                            {fmt(a.rivalutazione || 0)}
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              )}
                              {registroTFRDettaglio?.totale_liquidato > 0 && (
                                <div style={{ ...styles.small, marginTop: 6 }}>
                                  Liquidato/anticipato: {fmt(registroTFRDettaglio.totale_liquidato)}{' '}
                                  — disponibile: {fmt(registroTFRDettaglio.tfr_disponibile)}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </TabsContent>

        {/* SCADENZARIO */}
        <TabsContent value="scadenzario" style={{ marginTop: 8 }}>
          {urgenti && urgenti.num_urgenti > 0 && (
            <div style={styles.urgentBox}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  color: '#b91c1c',
                  fontSize: 12,
                  fontWeight: '600',
                  marginBottom: 8,
                }}
              >
                <AlertTriangle style={styles.iconMd} />
                Urgenti: {urgenti.num_urgenti} fatture
              </div>
              <div style={styles.grid2}>
                <div
                  style={{ background: 'white', padding: 6, borderRadius: 4, textAlign: 'center' }}
                >
                  <p style={styles.statLabel('#dc2626')}>Scadute</p>
                  <p style={{ fontWeight: 'bold', color: '#b91c1c' }}>
                    {urgenti.num_scadute} | {fmt(urgenti.totale_scaduto)}
                  </p>
                </div>
                <div
                  style={{ background: 'white', padding: 6, borderRadius: 4, textAlign: 'center' }}
                >
                  <p style={styles.statLabel('#d97706')}>In Scadenza</p>
                  <p style={{ fontWeight: 'bold', color: '#b45309' }}>
                    {urgenti.num_urgenti - urgenti.num_scadute} |{' '}
                    {fmt(urgenti.totale_urgente - urgenti.totale_scaduto)}
                  </p>
                </div>
              </div>
            </div>
          )}
          {scadenzario && (
            <>
              <div style={{ ...styles.grid4, marginBottom: 12 }}>
                <div style={styles.statBox('#f8fafc')}>
                  <p style={styles.statLabel('#475569')}>Fatture</p>
                  <p style={styles.statValue('#1e293b')}>
                    {scadenzario?.riepilogo?.totale_fatture}
                  </p>
                </div>
                <div style={styles.statBox('#eff6ff')}>
                  <p style={styles.statLabel('#2563eb')}>Da Pagare</p>
                  <p style={styles.statValue('#1e40af')}>
                    {fmt(scadenzario.riepilogo.totale_da_pagare)}
                  </p>
                </div>
                <div style={styles.statBox('#fef2f2')}>
                  <p style={styles.statLabel('#dc2626')}>Scaduto</p>
                  <p style={styles.statValue('#b91c1c')}>
                    {fmt(scadenzario.riepilogo.totale_scaduto)}
                  </p>
                </div>
                <div style={styles.statBox('#fffbeb')}>
                  <p style={styles.statLabel('#d97706')}>7gg</p>
                  <p style={styles.statValue('#b45309')}>
                    {scadenzario?.riepilogo?.num_prossimi_7gg}
                  </p>
                </div>
              </div>
              <div style={styles.card}>
                <div style={{ padding: '4px 8px', borderBottom: '1px solid #f1f5f9' }}>
                  <span style={{ fontSize: 12, fontWeight: '600' }}>Top Fornitori</span>
                </div>
                <div style={styles.cardContent}>
                  <div>
                    {scadenzario.per_fornitore.slice(0, 8).map((f, i) => (
                      <div
                        key={i}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '6px 8px',
                          background: '#f8fafc',
                          borderRadius: 4,
                          marginBottom: 4,
                          fontSize: 12,
                        }}
                      >
                        <span
                          style={{
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            maxWidth: 200,
                          }}
                        >
                          {f.fornitore} <span style={{ color: '#94a3b8' }}>({f.num_fatture})</span>
                        </span>
                        <span style={{ fontWeight: 'bold', fontFamily: MONO }}>
                          {fmt(f.totale)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </>
          )}
        </TabsContent>
      </Tabs>
    </PageLayout>
  );
}
