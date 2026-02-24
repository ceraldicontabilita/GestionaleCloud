import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, formatDateIT, STYLES, COLORS, button, badge } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { ExportButton } from '../components/ExportButton';
import { TurniSection } from '../components/attendance/TurniSection';
import { TabSaldoFerie } from '../components/attendance/TabSaldoFerie';
import { STATI_PRESENZA, MESI } from '../components/attendance/constants';
import { toast } from 'sonner';
import { Wallet, RefreshCw, CheckCircle, Clock, AlertCircle, FileText, Users, Car } from 'lucide-react';

/**
 * GESTIONE DIPENDENTI UNIFICATA
 * 
 * Una sola pagina con tab per:
 * - Anagrafica
 * - Contratti
 * - Retribuzione & Cedolini
 * - Bonifici
 * - Acconti
 * 
 * URL con tab: /dipendenti/anagrafica, /dipendenti/contratti, etc.
 */

const TABS = [
  { id: 'anagrafica', label: 'Anagrafica', icon: '👤' },
  { id: 'giustificativi', label: 'Giustificativi', icon: '📋' },
  { id: 'contratti', label: 'Contratti', icon: '📄' },
  { id: 'retribuzione', label: 'Retribuzione', icon: '📋' },
  { id: 'bonifici', label: 'Bonifici', icon: '🏦' },
  { id: 'acconti', label: 'Acconti', icon: '📋' },
  { id: 'presenze-batch', label: 'Presenze', icon: '📅', global: true },
  { id: 'turni', label: 'Gestione Turni', icon: '👥', global: true },
  { id: 'richieste', label: 'Richieste', icon: '📋', global: true, badge: true },
  { id: 'storico-ore', label: 'Storico Ore', icon: '⏱️', global: true },
  { id: 'saldo-ferie', label: 'Saldo Ferie', icon: '📅', global: true },
  { id: 'paghe', label: 'Paghe', icon: '📋', global: true },
  { id: 'veicoli', label: 'Veicoli', icon: '🚗', global: true },
];

