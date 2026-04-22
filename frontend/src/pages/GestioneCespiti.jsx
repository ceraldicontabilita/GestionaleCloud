import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/card';
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
} from 'lucide-react';
import { STYLES, COLORS, button, badge, formatEuro, formatDateIT, useIsMobile } from '../lib/utils';

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
  grid2: { display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 8 },
  grid3: { display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)', gap: 8 },
  grid4: { display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)', gap: 8 },
  card: {
    background: 'white',
    borderRadius: 8,
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
    marginBottom: 12,
  },
  cardContent: { padding: 8 },
  input: { height: 28, fontSize: 12 },
  btn: { height: 28, fontSize: 12 },
  statBox: bg => ({ background: bg, padding: 8, borderRadius: 6, textAlign: 'center' }),
  statLabel: color => ({ fontSize: 11, color: color }),
  statValue: color => ({ fontSize: 18, fontWeight: 'bold', color: color }),
  table: { width: '100%', fontSize: 12, borderCollapse: 'collapse' },
  th: {
    padding: '4px 8px',
    textAlign: 'left',
    background: '#f8fafc',
    fontWeight: '600',
    color: '#475569',
  },
  thRight: {
    padding: '4px 8px',
    textAlign: 'right',
    background: '#f8fafc',
    fontWeight: '600',
    color: '#475569',
  },
  thCenter: {
    padding: '4px 8px',
    textAlign: 'center',
    background: '#f8fafc',
    fontWeight: '600',
    color: '#475569',
  },
  td: { padding: '4px 8px', borderBottom: '1px solid #f1f5f9' },
  tdRight: { padding: '4px 8px', borderBottom: '1px solid #f1f5f9', textAlign: 'right' },
  tdCenter: { padding: '4px 8px', borderBottom: '1px solid #f1f5f9', textAlign: 'center' },
  row: { display: 'flex', alignItems: 'center', gap: 8 },
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
    border: '1px solid #bfdbfe',
    borderRadius: 8,
    padding: 8,
    marginBottom: 12,
  },
};