export default function GestioneDipendentiUnificata() {
  const { anno } = useAnnoGlobale();
  const navigate = useNavigate();
  const location = useLocation();
  
  // Ottieni tab e subtab dall'URL
  const getTabFromPath = () => {
    const path = location.pathname;
    const match = path.match(/\/dipendenti\/(\w+)/);
    if (match && TABS.find(t => t.id === match[1])) {
      return match[1];
    }
    return 'anagrafica';
  };
  
  const getSubtabFromPath = () => {
    const path = location.pathname;
    const match = path.match(/\/dipendenti\/giustificativi\/(\w+)/);
    return match ? match[1] : 'tutti';
  };
  
  const [dipendenti, setDipendenti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedDip, setSelectedDip] = useState(null);
  const [activeTab, setActiveTab] = useState(getTabFromPath());
  const [activeSubtab, setActiveSubtab] = useState(getSubtabFromPath());
  const [search, setSearch] = useState('');
  
  // Aggiorna URL quando cambia tab
  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    if (tabId === 'anagrafica') {
      navigate('/dipendenti');
    } else if (tabId === 'giustificativi') {
      navigate(`/dipendenti/giustificativi/${activeSubtab}`);
    } else {
      navigate(`/dipendenti/${tabId}`);
    }
  };
  
  // Aggiorna URL quando cambia subtab (categoria giustificativi)
  const handleSubtabChange = (subtabId) => {
    setActiveSubtab(subtabId);
    navigate(`/dipendenti/giustificativi/${subtabId}`);
  };
  
  // Sincronizza tab con URL
  useEffect(() => {
    const tab = getTabFromPath();
    const subtab = getSubtabFromPath();
    if (tab !== activeTab) {
      setActiveTab(tab);
    }
    if (subtab !== activeSubtab) {
      setActiveSubtab(subtab);
    }
  }, [location.pathname]);
  
  // Stati per ogni tab
  const [editMode, setEditMode] = useState(false);
  const [saving, setSaving] = useState(false);
  const [contratti, setContratti] = useState([]);
  const [cedolini, setCedolini] = useState([]);
  const [bonifici, setBonifici] = useState([]);
  const [acconti, setAcconti] = useState([]);
  const [loadingTab, setLoadingTab] = useState(false);

  // Nuovi tab globali
  const [richiestePending, setRichiestePending] = useState([]);
  const [allEmployees, setAllEmployees] = useState([]);
  const [currentDate, setCurrentDate] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));

  // Form anagrafica
  const [formData, setFormData] = useState({});

  // Carica lista dipendenti
  useEffect(() => {
    loadDipendenti();
  }, []);

  // Carica dati tab quando cambia dipendente o tab
  useEffect(() => {
    if (selectedDip) {
      loadTabData();
    }
  }, [selectedDip, activeTab, anno]);

  const loadDipendenti = async () => {
    try {
      const res = await api.get('/api/dipendenti');
      setDipendenti(res.data || []);
    } catch (e) {
      console.error('Errore:', e);
    } finally {
      setLoading(false);
    }
    // Carica anche richieste pending e tutti i dipendenti per tab globali
    try {
      const [pendingRes, empRes] = await Promise.all([
        api.get('/api/attendance/richieste-pending'),
        api.get('/api/employees?limit=200')
      ]);
      setRichiestePending(pendingRes.data?.richieste || []);
      const emps = (empRes.data?.employees || empRes.data || [])
        .filter(e => (e.status === 'attivo' || !e.status) && (e.in_carico !== false))
        .map(e => ({ ...e, nome_completo: e.nome_completo || e.name || `${e.nome || ''} ${e.cognome || ''}`.trim() }));
      setAllEmployees(emps);
    } catch (e) {
      // ignora errori tab globali
    }
  };

  const loadTabData = async () => {
    if (!selectedDip) return;
    console.log('loadTabData chiamato, tab:', activeTab, 'dip:', selectedDip?.id);
    setLoadingTab(true);
    
    try {
      switch (activeTab) {
        case 'anagrafica':
          setFormData({
            nome: selectedDip.nome || '',
            cognome: selectedDip.cognome || '',
            nome_completo: selectedDip.nome_completo || '',
            codice_fiscale: selectedDip.codice_fiscale || '',
            data_nascita: selectedDip.data_nascita || '',
            luogo_nascita: selectedDip.luogo_nascita || '',
            indirizzo: selectedDip.indirizzo || '',
            telefono: selectedDip.telefono || '',
            email: selectedDip.email || '',
            mansione: selectedDip.mansione || selectedDip.qualifica || '',
            data_assunzione: selectedDip.data_assunzione || '',
            ibans: selectedDip.ibans || [],
          });
          break;
          
        case 'contratti':
          const contRes = await api.get(`/api/dipendenti/contratti?dipendente_id=${selectedDip.id}`);
          setContratti(contRes.data || []);
          break;
          
        case 'retribuzione':
          const cedRes = await api.get(`/api/cedolini/dipendente/${selectedDip.id}?anno=${anno}`);
          setCedolini(Array.isArray(cedRes.data) ? cedRes.data : cedRes.data?.cedolini || []);
          break;
          
        case 'bonifici':
          // Cerca bonifici per nome dipendente (beneficiario)
          const nomeDip = selectedDip.nome_completo || `${selectedDip.cognome || ''} ${selectedDip.nome || ''}`.trim();
          const bonRes = await api.get(`/api/archivio-bonifici/transfers?beneficiario=${encodeURIComponent(nomeDip)}`);
          setBonifici(Array.isArray(bonRes.data) ? bonRes.data : []);
          break;
          
        case 'acconti':
          const accRes = await api.get(`/api/tfr/acconti/${selectedDip.id}`);
          setAcconti(Array.isArray(accRes.data) ? accRes.data : accRes.data?.acconti || []);
          break;
          
        case 'giustificativi':
          // I giustificativi vengono caricati dal componente TabGiustificativi stesso
          // Non serve caricare nulla qui
          console.log('Case giustificativi - nessuna azione');
          break;
      }
    } catch (e) {
      console.error('Errore caricamento tab:', e);
    } finally {
      console.log('Setting loadingTab = false');
      setLoadingTab(false);
    }
  };

  const handleSelectDipendente = (dip) => {
    setSelectedDip(dip);
    setEditMode(false);
  };

  const handleSaveAnagrafica = async () => {
    setSaving(true);
    try {
      await api.put(`/api/dipendenti/${selectedDip.id}`, formData);
      await loadDipendenti();
      setSelectedDip(prev => ({ ...prev, ...formData }));
      setEditMode(false);
    } catch (e) {
      alert('Errore: ' + (e.response?.data?.detail || e.message));
    } finally {
      setSaving(false);
    }
  };

  // Filtra dipendenti
  const filteredDip = dipendenti.filter(d => {
    const nome = (d.nome_completo || `${d.cognome} ${d.nome}` || '').toLowerCase();
    return nome.includes(search.toLowerCase());
  });

  return (
    <PageLayout title="Gestione Dipendenti" subtitle="Anagrafica, contratti, retribuzioni, bonifici e acconti">
    <div style={{ display: 'flex', flexDirection: 'column', position: 'relative' }}>
      {/* Page Info Card */}      
      {/* Header con Export */}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
        <ExportButton
          data={filteredDip}
          columns={[
            { key: 'nome_completo', label: 'Nome' },
            { key: 'codice_fiscale', label: 'Codice Fiscale' },
            { key: 'data_assunzione', label: 'Data Assunzione' },
            { key: 'qualifica', label: 'Qualifica' },
            { key: 'livello', label: 'Livello' },
            { key: 'status', label: 'Stato' }
          ]}
          filename="dipendenti"
          format="csv"
        />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: TABS.find(t => t.id === activeTab)?.global ? '1fr' : '280px 1fr', gap: 16, flex: 1, minHeight: 0 }}>
        {/* SIDEBAR - Lista Dipendenti (nascosta sui tab globali) */}
        {!TABS.find(t => t.id === activeTab)?.global && (
        <div style={{ 
          background: 'white', 
          borderRadius: 12, 
          boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden'
        }}>
          {/* Ricerca */}
          <div style={{ padding: 12, borderBottom: '1px solid #e5e7eb' }}>
            <input
              type="text"
              placeholder="🔍 Cerca dipendente..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                width: '100%',
                padding: '10px 12px',
                border: '1px solid #e5e7eb',
                borderRadius: 8,
                fontSize: 13
              }}
            />
          </div>
          
          {/* Lista */}
          <div style={{ flex: 1, overflow: 'auto', padding: '8px 12px' }}>
            {loading ? (
              <div style={{ textAlign: 'center', padding: 20, color: '#94a3b8' }}>Caricamento...</div>
            ) : filteredDip.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 20, color: '#94a3b8' }}>Nessun dipendente</div>
            ) : (
              filteredDip.map(dip => (
                <div
                  key={dip.id}
                  onClick={() => handleSelectDipendente(dip)}
                  style={{
                    padding: '12px',
                    marginBottom: 6,
                    borderRadius: 8,
                    cursor: 'pointer',
                    background: selectedDip?.id === dip.id ? '#dbeafe' : '#f8fafc',
                    border: selectedDip?.id === dip.id ? '2px solid #3b82f6' : '1px solid transparent',
                    transition: 'all 0.15s'
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: 14, color: '#1e293b' }}>
                    {dip.nome_completo || `${dip.cognome || ''} ${dip.nome || ''}`.trim() || 'N/A'}
                  </div>
                  <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>
                    {dip.mansione || dip.qualifica || 'Mansione N/D'}
                  </div>
                  <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 2 }}>
                    CF: {dip.codice_fiscale?.substring(0, 10) || 'N/D'}...
                  </div>
                </div>
              ))
            )}
          </div>
          
          {/* Conteggio */}
          <div style={{ padding: '10px 12px', borderTop: '1px solid #e5e7eb', fontSize: 12, color: '#64748b', textAlign: 'center' }}>
            {filteredDip.length} dipendenti
          </div>
        </div>
        )} {/* fine sidebar condizionale */}

        {/* MAIN - Dettaglio con Tab */}
        <div style={{ 
          background: 'white', 
          borderRadius: 12, 
          boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden'
        }}>
          {/* Tab bar sempre visibile */}
          <div style={{ borderBottom: '1px solid #e5e7eb' }}>
            {/* Header dipendente (solo se selezionato e tab non-globale) */}
            {selectedDip && !TABS.find(t => t.id === activeTab)?.global && (
              <div style={{ padding: '16px 20px', background: '#f8fafc' }}>
                <div style={{ fontWeight: 700, fontSize: 18, color: '#1e293b' }}>
                  {selectedDip.nome_completo || `${selectedDip.cognome || ''} ${selectedDip.nome || ''}`.trim()}
                </div>
                <div style={{ fontSize: 13, color: '#64748b', marginTop: 4 }}>
                  {selectedDip.mansione || selectedDip.qualifica || 'N/D'} • CF: {selectedDip.codice_fiscale || 'N/D'}
                </div>
              </div>
            )}
            {!selectedDip && !TABS.find(t => t.id === activeTab)?.global && (
              <div style={{ padding: '12px 20px', background: '#fef9c3', fontSize: 13, color: '#92400e', display: 'flex', alignItems: 'center', gap: 8 }}>
                <span>👈</span> Seleziona un dipendente dalla lista per vedere anagrafica, contratti, cedolini...
              </div>
            )}
            
            {/* Tab bar — due righe, niente scrollbar */}
            <div style={{ background: 'white', borderBottom: '1px solid #e5e7eb' }}>
              {/* Riga 1: tab dipendente */}
              <div style={{ display: 'flex', padding: '0 12px', gap: 0, borderBottom: '1px solid #f1f5f9' }}>
                {TABS.filter(t => !t.global).map(tab => (
                  <button
                    key={tab.id}
                    onClick={() => handleTabChange(tab.id)}
                    style={{
                      padding: '9px 12px',
                      background: 'none',
                      border: 'none',
                      borderBottom: activeTab === tab.id ? '3px solid #3b82f6' : '3px solid transparent',
                      color: activeTab === tab.id ? '#3b82f6' : '#64748b',
                      fontWeight: activeTab === tab.id ? 600 : 400,
                      cursor: 'pointer',
                      fontSize: 11.5,
                      whiteSpace: 'nowrap',
                      transition: 'all 0.15s',
                      marginBottom: -1
                    }}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
              {/* Riga 2: tab globali */}
              <div style={{ display: 'flex', padding: '0 12px', gap: 0, background: '#fafbfc' }}>
                {TABS.filter(t => t.global).map(tab => (
                  <button
                    key={tab.id}
                    onClick={() => handleTabChange(tab.id)}
                    style={{
                      padding: '8px 12px',
                      background: activeTab === tab.id ? '#1e3a5f' : 'none',
                      border: 'none',
                      borderRadius: activeTab === tab.id ? '6px 6px 0 0' : 0,
                      color: activeTab === tab.id ? 'white' : '#64748b',
                      fontWeight: activeTab === tab.id ? 600 : 400,
                      cursor: 'pointer',
                      fontSize: 11.5,
                      whiteSpace: 'nowrap',
                      transition: 'all 0.15s',
                    }}
                  >
                    {tab.id === 'richieste' ? `📋 Richieste (${richiestePending.length})` : tab.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Contenuto Tab */}
          <div style={{ flex: 1, overflow: 'auto', padding: 20 }}>
            {/* Tab globali - non richiedono dipendente selezionato */}
            {activeTab === 'presenze-batch' && (
              <TabPresenzeBatch 
                dipendenti={dipendenti}
                allEmployees={allEmployees}
                currentDate={currentDate}
                setCurrentDate={setCurrentDate}
              />
            )}
            {activeTab === 'turni' && (
              <TurniSection 
                employees={allEmployees}
                currentMonth={currentDate.getMonth()}
                currentYear={currentDate.getFullYear()}
              />
            )}
            {activeTab === 'richieste' && (
              <TabRichieste 
                richieste={richiestePending}
                onRefresh={loadDipendenti}
              />
            )}
            {activeTab === 'storico-ore' && (
              <TabStoricoOre 
                employees={allEmployees}
                currentDate={currentDate}
                setCurrentDate={setCurrentDate}
              />
            )}
            {activeTab === 'saldo-ferie' && (
              <TabSaldoFerie 
                employees={allEmployees}
                currentYear={currentDate.getFullYear()}
              />
            )}
            {activeTab === 'paghe' && (
              <TabPaghe anno={anno} />
            )}
            {activeTab === 'veicoli' && (
              <TabVeicoli />
            )}

            {/* Tab per dipendente */}
            {!TABS.find(t => t.id === activeTab)?.global && (
              <>
                {!selectedDip ? (
                  <div style={{ textAlign: 'center', padding: 60, color: '#94a3b8' }}>
                    <div style={{ fontSize: 48, marginBottom: 12 }}>👈</div>
                    <div>Seleziona un dipendente dalla lista</div>
                  </div>
                ) : loadingTab ? (
                  <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>
                    <div style={{ fontSize: 32 }}>⏳</div>
                    <div>Caricamento...</div>
                  </div>
                ) : (
                  <>
                    {activeTab === 'anagrafica' && (
                      <TabAnagrafica 
                        formData={formData} 
                        setFormData={setFormData}
                        editMode={editMode}
                        setEditMode={setEditMode}
                        onSave={handleSaveAnagrafica}
                        saving={saving}
                      />
                    )}
                    {activeTab === 'giustificativi' && (
                      <TabGiustificativi 
                        dipendente={selectedDip}
                        anno={anno}
                        selectedCategoria={activeSubtab}
                        onCategoriaChange={handleSubtabChange}
                      />
                    )}
                    {activeTab === 'contratti' && (
                      <TabContratti 
                        contratti={contratti}
                        dipendente={selectedDip}
                        onReload={loadTabData}
                      />
                    )}
                    {activeTab === 'retribuzione' && (
                      <TabRetribuzione 
                        cedolini={cedolini}
                        dipendente={selectedDip}
                        anno={anno}
                      />
                    )}
                    {activeTab === 'bonifici' && (
                      <TabBonifici 
                        bonifici={bonifici}
                        dipendente={selectedDip}
                        onReload={loadTabData}
                      />
                    )}
                    {activeTab === 'acconti' && (
                      <TabAcconti 
                        acconti={acconti}
                        dipendente={selectedDip}
                        onReload={loadTabData}
                      />
                    )}
                  </>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
    </PageLayout>
  );
}

// ============================================
// TAB COMPONENTS
// ============================================

function TabAnagrafica({ formData, setFormData, editMode, setEditMode, onSave, saving }) {
  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleAddIban = () => {
    const newIban = prompt('Inserisci nuovo IBAN:');
    if (newIban && newIban.trim()) {
      setFormData(prev => ({
        ...prev,
        ibans: [...(prev.ibans || []), newIban.trim().toUpperCase()]
      }));
    }
  };

  const handleRemoveIban = (idx) => {
    setFormData(prev => ({
      ...prev,
      ibans: prev.ibans.filter((_, i) => i !== idx)
    }));
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h3 style={{ margin: 0, fontSize: 16, color: '#374151' }}>Dati Anagrafici</h3>
        {!editMode ? (
          <button onClick={() => setEditMode(true)} style={btnStyle('#3b82f6')}>✏️ Modifica</button>
        ) : (
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => setEditMode(false)} style={btnStyle('#94a3b8')}>Annulla</button>
            <button onClick={onSave} disabled={saving} style={btnStyle('#10b981')}>
              {saving ? '⏳' : '💾'} Salva
            </button>
          </div>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
        <Field label="Nome" value={formData.nome} onChange={v => handleChange('nome', v)} disabled={!editMode} />
        <Field label="Cognome" value={formData.cognome} onChange={v => handleChange('cognome', v)} disabled={!editMode} />
        <Field label="Nome Completo" value={formData.nome_completo} onChange={v => handleChange('nome_completo', v)} disabled={!editMode} />
        <Field label="Codice Fiscale" value={formData.codice_fiscale} onChange={v => handleChange('codice_fiscale', v)} disabled={!editMode} />
        <Field label="Data Nascita" value={formData.data_nascita} onChange={v => handleChange('data_nascita', v)} disabled={!editMode} type="date" />
        <Field label="Luogo Nascita" value={formData.luogo_nascita} onChange={v => handleChange('luogo_nascita', v)} disabled={!editMode} />
        <Field label="Indirizzo" value={formData.indirizzo} onChange={v => handleChange('indirizzo', v)} disabled={!editMode} />
        <Field label="Telefono" value={formData.telefono} onChange={v => handleChange('telefono', v)} disabled={!editMode} />
        <Field label="Email" value={formData.email} onChange={v => handleChange('email', v)} disabled={!editMode} type="email" />
        <Field label="Mansione" value={formData.mansione} onChange={v => handleChange('mansione', v)} disabled={!editMode} />
        <Field label="Data Assunzione" value={formData.data_assunzione} onChange={v => handleChange('data_assunzione', v)} disabled={!editMode} type="date" />
      </div>

      {/* Flag In Carico - per modulo presenze */}
      <div style={{ marginTop: 20, padding: 16, background: '#f0f9ff', borderRadius: 10, border: '1px solid #bae6fd' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 14, color: '#0369a1', marginBottom: 4 }}>📋 Gestione Presenze</div>
            <p style={{ margin: 0, fontSize: 12, color: '#64748b' }}>
              Se attivo, il dipendente comparirà nel modulo presenze e nel calendario timbrature
            </p>
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: editMode ? 'pointer' : 'default' }}>
            <input 
              type="checkbox" 
              checked={formData.in_carico !== false}
              onChange={(e) => handleChange('in_carico', e.target.checked)}
              disabled={!editMode}
              style={{ width: 20, height: 20, cursor: editMode ? 'pointer' : 'default' }}
              data-testid="in-carico-toggle"
            />
            <span style={{ 
              fontSize: 14, 
              fontWeight: 600, 
              padding: '6px 12px',
              borderRadius: 6,
              background: formData.in_carico !== false ? '#dcfce7' : '#fee2e2',
              color: formData.in_carico !== false ? '#166534' : '#dc2626'
            }}>
              {formData.in_carico !== false ? '✓ In Carico' : '✗ Non in Carico'}
            </span>
          </label>
        </div>
      </div>

      {/* IBAN multipli */}
      <div style={{ marginTop: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h4 style={{ margin: 0, fontSize: 14, color: '#374151' }}>🏦 IBAN</h4>
          {editMode && (
            <button onClick={handleAddIban} style={btnStyle('#3b82f6', 'small')}>+ Aggiungi IBAN</button>
          )}
        </div>
        {(!formData.ibans || formData.ibans.length === 0) ? (
          <div style={{ padding: 16, background: '#f8fafc', borderRadius: 8, color: '#94a3b8', textAlign: 'center' }}>
            Nessun IBAN registrato
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {formData.ibans.map((iban, idx) => (
              <div key={idx} style={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: 8, 
                padding: '10px 14px', 
                background: '#f8fafc', 
                borderRadius: 8,
                border: '1px solid #e5e7eb'
              }}>
                <span style={{ fontFamily: 'monospace', flex: 1 }}>{iban}</span>
                {editMode && (
                  <button onClick={() => handleRemoveIban(idx)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444' }}>✕</button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function TabContratti({ contratti, dipendente, onReload }) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h3 style={{ margin: 0, fontSize: 16, color: '#374151' }}>Contratti</h3>
      </div>
      
      {contratti.length === 0 ? (
        <EmptyState icon="📋" text="Nessun contratto registrato" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {contratti.map((c, idx) => (
            <div key={idx} style={{ padding: 16, background: '#f8fafc', borderRadius: 8, border: '1px solid #e5e7eb' }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>{c.tipo_contratto || 'Contratto'}</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, fontSize: 13 }}>
                <div><span style={{ color: '#64748b' }}>Inizio:</span> {c.data_inizio || 'N/D'}</div>
                <div><span style={{ color: '#64748b' }}>Fine:</span> {c.data_fine || 'Indeterminato'}</div>
                <div><span style={{ color: '#64748b' }}>Livello:</span> {c.livello || 'N/D'}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TabRetribuzione({ cedolini, dipendente, anno }) {
  const totaleNetto = cedolini.reduce((sum, c) => sum + (c.netto || c.netto_in_busta || 0), 0);
  const totaleLordo = cedolini.reduce((sum, c) => sum + (c.lordo || c.lordo_totale || 0), 0);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h3 style={{ margin: 0, fontSize: 16, color: '#374151' }}>Cedolini {anno}</h3>
      </div>

      {/* Riepilogo */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 20 }}>
        <StatBox label="Cedolini" value={cedolini.length} color="#3b82f6" />
        <StatBox label="Totale Lordo" value={formatEuro(totaleLordo)} color="#f59e0b" />
        <StatBox label="Totale Netto" value={formatEuro(totaleNetto)} color="#10b981" />
      </div>
      
      {cedolini.length === 0 ? (
        <EmptyState icon="📄" text={`Nessun cedolino per ${anno}`} />
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#f8fafc' }}>
              <th style={thStyle}>Mese</th>
              <th style={thStyle}>Ore</th>
              <th style={{ ...thStyle, textAlign: 'right' }}>Lordo</th>
              <th style={{ ...thStyle, textAlign: 'right' }}>Netto</th>
              <th style={{ ...thStyle, textAlign: 'center' }}>Allegato</th>
              <th style={{ ...thStyle, textAlign: 'center' }}>Stato</th>
            </tr>
          </thead>
          <tbody>
            {cedolini.map((c, idx) => (
              <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                <td style={tdStyle}>{getMeseName(c.mese)}</td>
                <td style={tdStyle}>{c.ore_lavorate || '-'}</td>
                <td style={{ ...tdStyle, textAlign: 'right' }}>{formatEuro(c.lordo || c.lordo_totale || 0)}</td>
                <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 600, color: '#10b981' }}>{formatEuro(c.netto || c.netto_in_busta || 0)}</td>
                <td style={{ ...tdStyle, textAlign: 'center' }}>
                  {c.pdf_data ? (
                    <a
                      href={`${import.meta.env.VITE_BACKEND_URL || ''}/api/cedolini/${c.id}/download`}
                      target="_blank"
                      rel="noreferrer"
                      style={{ color: '#3b82f6', textDecoration: 'none', fontWeight: 600 }}
                    >
                      📎 PDF
                    </a>
                  ) : '-'}
                </td>
                <td style={{ ...tdStyle, textAlign: 'center' }}>
                  {c.pagato ? <span style={{ color: '#10b981' }}>✓ Pagato</span> : <span style={{ color: '#f59e0b' }}>⏳</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function TabBonifici({ bonifici, dipendente, onReload }) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h3 style={{ margin: 0, fontSize: 16, color: '#374151' }}>Bonifici Effettuati</h3>
      </div>
      
      {bonifici.length === 0 ? (
        <EmptyState icon="🏦" text="Nessun bonifico registrato" />
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#f8fafc' }}>
              <th style={thStyle}>Data</th>
              <th style={thStyle}>Descrizione</th>
              <th style={{ ...thStyle, textAlign: 'right' }}>Importo</th>
              <th style={thStyle}>IBAN</th>
            </tr>
          </thead>
          <tbody>
            {bonifici.map((b, idx) => (
              <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                <td style={tdStyle}>{b.data ? formatDateIT(b.data) : '-'}</td>
                <td style={tdStyle}>{b.descrizione || b.causale || '-'}</td>
                <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 600 }}>{formatEuro(b.importo || 0)}</td>
                <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 11 }}>{b.iban?.substring(0, 20) || '-'}...</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function TabAcconti({ acconti: accontiData, dipendente, onReload }) {
  const [showForm, setShowForm] = useState(false);
  const [editingAcconto, setEditingAcconto] = useState(null);
  const [newAcconto, setNewAcconto] = useState({ importo: '', data: '', note: '', tipo: 'tfr' });
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(null);

  // Gestisce sia array che oggetto strutturato
  const accontiObj = accontiData && typeof accontiData === 'object' && !Array.isArray(accontiData) 
    ? accontiData 
    : { tfr_accantonato: 0, tfr_acconti: 0, tfr_saldo: 0, totale_acconti: 0, acconti: { tfr: [], ferie: [], tredicesima: [], quattordicesima: [], prestito: [] } };
  
  // Flatten tutti gli acconti in un array
  const allAcconti = accontiObj.acconti 
    ? [...(accontiObj.acconti.tfr || []), ...(accontiObj.acconti.ferie || []), ...(accontiObj.acconti.tredicesima || []), ...(accontiObj.acconti.quattordicesima || []), ...(accontiObj.acconti.prestito || [])]
    : (Array.isArray(accontiData) ? accontiData : []);

  const handleAddAcconto = async () => {
    if (!newAcconto.importo) return alert('Inserisci importo');
    setSaving(true);
    try {
      await api.post(`/api/tfr/acconti`, {
        dipendente_id: dipendente.id,
        tipo: newAcconto.tipo,
        importo: parseFloat(newAcconto.importo),
        data: newAcconto.data || new Date().toISOString().split('T')[0],
        note: newAcconto.note
      });
      setShowForm(false);
      setNewAcconto({ importo: '', data: '', note: '', tipo: 'tfr' });
      onReload();
    } catch (e) {
      alert('Errore: ' + (e.response?.data?.detail || e.message));
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateAcconto = async () => {
    if (!editingAcconto || !editingAcconto.importo) return alert('Inserisci importo');
    setSaving(true);
    try {
      await api.put(`/api/tfr/acconti/${editingAcconto.id}`, {
        tipo: editingAcconto.tipo,
        importo: parseFloat(editingAcconto.importo),
        data: editingAcconto.data,
        note: editingAcconto.note
      });
      setEditingAcconto(null);
      onReload();
    } catch (e) {
      alert('Errore: ' + (e.response?.data?.detail || e.message));
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteAcconto = async (accontoId) => {
    if (!confirm('Sei sicuro di voler eliminare questo acconto?')) return;
    setDeleting(accontoId);
    try {
      await api.delete(`/api/tfr/acconti/${accontoId}`);
      onReload();
    } catch (e) {
      alert('Errore eliminazione: ' + (e.response?.data?.detail || e.message));
    } finally {
      setDeleting(null);
    }
  };

  const totaleAcconti = accontiObj.totale_acconti || 0;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h3 style={{ margin: 0, fontSize: 16, color: '#374151' }}>Acconti</h3>
        <button onClick={() => setShowForm(!showForm)} style={btnStyle('#3b82f6')}>
          {showForm ? 'Annulla' : '+ Nuovo Acconto'}
        </button>
      </div>

      {/* Form nuovo acconto */}
      {showForm && (
        <div style={{ padding: 16, background: '#f0f9ff', borderRadius: 8, marginBottom: 20, border: '1px solid #bae6fd' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#64748b', marginBottom: 4 }}>Tipo</label>
              <select 
                value={newAcconto.tipo} 
                onChange={e => setNewAcconto(p => ({ ...p, tipo: e.target.value }))}
                style={{ width: '100%', padding: '10px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13 }}
              >
                <option value="tfr">TFR</option>
                <option value="ferie">Ferie</option>
                <option value="tredicesima">Tredicesima</option>
                <option value="quattordicesima">Quattordicesima</option>
                <option value="prestito">Prestito</option>
              </select>
            </div>
            <Field label="Importo €" value={newAcconto.importo} onChange={v => setNewAcconto(p => ({ ...p, importo: v }))} type="number" />
            <Field label="Data" value={newAcconto.data} onChange={v => setNewAcconto(p => ({ ...p, data: v }))} type="date" />
            <Field label="Note" value={newAcconto.note} onChange={v => setNewAcconto(p => ({ ...p, note: v }))} />
          </div>
          <button onClick={handleAddAcconto} disabled={saving} style={{ ...btnStyle('#10b981'), marginTop: 12 }}>
            {saving ? '⏳' : '💾'} Salva Acconto
          </button>
        </div>
      )}

      {/* Totale e TFR Info */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 16 }}>
        <div style={{ padding: 12, background: '#f0fdf4', borderRadius: 8, textAlign: 'center' }}>
          <div style={{ fontSize: 11, color: '#64748b' }}>TFR Accantonato</div>
          <div style={{ fontWeight: 700, color: '#059669' }}>{formatEuro(accontiObj.tfr_accantonato || 0)}</div>
        </div>
        <div style={{ padding: 12, background: '#fef3c7', borderRadius: 8, textAlign: 'center' }}>
          <div style={{ fontSize: 11, color: '#64748b' }}>Totale Acconti</div>
          <div style={{ fontWeight: 700, color: '#f59e0b' }}>{formatEuro(totaleAcconti)}</div>
        </div>
        <div style={{ padding: 12, background: '#dbeafe', borderRadius: 8, textAlign: 'center' }}>
          <div style={{ fontSize: 11, color: '#64748b' }}>TFR Saldo</div>
          <div style={{ fontWeight: 700, color: '#2563eb' }}>{formatEuro(accontiObj.tfr_saldo || 0)}</div>
        </div>
      </div>
      
      {allAcconti.length === 0 ? (
        <EmptyState icon="💵" text="Nessun acconto registrato" />
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#f8fafc' }}>
              <th style={thStyle}>Data</th>
              <th style={thStyle}>Tipo</th>
              <th style={{ ...thStyle, textAlign: 'right' }}>Importo</th>
              <th style={thStyle}>Note</th>
              <th style={{ ...thStyle, textAlign: 'center' }}>Azioni</th>
            </tr>
          </thead>
          <tbody>
            {allAcconti.map((a, idx) => (
              <tr key={a.id || idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                <td style={tdStyle}>{a.data ? formatDateIT(a.data) : '-'}</td>
                <td style={tdStyle}><span style={{ padding: '2px 8px', background: '#f1f5f9', borderRadius: 4, fontSize: 11 }}>{a.tipo || 'N/D'}</span></td>
                <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 600, color: '#f59e0b' }}>{formatEuro(a.importo || 0)}</td>
                <td style={tdStyle}>{a.note || '-'}</td>
                <td style={{ ...tdStyle, textAlign: 'center' }}>
                  <button
                    onClick={() => setEditingAcconto({ ...a })}
                    style={{ ...btnStyle('#3b82f6', 'small'), marginRight: 4 }}
                    title="Modifica"
                  >
                    ✏️
                  </button>
                  <button
                    onClick={() => handleDeleteAcconto(a.id)}
                    disabled={deleting === a.id}
                    style={{ ...btnStyle('#ef4444', 'small'), opacity: deleting === a.id ? 0.5 : 1 }}
                    title="Elimina"
                  >
                    {deleting === a.id ? '⏳' : '🗑️'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Modal di modifica acconto */}
      {editingAcconto && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000
        }}>
          <div style={{
            background: 'white',
            borderRadius: 12,
            padding: 24,
            width: '90%',
            maxWidth: 500,
            boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)'
          }}>
            <h3 style={{ margin: '0 0 20px', fontSize: 18 }}>✏️ Modifica Acconto</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: '#64748b', marginBottom: 4 }}>Tipo</label>
                <select 
                  value={editingAcconto.tipo} 
                  onChange={e => setEditingAcconto(p => ({ ...p, tipo: e.target.value }))}
                  style={{ width: '100%', padding: '10px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13 }}
                >
                  <option value="tfr">TFR</option>
                  <option value="ferie">Ferie</option>
                  <option value="tredicesima">Tredicesima</option>
                  <option value="quattordicesima">Quattordicesima</option>
                  <option value="prestito">Prestito</option>
                </select>
              </div>
              <Field 
                label="Importo €" 
                value={editingAcconto.importo} 
                onChange={v => setEditingAcconto(p => ({ ...p, importo: v }))} 
                type="number" 
              />
              <Field 
                label="Data" 
                value={editingAcconto.data} 
                onChange={v => setEditingAcconto(p => ({ ...p, data: v }))} 
                type="date" 
              />
              <Field 
                label="Note" 
                value={editingAcconto.note} 
                onChange={v => setEditingAcconto(p => ({ ...p, note: v }))} 
              />
            </div>
            <div style={{ display: 'flex', gap: 12, marginTop: 20 }}>
              <button 
                onClick={() => setEditingAcconto(null)} 
                style={{ ...btnStyle('#64748b'), flex: 1 }}
              >
                Annulla
              </button>
              <button 
                onClick={handleUpdateAcconto} 
                disabled={saving}
                style={{ ...btnStyle('#10b981'), flex: 1 }}
              >
                {saving ? '⏳' : '💾'} Salva Modifiche
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================
// HELPER COMPONENTS
// ============================================

function Field({ label, value, onChange, disabled, type = 'text' }) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: 11, color: '#64748b', marginBottom: 4 }}>{label}</label>
      <input
        type={type}
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        style={{
          width: '100%',
          padding: '10px 12px',
          border: '1px solid #e5e7eb',
          borderRadius: 6,
          fontSize: 13,
          background: disabled ? '#f8fafc' : 'white'
        }}
      />
    </div>
  );
}

function StatBox({ label, value, color }) {
  return (
    <div style={{ padding: 12, background: '#f8fafc', borderRadius: 8, borderLeft: `4px solid ${color}` }}>
      <div style={{ fontSize: 11, color: '#64748b' }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 700, color }}>{value}</div>
    </div>
  );
}

function EmptyState({ icon, text }) {
  return (
    <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
      <div style={{ fontSize: 40, marginBottom: 8, opacity: 0.5 }}>{icon}</div>
      <div>{text}</div>
    </div>
  );
}

const btnStyle = (color, size = 'normal') => ({
  padding: size === 'small' ? '6px 12px' : '10px 16px',
  background: color,
  color: 'white',
  border: 'none',
  borderRadius: 6,
  cursor: 'pointer',
  fontWeight: 600,
  fontSize: size === 'small' ? 12 : 13
});

const thStyle = { padding: 10, textAlign: 'left', fontWeight: 600, color: '#374151' };
const tdStyle = { padding: 10 };

const getMeseName = (mese) => {
  const mesi = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic'];
  return mesi[(mese || 1) - 1] || mese;
};


// ============================================
// TAB GIUSTIFICATIVI
// ============================================

function TabGiustificativi({ dipendente, anno, selectedCategoria = 'tutti', onCategoriaChange }) {
  const [giustificativi, setGiustificativi] = useState([]);
  const [saldoFerie, setSaldoFerie] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Handler per cambio categoria - usa la prop se fornita
  const handleCategoriaClick = (cat) => {
    if (onCategoriaChange) {
      onCategoriaChange(cat);
    }
  };
  
  // Carica dati al mount e quando cambia dipendente
  useEffect(() => {
    if (!dipendente?.id) {
      setLoading(false);
      return;
    }
    
    let cancelled = false;
    
    const fetchData = async () => {
      setLoading(true);
      setError(null);
      
      try {
        // Prima chiamata - giustificativi
        const giustRes = await api.get(`/api/giustificativi/dipendente/${dipendente.id}/giustificativi`, { 
          params: { anno },
          timeout: 60000 // 60 secondi di timeout
        });
        
        if (cancelled) return;
        setGiustificativi(giustRes.data?.giustificativi || []);
        
        // Seconda chiamata - ferie
        const ferieRes = await api.get(`/api/giustificativi/dipendente/${dipendente.id}/saldo-ferie`, { 
          params: { anno },
          timeout: 60000
        });
        
        if (cancelled) return;
        setSaldoFerie(ferieRes.data || null);
        setLoading(false);
      } catch (err) {
        if (cancelled) return;
        console.error('Errore caricamento:', err);
        setError(err.response?.data?.detail || err.message || 'Errore caricamento');
        setLoading(false);
      }
    };
    
    fetchData();
    
    return () => { cancelled = true; };
  }, [dipendente?.id, anno]);
  
  // Se non c'è dipendente selezionato
  if (!dipendente?.id) {
    return <div style={{ textAlign: 'center', padding: 40, color: '#6b7280' }}>Seleziona un dipendente</div>;
  }
  
  if (error) {
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <div style={{ color: '#dc2626', marginBottom: 16 }}>Errore: {error}</div>
      </div>
    );
  }
  
  const categorie = ['tutti', 'ferie', 'permesso', 'assenza', 'congedo', 'malattia', 'formazione', 'lavoro'];
  
  const filteredGiustificativi = selectedCategoria === 'tutti' 
    ? giustificativi 
    : giustificativi.filter(g => g.categoria === selectedCategoria);
  
  if (loading) return <div style={{ textAlign: 'center', padding: 40, color: '#6b7280' }}>Caricamento...</div>;
  
  return (
    <div>
      {/* Riepilogo Ferie/ROL/Ex-Festività */}
      {saldoFerie && (
        <div style={{ marginBottom: 24 }}>
          <h4 style={{ margin: '0 0 12px 0', color: '#1e3a5f', fontSize: 15 }}>📊 Riepilogo {anno}</h4>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
            {/* Ferie */}
            <div style={{ background: '#dcfce7', borderRadius: 10, padding: 16, border: '1px solid #86efac' }}>
              <div style={{ fontSize: 12, color: '#166534', marginBottom: 4 }}>🏖️ FERIE</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: '#166534' }}>
                {saldoFerie.ferie?.giorni_residui?.toFixed(1) || 0} <span style={{ fontSize: 12 }}>giorni</span>
              </div>
              <div style={{ fontSize: 11, color: '#15803d', marginTop: 4 }}>
                Maturate: {saldoFerie.ferie?.maturate?.toFixed(0)}h | Godute: {saldoFerie.ferie?.godute?.toFixed(0)}h
              </div>
            </div>
            
            {/* ROL */}
            <div style={{ background: '#dbeafe', borderRadius: 10, padding: 16, border: '1px solid #93c5fd' }}>
              <div style={{ fontSize: 12, color: '#1e40af', marginBottom: 4 }}>⏰ ROL</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: '#1e40af' }}>
                {saldoFerie.rol?.residui?.toFixed(0) || 0} <span style={{ fontSize: 12 }}>ore</span>
              </div>
              <div style={{ fontSize: 11, color: '#1d4ed8', marginTop: 4 }}>
                Maturati: {saldoFerie.rol?.maturati?.toFixed(0)}h | Goduti: {saldoFerie.rol?.goduti?.toFixed(0)}h
              </div>
            </div>
            
            {/* Ex Festività */}
            <div style={{ background: '#fef3c7', borderRadius: 10, padding: 16, border: '1px solid #fcd34d' }}>
              <div style={{ fontSize: 12, color: '#92400e', marginBottom: 4 }}>📅 EX FESTIVITÀ</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: '#92400e' }}>
                {saldoFerie.ex_festivita?.residue?.toFixed(0) || 0} <span style={{ fontSize: 12 }}>ore</span>
              </div>
              <div style={{ fontSize: 11, color: '#b45309', marginTop: 4 }}>
                Maturate: {saldoFerie.ex_festivita?.maturate?.toFixed(0)}h | Godute: {saldoFerie.ex_festivita?.godute?.toFixed(0)}h
              </div>
            </div>
            
            {/* Permessi */}
            <div style={{ background: '#f3e8ff', borderRadius: 10, padding: 16, border: '1px solid #d8b4fe' }}>
              <div style={{ fontSize: 12, color: '#6b21a8', marginBottom: 4 }}>🎫 PERMESSI</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: '#6b21a8' }}>
                {saldoFerie.permessi?.goduti_anno?.toFixed(0) || 0} <span style={{ fontSize: 12 }}>ore usate</span>
              </div>
              <div style={{ fontSize: 11, color: '#7c3aed', marginTop: 4 }}>
                Anno {anno}
              </div>
            </div>
          </div>
        </div>
      )}
      
      {/* Filtro Categorie */}
      <div style={{ marginBottom: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {categorie.map(cat => (
          <button
            key={cat}
            onClick={() => handleCategoriaClick(cat)}
            data-testid={`categoria-${cat}`}
            style={{
              padding: '6px 14px',
              borderRadius: 20,
              border: 'none',
              background: selectedCategoria === cat ? '#1e3a5f' : '#e5e7eb',
              color: selectedCategoria === cat ? 'white' : '#374151',
              cursor: 'pointer',
              fontSize: 12,
              fontWeight: 500,
              textTransform: 'capitalize'
            }}
          >
            {cat}
          </button>
        ))}
      </div>
      
      {/* Tabella Giustificativi */}
      <div style={{ background: 'white', borderRadius: 10, border: '1px solid #e5e7eb', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e5e7eb' }}>
              <th style={{ ...thStyle, width: 80 }}>Codice</th>
              <th style={thStyle}>Descrizione</th>
              <th style={{ ...thStyle, width: 100, textAlign: 'center' }}>Limite Anno</th>
              <th style={{ ...thStyle, width: 100, textAlign: 'center' }}>Limite Mese</th>
              <th style={{ ...thStyle, width: 100, textAlign: 'center' }}>Usate Anno</th>
              <th style={{ ...thStyle, width: 100, textAlign: 'center' }}>Usate Mese</th>
              <th style={{ ...thStyle, width: 100, textAlign: 'center' }}>Residuo</th>
              <th style={{ ...thStyle, width: 80, textAlign: 'center' }}>Stato</th>
            </tr>
          </thead>
          <tbody>
            {filteredGiustificativi.map((g, idx) => {
              const superato = g.superato_annuale || g.superato_mensile;
              const warning = g.residuo_annuale !== null && g.residuo_annuale < 10 && g.residuo_annuale >= 0;
              
              return (
                <tr 
                  key={g.codice}
                  style={{ 
                    background: superato ? '#fef2f2' : (idx % 2 === 0 ? 'white' : '#f9fafb'),
                    borderBottom: '1px solid #e5e7eb'
                  }}
                >
                  <td style={{ ...tdStyle, fontWeight: 600, color: '#1e3a5f' }}>{g.codice}</td>
                  <td style={tdStyle}>
                    {g.descrizione}
                    {g.retribuito && <span style={{ marginLeft: 6, fontSize: 10, color: '#059669' }}>Retribuito</span>}
                  </td>
                  <td style={{ ...tdStyle, textAlign: 'center' }}>
                    {g.limite_annuale_ore != null ? `${g.limite_annuale_ore}h` : '-'}
                  </td>
                  <td style={{ ...tdStyle, textAlign: 'center' }}>
                    {g.limite_mensile_ore != null ? `${g.limite_mensile_ore}h` : '-'}
                  </td>
                  <td style={{ ...tdStyle, textAlign: 'center', fontWeight: g.ore_usate_anno > 0 ? 600 : 400 }}>
                    {g.ore_usate_anno > 0 ? `${g.ore_usate_anno.toFixed(1)}h` : '-'}
                  </td>
                  <td style={{ ...tdStyle, textAlign: 'center' }}>
                    {g.ore_usate_mese > 0 ? `${g.ore_usate_mese.toFixed(1)}h` : '-'}
                  </td>
                  <td style={{ 
                    ...tdStyle, 
                    textAlign: 'center',
                    color: superato ? '#dc2626' : (warning ? '#d97706' : '#059669'),
                    fontWeight: 600
                  }}>
                    {g.residuo_annuale != null ? `${g.residuo_annuale.toFixed(1)}h` : '-'}
                  </td>
                  <td style={{ ...tdStyle, textAlign: 'center' }}>
                    {superato ? (
                      <span style={{ color: '#dc2626', fontWeight: 600 }}>⛔ SUPERATO</span>
                    ) : warning ? (
                      <span style={{ color: '#d97706' }}>⚠️ Attenzione</span>
                    ) : (
                      <span style={{ color: '#059669' }}>✓ OK</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      
      {/* Legenda */}
      <div style={{ marginTop: 16, padding: 12, background: '#f0f9ff', borderRadius: 8, fontSize: 11, color: '#0369a1' }}>
        <strong>ℹ️ Note:</strong> I limiti mostrati sono quelli di default del CCNL. Possono essere personalizzati per ogni dipendente.
        Se viene superato un limite, il sistema bloccherà l'inserimento di nuovi giustificativi di quel tipo.
      </div>
    </div>
  );
}

// ============================================
// TAB PRESENZE BATCH
// ============================================

function TabPresenzeBatch({ dipendenti, allEmployees, currentDate, setCurrentDate }) {
  const tuttiDipendenti = (dipendenti.length > 0 ? dipendenti : allEmployees).map(d => ({
    ...d,
    nome_completo: d.nome_completo || d.name || `${d.cognome || ''} ${d.nome || ''}`.trim()
  }));

  const [selectedIds, setSelectedIds] = useState([]);
  const [dataFrom, setDataFrom] = useState('');
  const [dataTo, setDataTo] = useState('');
  const [statoScelto, setStatoScelto] = useState('assente');
  const [saltaDomenica, setSaltaDomenica] = useState(true);
  const [saltaSabato, setSaltaSabato] = useState(false);
  const [loading, setLoading] = useState(false);
  const [risultato, setRisultato] = useState(null);

  const statiDisponibili = Object.entries(STATI_PRESENZA).filter(
    ([k]) => !['riposo', 'cessato', 'riposo_settimanale'].includes(k)
  );

  const toggleDip = (id) => {
    setSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
    setRisultato(null);
  };

  const selectAll = () => setSelectedIds(tuttiDipendenti.map(d => d.id));
  const clearAll = () => setSelectedIds([]);

  const handleCompila = async () => {
    if (selectedIds.length === 0) { toast.error('Seleziona almeno un dipendente'); return; }
    if (!dataFrom || !dataTo) { toast.error('Inserisci le date'); return; }
    if (dataFrom > dataTo) { toast.error('La data di inizio deve essere prima della fine'); return; }

    setLoading(true);
    setRisultato(null);

    // Genera giorni nel range
    const giorni = [];
    let current = new Date(dataFrom);
    const end = new Date(dataTo);
    while (current <= end) {
      const dow = current.getDay();
      if (!(saltaDomenica && dow === 0) && !(saltaSabato && dow === 6)) {
        giorni.push(current.toISOString().split('T')[0]);
      }
      current.setDate(current.getDate() + 1);
    }

    if (giorni.length === 0) { toast.error('Nessun giorno da compilare'); setLoading(false); return; }

    let successi = 0, errori = 0;
    for (const empId of selectedIds) {
      for (const dateStr of giorni) {
        try {
          await api.post('/api/attendance/set-presenza', { employee_id: empId, data: dateStr, stato: statoScelto });
          successi++;
        } catch { errori++; }
      }
    }

    setRisultato({ successi, errori, giorni: giorni.length, dipendenti: selectedIds.length, stato: statoScelto });
    if (errori === 0) toast.success(`✅ ${successi} presenze compilate`);
    else toast.warning(`⚠️ ${successi} ok, ${errori} errori`);
    setLoading(false);
  };

  const nGiorni = (() => {
    if (!dataFrom || !dataTo || dataFrom > dataTo) return 0;
    let n = 0, cur = new Date(dataFrom), end = new Date(dataTo);
    while (cur <= end) {
      const d = cur.getDay();
      if (!(saltaDomenica && d === 0) && !(saltaSabato && d === 6)) n++;
      cur.setDate(cur.getDate() + 1);
    }
    return n;
  })();

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 20, alignItems: 'start' }}>

      {/* Colonna sinistra: form */}
      <div>
        <h3 style={{ margin: '0 0 18px', fontSize: 17, fontWeight: 700, color: '#1e3a5f' }}>📅 Compilazione Presenze</h3>

        {/* Date + Stato */}
        <div style={{ background: '#f8fafc', borderRadius: 12, padding: 20, border: '1px solid #e2e8f0', marginBottom: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 16 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 6 }}>📅 Data Inizio *</label>
              <input type="date" value={dataFrom} onChange={e => { setDataFrom(e.target.value); setRisultato(null); }}
                style={{ width: '100%', padding: '10px 12px', border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 14 }} />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 6 }}>📅 Data Fine *</label>
              <input type="date" value={dataTo} onChange={e => { setDataTo(e.target.value); setRisultato(null); }}
                style={{ width: '100%', padding: '10px 12px', border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 14 }} />
            </div>
          </div>

          {/* Opzioni */}
          <div style={{ display: 'flex', gap: 20, marginBottom: 16, flexWrap: 'wrap' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 7, cursor: 'pointer', fontSize: 13, color: '#374151' }}>
              <input type="checkbox" checked={saltaDomenica} onChange={e => setSaltaDomenica(e.target.checked)} />
              Salta domeniche
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 7, cursor: 'pointer', fontSize: 13, color: '#374151' }}>
              <input type="checkbox" checked={saltaSabato} onChange={e => setSaltaSabato(e.target.checked)} />
              Salta sabati
            </label>
          </div>

          {/* Stato */}
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 10 }}>🏷️ Stato da applicare *</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
            {statiDisponibili.map(([key, cfg]) => (
              <button key={key} onClick={() => setStatoScelto(key)} style={{
                padding: '7px 13px', borderRadius: 8,
                border: statoScelto === key ? `2px solid ${cfg.color}` : '2px solid transparent',
                background: statoScelto === key ? cfg.bg : '#f1f5f9',
                color: statoScelto === key ? cfg.color : '#64748b',
                fontWeight: statoScelto === key ? 700 : 400,
                cursor: 'pointer', fontSize: 12.5,
                display: 'flex', alignItems: 'center', gap: 5, transition: 'all .1s'
              }}>
                <span style={{ width: 20, height: 20, borderRadius: 4, background: cfg.bg, color: cfg.color, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 9, fontWeight: 700, border: `1px solid ${cfg.color}40` }}>
                  {cfg.label}
                </span>
                {cfg.name}
              </button>
            ))}
          </div>
        </div>

        {/* Preview */}
        {dataFrom && dataTo && dataFrom <= dataTo && selectedIds.length > 0 && (
          <div style={{ padding: '12px 16px', background: '#eff6ff', borderRadius: 10, fontSize: 13, color: '#1e40af', border: '1px solid #bfdbfe', marginBottom: 16 }}>
            ℹ️ <strong>{selectedIds.length} dipendenti</strong> × <strong>{nGiorni} giorni</strong>
            {' '}= <strong>{selectedIds.length * nGiorni} presenze</strong> da impostare a{' '}
            <strong style={{ color: STATI_PRESENZA[statoScelto]?.color }}>"{STATI_PRESENZA[statoScelto]?.name}"</strong>
            {saltaDomenica ? ' · dom. escluse' : ''}
            {saltaSabato ? ' · sab. esclusi' : ''}
          </div>
        )}

        <button onClick={handleCompila}
          disabled={loading || selectedIds.length === 0 || !dataFrom || !dataTo}
          style={{
            padding: '13px 30px', background: loading ? '#94a3b8' : '#1e3a5f', color: 'white',
            border: 'none', borderRadius: 9, cursor: 'pointer', fontWeight: 700, fontSize: 14,
            display: 'flex', alignItems: 'center', gap: 8, opacity: selectedIds.length === 0 || !dataFrom || !dataTo ? .6 : 1
          }}>
          {loading ? '⏳ Compilazione...' : `✅ Compila ${selectedIds.length > 0 ? selectedIds.length + ' dipendenti' : ''}`}
        </button>

        {/* Risultato */}
        {risultato && (
          <div style={{ marginTop: 18, padding: '16px 20px', borderRadius: 12, background: risultato.errori === 0 ? '#f0fdf4' : '#fef9c3', border: `1px solid ${risultato.errori === 0 ? '#86efac' : '#fcd34d'}`, display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{ fontSize: 36 }}>{risultato.errori === 0 ? '✅' : '⚠️'}</div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 15, color: '#1e293b', marginBottom: 3 }}>
                {risultato.errori === 0 ? 'Completato!' : 'Completato con errori'}
              </div>
              <div style={{ fontSize: 13, color: '#64748b' }}>
                <strong>{risultato.successi}</strong> presenze impostate come "{STATI_PRESENZA[risultato.stato]?.name}"
                su <strong>{risultato.dipendenti}</strong> dipendenti × <strong>{risultato.giorni}</strong> giorni
                {risultato.errori > 0 && <span style={{ color: '#dc2626', marginLeft: 8 }}>• {risultato.errori} errori</span>}
              </div>
            </div>
          </div>
        )}

        <div style={{ marginTop: 14, padding: '10px 14px', background: '#f0f9ff', borderRadius: 8, fontSize: 11.5, color: '#0369a1', border: '1px solid #bae6fd' }}>
          <strong>💡</strong> Seleziona uno o più dipendenti dalla lista a destra, imposta il periodo e lo stato, poi clicca Compila.
        </div>
      </div>

      {/* Colonna destra: lista dipendenti chip */}
      <div style={{ background: 'white', borderRadius: 12, border: '1px solid #e5e7eb', overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,.06)' }}>
        <div style={{ padding: '12px 14px', borderBottom: '1px solid #e5e7eb', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#f8fafc' }}>
          <div style={{ fontWeight: 600, fontSize: 13, color: '#1e3a5f' }}>
            👥 Dipendenti <span style={{ fontWeight: 400, color: '#6b7280' }}>({selectedIds.length}/{tuttiDipendenti.length} sel.)</span>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={selectAll} style={{ padding: '4px 10px', background: '#1e3a5f', color: 'white', border: 'none', borderRadius: 6, fontSize: 11, cursor: 'pointer', fontWeight: 600 }}>
              Tutti
            </button>
            <button onClick={clearAll} style={{ padding: '4px 10px', background: '#f3f4f6', color: '#374151', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 11, cursor: 'pointer' }}>
              Nessuno
            </button>
          </div>
        </div>
        <div style={{ maxHeight: 460, overflowY: 'auto', padding: '8px 10px' }}>
          {tuttiDipendenti.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 30, color: '#94a3b8', fontSize: 13 }}>Nessun dipendente</div>
          ) : (
            tuttiDipendenti.map(d => {
              const sel = selectedIds.includes(d.id);
              return (
                <div key={d.id} onClick={() => toggleDip(d.id)} style={{
                  padding: '10px 12px', marginBottom: 5, borderRadius: 8, cursor: 'pointer',
                  background: sel ? '#dbeafe' : '#f8fafc',
                  border: sel ? '2px solid #3b82f6' : '1.5px solid transparent',
                  display: 'flex', alignItems: 'center', gap: 10, transition: 'all .12s'
                }}>
                  <div style={{
                    width: 22, height: 22, borderRadius: 6, flexShrink: 0,
                    background: sel ? '#3b82f6' : '#e5e7eb',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: sel ? 'white' : '#94a3b8', fontSize: 13, fontWeight: 700
                  }}>
                    {sel ? '✓' : ''}
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{d.nome_completo}</div>
                    <div style={{ fontSize: 11, color: '#64748b' }}>{d.mansione || d.qualifica || ''}</div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

    </div>
  );
}

// ============================================
// TAB RICHIESTE
// ============================================

function TabRichieste({ richieste, onRefresh }) {
  const handleApprova = async (id) => {
    try {
      await api.put(`/api/attendance/richiesta-assenza/${id}/approva`);
      toast.success('✅ Richiesta approvata');
      onRefresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Errore approvazione');
    }
  };

  const handleRifiuta = async (id) => {
    const motivo = prompt('Motivo del rifiuto:');
    if (!motivo) return;
    try {
      await api.put(`/api/attendance/richiesta-assenza/${id}/rifiuta`, { motivo });
      toast.success('Richiesta rifiutata');
      onRefresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Errore');
    }
  };

  return (
    <div>
      <h3 style={{ margin: '0 0 20px 0', fontSize: 16, color: '#1e3a5f' }}>📋 Richieste in Attesa</h3>
      {richieste.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: '#9ca3af' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>✅</div>
          <div>Nessuna richiesta in attesa di approvazione</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {richieste.map(r => (
            <div key={r.id} style={{
              padding: 16, background: '#f9fafb', borderRadius: 8,
              borderLeft: '4px solid #eab308',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center'
            }}>
              <div>
                <div style={{ fontWeight: 600, color: '#1f2937', marginBottom: 4 }}>{r.employee_nome}</div>
                <div style={{ fontSize: 13, color: '#6b7280' }}>
                  <span style={{
                    display: 'inline-block', padding: '2px 8px',
                    background: '#fef3c7', color: '#92400e',
                    borderRadius: 4, fontSize: 11, fontWeight: 600, marginRight: 8
                  }}>{r.tipo}</span>
                  📅 {r.data_inizio} → {r.data_fine}
                  <span style={{ marginLeft: 8, fontWeight: 600 }}>({r.giorni_totali} giorni)</span>
                </div>
                {r.motivo && <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 4 }}>{r.motivo}</div>}
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={() => handleApprova(r.id)} style={{
                  padding: '8px 16px', background: '#22c55e', color: 'white',
                  border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer'
                }}>✓ Approva</button>
                <button onClick={() => handleRifiuta(r.id)} style={{
                  padding: '8px 16px', background: '#ef4444', color: 'white',
                  border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer'
                }}>✕ Rifiuta</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ============================================
// TAB STORICO ORE
// ============================================

function TabStoricoOre({ employees, currentDate, setCurrentDate }) {
  const [selectedEmp, setSelectedEmp] = useState('');
  const [storicoData, setStoricoData] = useState(null);
  const [loading, setLoading] = useState(false);
  const currentYear = currentDate.getFullYear();
  const currentMonth = currentDate.getMonth();

  const loadStorico = async () => {
    if (!selectedEmp) { toast.error('Seleziona un dipendente'); return; }
    setLoading(true);
    try {
      const res = await api.get(`/api/attendance/ore-lavorate/${selectedEmp}?mese=${currentMonth + 1}&anno=${currentYear}`);
      setStoricoData(res.data);
    } catch (e) {
      toast.error('Errore caricamento storico ore');
    } finally {
      setLoading(false);
    }
  };

  const navMonth = (delta) => setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth() + delta, 1));

  return (
    <div>
      <h3 style={{ margin: '0 0 20px 0', fontSize: 16, color: '#1e3a5f' }}>⏱️ Storico Ore</h3>
      <div style={{ background: '#f8fafc', borderRadius: 10, padding: 16, marginBottom: 20, display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-end' }}>
        <div style={{ flex: 1, minWidth: 200 }}>
          <label style={{ display: 'block', fontSize: 13, color: '#6b7280', marginBottom: 6 }}>Dipendente *</label>
          <select value={selectedEmp} onChange={e => setSelectedEmp(e.target.value)}
            style={{ width: '100%', padding: '10px 12px', border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 14 }}>
            <option value="">Seleziona...</option>
            {employees.map(e => (
              <option key={e.id} value={e.id}>{e.nome_completo || e.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 13, color: '#6b7280', marginBottom: 6 }}>Periodo</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button onClick={() => navMonth(-1)} style={{ padding: '8px 10px', border: '1px solid #e5e7eb', borderRadius: 6, cursor: 'pointer', background: 'white' }}>◀</button>
            <div style={{ padding: '10px 16px', border: '1px solid #e5e7eb', borderRadius: 6, fontWeight: 500, minWidth: 140, textAlign: 'center' }}>
              {MESI[currentMonth]} {currentYear}
            </div>
            <button onClick={() => navMonth(1)} style={{ padding: '8px 10px', border: '1px solid #e5e7eb', borderRadius: 6, cursor: 'pointer', background: 'white' }}>▶</button>
          </div>
        </div>
        <button onClick={loadStorico} disabled={loading}
          style={{ padding: '10px 20px', background: '#1e3a5f', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600 }}>
          {loading ? '⏳' : '🔍 Carica Storico'}
        </button>
      </div>

      {storicoData ? (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 20 }}>
            {[
              { label: 'Ore Ordinarie', value: storicoData.riepilogo?.ore_ordinarie?.toFixed(2) || 0, color: '#1e3a5f' },
              { label: 'Ore Straordinarie', value: storicoData.riepilogo?.ore_straordinario?.toFixed(2) || 0, color: '#f97316' },
              { label: 'Ore Totali', value: storicoData.riepilogo?.ore_totali?.toFixed(2) || 0, color: '#10b981' },
            ].map(s => (
              <div key={s.label} style={{ background: 'white', borderRadius: 10, padding: 16, border: '1px solid #e5e7eb', textAlign: 'center' }}>
                <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4 }}>{s.label}</div>
                <div style={{ fontSize: 24, fontWeight: 700, color: s.color }}>{s.value}h</div>
              </div>
            ))}
          </div>
          <div style={{ background: 'white', borderRadius: 10, border: '1px solid #e5e7eb', overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: '#f8fafc' }}>
                  {['Data', 'Giorno', 'Entrata', 'Uscita', 'Ore Ord.', 'Straord.', 'Totale'].map(h => (
                    <th key={h} style={{ ...thStyle, textAlign: h === 'Data' || h === 'Giorno' ? 'left' : 'right' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(storicoData.giorni || []).map((g, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #f1f5f9', background: i % 2 === 0 ? 'white' : '#f9fafb' }}>
                    <td style={tdStyle}>{g.data}</td>
                    <td style={tdStyle}>{g.giorno_settimana}</td>
                    <td style={{ ...tdStyle, textAlign: 'right' }}>{g.entrata || '-'}</td>
                    <td style={{ ...tdStyle, textAlign: 'right' }}>{g.uscita || '-'}</td>
                    <td style={{ ...tdStyle, textAlign: 'right' }}>{g.ore_ordinarie?.toFixed(2) || '-'}</td>
                    <td style={{ ...tdStyle, textAlign: 'right', color: '#f97316' }}>
                      {g.ore_straordinario > 0 ? `+${g.ore_straordinario.toFixed(2)}` : '-'}
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700 }}>{g.ore_totali?.toFixed(2) || '-'}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr style={{ background: '#f0fdf4', fontWeight: 700 }}>
                  <td colSpan="4" style={{ ...tdStyle }}>TOTALE MESE</td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>{storicoData.riepilogo?.ore_ordinarie?.toFixed(2)}h</td>
                  <td style={{ ...tdStyle, textAlign: 'right', color: '#f97316' }}>
                    {storicoData.riepilogo?.ore_straordinario > 0 ? `+${storicoData.riepilogo?.ore_straordinario?.toFixed(2)}h` : '-'}
                  </td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>{storicoData.riepilogo?.ore_totali?.toFixed(2)}h</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: 60, color: '#9ca3af' }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>⏱️</div>
          <div>Seleziona un dipendente e clicca "Carica Storico"</div>
        </div>
      )}
    </div>
  );
}

// ============================================
// TAB PAGHE (Buste Paga + F24)
// ============================================

const MESI_PAGHE = ['', 'Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic'];

function BadgeStatoPaghe({ stato }) {
  const isOk = stato === 'PAGATO';
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 700,
      background: isOk ? '#d1fae5' : '#fef3c7',
      color: isOk ? '#065f46' : '#92400e',
      border: `1px solid ${isOk ? '#6ee7b7' : '#fcd34d'}`
    }}>
      {isOk ? '✓' : '⏳'} {stato || 'N/D'}
    </span>
  );
}

function TabPaghe({ anno }) {
  const [bustePaga, setBustePaga] = useState([]);
  const [f24, setF24] = useState([]);
  const [loadingBuste, setLoadingBuste] = useState(false);
  const [loadingF24, setLoadingF24] = useState(false);
  const [expandedBusta, setExpandedBusta] = useState(null);
  const [expandedF24, setExpandedF24] = useState(null);

  const loadBuste = async () => {
    setLoadingBuste(true);
    try {
      const res = await api.get('/api/paghe/buste-paga', { params: { anno } });
      setBustePaga(res.data?.data || []);
    } catch (e) { console.error(e); }
    setLoadingBuste(false);
  };

  const loadF24 = async () => {
    setLoadingF24(true);
    try {
      const res = await api.get('/api/paghe/distinte-f24', { params: { anno } });
      setF24(res.data?.data || []);
    } catch (e) { console.error(e); }
    setLoadingF24(false);
  };

  useEffect(() => { loadBuste(); loadF24(); }, [anno]);

  const totBustePagato = bustePaga.filter(b => b.stato_pagamento === 'PAGATO').reduce((s, b) => s + (b.netto_mese || 0), 0);
  const totBusteDaPagare = bustePaga.filter(b => b.stato_pagamento !== 'PAGATO').reduce((s, b) => s + (b.netto_mese || 0), 0);
  const totF24Pagato = f24.filter(f => f.stato_pagamento === 'PAGATO').reduce((s, f) => s + (f.totale || 0), 0);
  const totF24DaPagare = f24.filter(f => f.stato_pagamento !== 'PAGATO').reduce((s, f) => s + (f.totale || 0), 0);

  const cardStyle = { background: 'white', borderRadius: 12, border: '1px solid #e5e7eb', overflow: 'hidden' };
  const sectionHeaderStyle = { padding: '14px 18px', borderBottom: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', justifyContent: 'space-between' };
  const statRowStyle = { padding: '12px 16px', display: 'flex', gap: 10, background: '#fafafa', borderBottom: '1px solid #e5e7eb', flexWrap: 'wrap' };
  const statMiniStyle = { background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: '10px 14px', flex: '1 1 100px' };

  return (
    <div>
      <h3 style={{ margin: '0 0 20px 0', fontSize: 16, color: '#1e3a5f' }}>💼 Paghe — Buste Paga & F24</h3>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>

        {/* Buste Paga */}
        <div style={cardStyle}>
          <div style={sectionHeaderStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ width: 34, height: 34, borderRadius: 8, background: '#ede9fe', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Users size={16} color="#7c3aed" />
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 14, color: '#374151' }}>Buste Paga</div>
                <div style={{ fontSize: 11, color: '#6b7280' }}>{bustePaga.length} dipendenti</div>
              </div>
            </div>
            <button onClick={loadBuste} disabled={loadingBuste} style={{ padding: '5px 10px', background: '#f3f4f6', border: 'none', borderRadius: 6, cursor: 'pointer' }}>
              <RefreshCw size={13} style={{ animation: loadingBuste ? 'spin 1s linear infinite' : 'none' }} />
            </button>
          </div>
          <div style={statRowStyle}>
            <div style={statMiniStyle}>
              <div style={{ fontSize: 10, color: '#6b7280', fontWeight: 600, textTransform: 'uppercase', letterSpacing: .4, marginBottom: 3 }}>Da Pagare</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: '#f59e0b' }}>{formatEuro(totBusteDaPagare)}</div>
            </div>
            <div style={statMiniStyle}>
              <div style={{ fontSize: 10, color: '#6b7280', fontWeight: 600, textTransform: 'uppercase', letterSpacing: .4, marginBottom: 3 }}>Pagati</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: '#10b981' }}>{formatEuro(totBustePagato)}</div>
            </div>
            <div style={statMiniStyle}>
              <div style={{ fontSize: 10, color: '#6b7280', fontWeight: 600, textTransform: 'uppercase', letterSpacing: .4, marginBottom: 3 }}>Totale</div>
              <div style={{ fontSize: 20, fontWeight: 800 }}>{formatEuro(totBustePagato + totBusteDaPagare)}</div>
            </div>
          </div>
          {bustePaga.length === 0 ? (
            <div style={{ padding: 40, textAlign: 'center', color: '#9ca3af' }}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>📄</div>
              <div style={{ fontWeight: 600 }}>Nessuna busta paga</div>
              <div style={{ fontSize: 12, marginTop: 4 }}>Carica un LUL dalla pagina Import</div>
            </div>
          ) : (
            <div style={{ maxHeight: 360, overflowY: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
                <thead>
                  <tr style={{ background: '#f9fafb' }}>
                    {['Dipendente', 'Periodo', 'Netto', 'Stato'].map(h => (
                      <th key={h} style={{ padding: '9px 12px', textAlign: 'left', fontWeight: 700, fontSize: 10.5, color: '#6b7280', borderBottom: '1px solid #e5e7eb', textTransform: 'uppercase', letterSpacing: .3 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {bustePaga.map((b, i) => (
                    <React.Fragment key={i}>
                      <tr onClick={() => setExpandedBusta(expandedBusta === i ? null : i)}
                        style={{ borderBottom: '1px solid #f3f4f6', cursor: 'pointer', background: expandedBusta === i ? '#f8fafc' : 'white' }}>
                        <td style={{ padding: '10px 12px', fontWeight: 600 }}>{b.dipendente_nome || b.codice_fiscale}</td>
                        <td style={{ padding: '10px 12px', color: '#6b7280' }}>
                          {b.periodo ? `${MESI_PAGHE[parseInt(b.periodo.split('-')[1])] || ''} ${b.periodo.split('-')[0]}` : '—'}
                        </td>
                        <td style={{ padding: '10px 12px', fontWeight: 700 }}>{formatEuro(b.netto_mese)}</td>
                        <td style={{ padding: '10px 12px' }}><BadgeStatoPaghe stato={b.stato_pagamento} /></td>
                      </tr>
                      {expandedBusta === i && (
                        <tr>
                          <td colSpan={4} style={{ padding: '0 12px 12px', background: '#f8fafc' }}>
                            <div style={{ padding: 10, background: 'white', borderRadius: 7, border: '1px solid #e5e7eb', fontSize: 11.5 }}>
                              <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                                <div><span style={{ color: '#6b7280' }}>CF:</span> <strong>{b.codice_fiscale}</strong></div>
                                {b.data_pagamento && <div><span style={{ color: '#6b7280' }}>Pagato il:</span> <strong>{formatDateIT(b.data_pagamento)}</strong></div>}
                                {b.lordo_mese && <div><span style={{ color: '#6b7280' }}>Lordo:</span> <strong>{formatEuro(b.lordo_mese)}</strong></div>}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* F24 */}
        <div style={cardStyle}>
          <div style={sectionHeaderStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ width: 34, height: 34, borderRadius: 8, background: '#fee2e2', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <FileText size={16} color="#dc2626" />
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 14, color: '#374151' }}>F24</div>
                <div style={{ fontSize: 11, color: '#6b7280' }}>{f24.length} modelli</div>
              </div>
            </div>
            <button onClick={loadF24} disabled={loadingF24} style={{ padding: '5px 10px', background: '#f3f4f6', border: 'none', borderRadius: 6, cursor: 'pointer' }}>
              <RefreshCw size={13} style={{ animation: loadingF24 ? 'spin 1s linear infinite' : 'none' }} />
            </button>
          </div>
          <div style={statRowStyle}>
            <div style={statMiniStyle}>
              <div style={{ fontSize: 10, color: '#6b7280', fontWeight: 600, textTransform: 'uppercase', letterSpacing: .4, marginBottom: 3 }}>Da Pagare</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: '#f59e0b' }}>{formatEuro(totF24DaPagare)}</div>
            </div>
            <div style={statMiniStyle}>
              <div style={{ fontSize: 10, color: '#6b7280', fontWeight: 600, textTransform: 'uppercase', letterSpacing: .4, marginBottom: 3 }}>Pagati</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: '#10b981' }}>{formatEuro(totF24Pagato)}</div>
            </div>
            <div style={statMiniStyle}>
              <div style={{ fontSize: 10, color: '#6b7280', fontWeight: 600, textTransform: 'uppercase', letterSpacing: .4, marginBottom: 3 }}>Totale</div>
              <div style={{ fontSize: 20, fontWeight: 800 }}>{formatEuro(totF24Pagato + totF24DaPagare)}</div>
            </div>
          </div>
          {f24.length === 0 ? (
            <div style={{ padding: 40, textAlign: 'center', color: '#9ca3af' }}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>📋</div>
              <div style={{ fontWeight: 600 }}>Nessun F24</div>
              <div style={{ fontSize: 12, marginTop: 4 }}>Carica un F24 dalla pagina Import</div>
            </div>
          ) : (
            <div style={{ maxHeight: 360, overflowY: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
                <thead>
                  <tr style={{ background: '#f9fafb' }}>
                    {['Periodo', 'Scadenza', 'Totale', 'Stato'].map(h => (
                      <th key={h} style={{ padding: '9px 12px', textAlign: 'left', fontWeight: 700, fontSize: 10.5, color: '#6b7280', borderBottom: '1px solid #e5e7eb', textTransform: 'uppercase', letterSpacing: .3 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {f24.map((f, i) => (
                    <React.Fragment key={i}>
                      <tr onClick={() => setExpandedF24(expandedF24 === i ? null : i)}
                        style={{ borderBottom: '1px solid #f3f4f6', cursor: 'pointer', background: expandedF24 === i ? '#f8fafc' : 'white' }}>
                        <td style={{ padding: '10px 12px', fontWeight: 600 }}>
                          {f.periodo ? `${MESI_PAGHE[parseInt(f.periodo.split('-')[1])] || ''} ${f.periodo.split('-')[0]}` : f.periodo || '—'}
                        </td>
                        <td style={{ padding: '10px 12px', color: '#6b7280' }}>{f.data_scadenza ? formatDateIT(f.data_scadenza) : '—'}</td>
                        <td style={{ padding: '10px 12px', fontWeight: 700 }}>{formatEuro(f.totale)}</td>
                        <td style={{ padding: '10px 12px' }}><BadgeStatoPaghe stato={f.stato_pagamento} /></td>
                      </tr>
                      {expandedF24 === i && f.tributi?.length > 0 && (
                        <tr>
                          <td colSpan={4} style={{ padding: '0 12px 12px', background: '#f8fafc' }}>
                            <div style={{ padding: 10, background: 'white', borderRadius: 7, border: '1px solid #e5e7eb', fontSize: 11.5 }}>
                              <div style={{ fontWeight: 600, marginBottom: 6, color: '#374151' }}>Tributi ({f.tributi.length})</div>
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                                {f.tributi.slice(0, 10).map((t, ti) => (
                                  <span key={ti} style={{ padding: '3px 7px', background: '#fee2e2', borderRadius: 4, fontSize: 11 }}>
                                    {t.codice || t.codice_tributo}: {formatEuro(t.importo || t.importo_a_debito)}
                                  </span>
                                ))}
                                {f.tributi.length > 10 && (
                                  <span style={{ padding: '3px 7px', background: '#f3f4f6', borderRadius: 4, fontSize: 11 }}>+{f.tributi.length - 10} altri</span>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================
// TAB VEICOLI (Noleggio Auto)
// ============================================

function TabVeicoli() {
  const [veicoli, setVeicoli] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ targa: '', marca: '', modello: '', anno: '', data_scadenza_noleggio: '', note: '' });
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/noleggio-auto/veicoli');
      setVeicoli(res.data?.veicoli || res.data || []);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const handleSave = async () => {
    if (!form.targa) { toast.error('Inserisci la targa'); return; }
    setSaving(true);
    try {
      await api.post('/api/noleggio-auto/veicoli', form);
      toast.success('Veicolo aggiunto');
      setShowForm(false);
      setForm({ targa: '', marca: '', modello: '', anno: '', data_scadenza_noleggio: '', note: '' });
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Errore salvataggio');
    }
    setSaving(false);
  };

  const getStatoColor = (v) => {
    if (v.stato === 'manutenzione') return { dot: '#f59e0b', label: 'Manutenzione', bg: '#fef3c7' };
    if (v.stato === 'fermo') return { dot: '#ef4444', label: 'Fermo', bg: '#fee2e2' };
    return { dot: '#22c55e', label: 'Attivo', bg: '#dcfce7' };
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h3 style={{ margin: 0, fontSize: 16, color: '#1e3a5f' }}>🚗 Veicoli — Noleggio Auto</h3>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={load} disabled={loading} style={{ padding: '8px 14px', background: '#f3f4f6', border: '1px solid #e5e7eb', borderRadius: 8, cursor: 'pointer', fontSize: 13 }}>
            🔄 Aggiorna
          </button>
          <button onClick={() => setShowForm(!showForm)} style={{ padding: '8px 16px', background: '#1e3a5f', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 600 }}>
            + Nuovo Veicolo
          </button>
        </div>
      </div>

      {/* Form nuovo veicolo */}
      {showForm && (
        <div style={{ background: '#f8fafc', borderRadius: 12, padding: 20, border: '1px solid #e2e8f0', marginBottom: 20 }}>
          <h4 style={{ margin: '0 0 16px 0', fontSize: 14, color: '#374151' }}>➕ Nuovo Veicolo</h4>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 14 }}>
            {[
              { key: 'targa', label: 'Targa *' },
              { key: 'marca', label: 'Marca' },
              { key: 'modello', label: 'Modello' },
              { key: 'anno', label: 'Anno', type: 'number' },
              { key: 'data_scadenza_noleggio', label: 'Scad. Noleggio', type: 'date' },
            ].map(f => (
              <div key={f.key}>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 5 }}>{f.label}</label>
                <input
                  type={f.type || 'text'}
                  value={form[f.key]}
                  onChange={e => setForm(prev => ({ ...prev, [f.key]: e.target.value }))}
                  style={{ width: '100%', padding: '9px 12px', border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 13 }}
                />
              </div>
            ))}
          </div>
          <div style={{ marginBottom: 14 }}>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 5 }}>Note</label>
            <input
              type="text"
              value={form.note}
              onChange={e => setForm(prev => ({ ...prev, note: e.target.value }))}
              style={{ width: '100%', padding: '9px 12px', border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 13 }}
            />
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={handleSave} disabled={saving} style={{ padding: '9px 20px', background: '#10b981', color: 'white', border: 'none', borderRadius: 8, fontWeight: 600, cursor: 'pointer', fontSize: 13 }}>
              {saving ? '⏳ Salvo...' : '💾 Salva'}
            </button>
            <button onClick={() => setShowForm(false)} style={{ padding: '9px 16px', background: '#f3f4f6', border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 13 }}>
              Annulla
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>⏳ Caricamento...</div>
      ) : veicoli.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: '#9ca3af' }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>🚗</div>
          <div style={{ fontWeight: 600 }}>Nessun veicolo registrato</div>
          <div style={{ fontSize: 13, marginTop: 4 }}>Clicca "+ Nuovo Veicolo" per aggiungerne uno</div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 14 }}>
          {veicoli.map((v, i) => {
            const stato = getStatoColor(v);
            return (
              <div key={i} style={{ background: 'white', borderRadius: 12, border: '1px solid #e5e7eb', padding: 16, boxShadow: '0 1px 3px rgba(0,0,0,.06)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                  <div style={{ fontWeight: 800, fontSize: 15, color: '#1e3a5f', fontFamily: 'monospace', background: '#f0f4ff', border: '2px solid #1e3a5f', padding: '3px 8px', borderRadius: 5 }}>
                    {v.targa}
                  </div>
                  <span style={{ padding: '3px 8px', borderRadius: 20, fontSize: 11, fontWeight: 600, background: stato.bg, color: stato.dot, border: `1px solid ${stato.dot}40` }}>
                    <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: stato.dot, marginRight: 4 }} />
                    {stato.label}
                  </span>
                </div>
                <div style={{ fontWeight: 600, fontSize: 13, color: '#374151', marginBottom: 8 }}>
                  {[v.marca, v.modello, v.anno].filter(Boolean).join(' — ')}
                </div>
                <div style={{ fontSize: 11.5, color: '#6b7280', lineHeight: 1.7 }}>
                  {v.data_scadenza_noleggio && <div>📅 Scad. noleggio: <strong>{formatDateIT(v.data_scadenza_noleggio)}</strong></div>}
                  {v.data_ultima_manutenzione && <div>🔧 Ultima manutenzione: {formatDateIT(v.data_ultima_manutenzione)}</div>}
                  {v.bollo_stato && (
                    <div>📋 Bollo: <span style={{ color: v.bollo_stato === 'pagato' ? '#22c55e' : '#f59e0b', fontWeight: 600 }}>
                      {v.bollo_stato === 'pagato' ? '✓ Pagato' : '⏳ Da pagare'}
                    </span></div>
                  )}
                  {v.note && <div style={{ marginTop: 6, fontStyle: 'italic', color: '#94a3b8' }}>{v.note}</div>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