export default function GestioneCespiti() {
  const isMobile = useIsMobile();
  const { anno } = useAnnoGlobale();
  // URL Tab Support
  const navigate = useNavigate();
  const location = useLocation();

  const getTabFromPath = () => {
    const path = location.pathname;
    const match = path.match(/\/cespiti\/([\w-]+)/);
    return match ? match[1] : 'cespiti';
  };

  const [activeTab, setActiveTab] = useState(getTabFromPath());

  const handleTabChange = tabId => {
    setActiveTab(tabId);
    navigate(`/cespiti/${tabId}`);
  };

  useEffect(() => {
    const tab = getTabFromPath();
    if (tab !== activeTab) setActiveTab(tab);
  }, [location.pathname]);
  const [loading, setLoading] = useState(false);
  const [cespiti, setCespiti] = useState([]);
  const [riepilogoCespiti, setRiepilogoCespiti] = useState(null);
  const [categorie, setCategorie] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [nuovoCespite, setNuovoCespite] = useState({
    descrizione: '',
    categoria: '',
    data_acquisto: '',
    valore_acquisto: '',
    fornitore: '',
  });
  const [riepilogoTFR, setRiepilogoTFR] = useState(null);
  const [scadenzario, setScadenzario] = useState(null);
  const [urgenti, setUrgenti] = useState(null);
  const [editingCespite, setEditingCespite] = useState(null);
  const [editData, setEditData] = useState({});

  useEffect(() => {
    if (activeTab === 'cespiti') {
      loadCespiti();
      loadCategorie();
    } else if (activeTab === 'tfr') {
      loadTFR();
    } else if (activeTab === 'scadenzario') {
      loadScadenzario();
    }
  }, [activeTab, anno]);

  const loadCespiti = async () => {
    try {
      setLoading(true);
      const [c, r] = await Promise.all([
        api.get('/api/cespiti/?attivi=true'),
        api.get('/api/cespiti/riepilogo'),
      ]);
      setCespiti(c.data);
      setRiepilogoCespiti(r.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };
  const loadCategorie = async () => {
    try {
      const r = await api.get('/api/cespiti/categorie');
      setCategorie(r.data.categorie);
    } catch (e) {
      console.error(e);
    }
  };
  const loadTFR = async () => {
    try {
      setLoading(true);
      const r = await api.get(`/api/tfr/riepilogo-aziendale?anno=${anno}`);
      setRiepilogoTFR(r.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };
  const loadScadenzario = async () => {
    try {
      setLoading(true);
      const [s, u] = await Promise.all([
        api.get(`/api/scadenzario-fornitori/?anno=${anno}`),
        api.get('/api/scadenzario-fornitori/urgenti'),
      ]);
      setScadenzario(s.data);
      setUrgenti(u.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreaCespite = async () => {
    if (!nuovoCespite.descrizione || !nuovoCespite.categoria || !nuovoCespite.valore_acquisto)
      return alert('Campi obbligatori');
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
        valore_acquisto: '',
        fornitore: '',
      });
      loadCespiti();
    } catch (e) {
      alert('Errore: ' + (e.response?.data?.detail || e.message));
    }
  };

  const handleCalcolaAmm = async () => {
    try {
      const r = await api.post(`/api/cespiti/registra/${anno}`);
      alert(r?.data?.messaggio);
      loadCespiti();
    } catch (e) {
      alert('Errore');
    }
  };

  const handleScanFatture = async () => {
    try {
      setLoading(true);
      const r = await api.post('/api/cespiti/scan-fatture?soglia_valore=200&dry_run=false');
      if (r.data.cespiti_creati > 0) {
        alert(
          `${r?.data?.messaggio}\nValore totale: EUR ${r?.data?.valore_totale?.toLocaleString('it-IT')}`
        );
      } else {
        alert('Nessun nuovo cespite trovato nelle fatture XML.');
      }
      loadCespiti();
    } catch (e) {
      alert('Errore scan: ' + (e.response?.data?.detail || e.message));
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
    });
  };

  const handleSaveEdit = async () => {
    try {
      await api.put(`/api/cespiti/${editingCespite}`, editData);
      setEditingCespite(null);
      setEditData({});
      loadCespiti();
    } catch (e) {
      alert('Errore: ' + (e.response?.data?.detail || e.message));
    }
  };

  const handleCancelEdit = () => {
    setEditingCespite(null);
    setEditData({});
  };

  const handleDeleteCespite = async cespite => {
    try {
      await api.delete(`/api/cespiti/${cespite.id}`);
      loadCespiti();
    } catch (e) {
      alert('Errore: ' + (e.response?.data?.detail || e.message));
    }
  };

  const fmt = v =>
    v != null
      ? new Intl.NumberFormat('it-IT', {
          style: 'currency',
          currency: 'EUR',
          maximumFractionDigits: 0,
        }).format(v)
      : '-';

  return (
    <PageLayout title="Cespiti & TFR" icon="🏢" subtitle={`Anno ${anno}`}>
      <Tabs value={activeTab} onValueChange={setActiveTab}>
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
                <p style={styles.statLabel('#9333ea')}>Netto</p>
                <p style={styles.statValue('#7c3aed')}>
                  {fmt(riepilogoCespiti.totali.valore_netto_contabile)}
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
              Ammort. {anno}
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
          {showForm && (
            <div style={styles.formCard}>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)',
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
              ) : (
                <table style={styles.table}>
                  <thead>
                    <tr>
                      <th style={styles.th}>Descrizione</th>
                      <th style={styles.th}>Categoria</th>
                      <th style={styles.thCenter}>%</th>
                      <th style={styles.thRight}>Valore</th>
                      <th style={styles.thRight}>Fondo</th>
                      <th style={styles.thRight}>Residuo</th>
                      <th style={{ ...styles.thCenter, width: 80 }}>Azioni</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cespiti.map((c, i) => (
                      <tr key={i}>
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
                            <td style={styles.tdCenter}>{c.coefficiente_ammortamento}%</td>
                            <td style={styles.tdRight}>
                              <Input
                                type="number"
                                value={editData.valore_acquisto}
                                onChange={e =>
                                  setEditData({
                                    ...editData,
                                    valore_acquisto: parseFloat(e.target.value),
                                  })
                                }
                                style={{ height: 24, fontSize: 11, width: 80, textAlign: 'right' }}
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
                                  <Pencil style={{ width: 12, height: 12, color: '#2563eb' }} />
                                </Button>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  style={{ height: 24, width: 24, padding: 0 }}
                                  onClick={() => handleDeleteCespite(c)}
                                  title="Elimina"
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
                  <p style={styles.statLabel('#4f46e5')}>Fondo TFR</p>
                  <p style={styles.statValue('#4338ca')}>{fmt(riepilogoTFR.totale_fondo_tfr)}</p>
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
                  <span style={{ fontSize: 12, fontWeight: '600' }}>TFR per Dipendente</span>
                </div>
                <div style={styles.cardContent}>
                  {riepilogoTFR?.dettaglio_dipendenti?.length === 0 ? (
                    <div style={{ ...styles.small, textAlign: 'center' }}>Nessun TFR</div>
                  ) : (
                    <div>
                      {riepilogoTFR.dettaglio_dipendenti.map((d, i) => (
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
                          <span>{d.nome}</span>
                          <span style={{ fontWeight: 'bold', color: '#4f46e5' }}>
                            {fmt(d.tfr_accantonato)}
                          </span>
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
                  <p style={{ fontSize: 18, fontWeight: 'bold' }}>
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
                        <span style={{ fontWeight: 'bold' }}>{fmt(f.totale)}</span>
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
