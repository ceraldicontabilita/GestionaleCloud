import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, formatDateIT, STYLES, COLORS, button, badge } from '../lib/utils';
import api from '../api';
import { PageLayout } from '../components/PageLayout';
import { 
  Banknote, Building2, Users, FileText, ArrowLeft,
  Plus, Check, CreditCard, Wallet, Save, ChevronRight,
  Clock, History
} from 'lucide-react';

// Stili inline per massima semplicità mobile
const styles = {
  container: {
    minHeight: '100vh',
    background: 'var(--bg-primary, #f8fafc)',
    padding: '12px',
    paddingBottom: '80px'
  },
  header: {
    background: 'linear-gradient(135deg, #1535a8 0%, #2050e8 100%)',
    borderRadius: '12px',
    padding: '16px',
    marginBottom: '16px',
    color: 'white'
  },
  headerTitle: {
    fontSize: '18px',
    fontWeight: '600',
    margin: 0
  },
  headerSub: {
    fontSize: '13px',
    opacity: 0.9,
    marginTop: '4px'
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, 1fr)',
    gap: '12px',
    marginBottom: '20px'
  },
  card: {
    background: 'white',
    borderRadius: '12px',
    padding: '16px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    border: '2px solid transparent',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '8px',
    minHeight: '100px'
  },
  cardActive: {
    borderColor: '#1535a8',
    background: '#eff6ff'
  },
  cardIcon: {
    width: '40px',
    height: '40px',
    borderRadius: '10px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center'
  },
  cardLabel: {
    fontSize: '13px',
    fontWeight: '500',
    textAlign: 'center',
    color: '#1e293b'
  },
  form: {
    background: 'white',
    borderRadius: '12px',
    padding: '16px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
  },
  formTitle: {
    fontSize: '16px',
    fontWeight: '600',
    marginBottom: '16px',
    display: 'flex',
    alignItems: 'center',
    gap: '8px'
  },
  inputGroup: {
    marginBottom: '16px'
  },
  label: {
    display: 'block',
    fontSize: '13px',
    fontWeight: '500',
    marginBottom: '6px',
    color: '#475569'
  },
  input: {
    width: '100%',
    padding: '14px 12px',
    fontSize: '16px',
    border: '1px solid #e2e8f0',
    borderRadius: '8px',
    outline: 'none',
    transition: 'border-color 0.2s'
  },
  inputFocus: {
    borderColor: '#1535a8'
  },
  btnRow: {
    display: 'flex',
    gap: '8px',
    marginBottom: '12px'
  },
  btn: {
    flex: 1,
    padding: '14px',
    fontSize: '14px',
    fontWeight: '500',
    borderRadius: '8px',
    border: 'none',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '6px',
    transition: 'all 0.2s'
  },
  btnPrimary: {
    background: '#1535a8',
    color: 'white'
  },
  btnSuccess: {
    background: '#22c55e',
    color: 'white'
  },
  btnOutline: {
    background: 'white',
    color: '#475569',
    border: '1px solid #e2e8f0'
  },
  btnOutlineActive: {
    background: '#eff6ff',
    color: '#1535a8',
    border: '2px solid #1535a8'
  },
  message: {
    padding: '12px',
    borderRadius: '8px',
    marginBottom: '12px',
    fontSize: '14px'
  },
  messageSuccess: {
    background: '#dcfce7',
    color: '#166534'
  },
  messageError: {
    background: '#fef2f2',
    color: '#dc2626'
  },
  list: {
    marginTop: '16px'
  },
  listItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '12px',
    background: '#f8fafc',
    borderRadius: '8px',
    marginBottom: '8px'
  },
  listItemLeft: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px'
  },
  listItemDesc: {
    fontSize: '14px',
    fontWeight: '500'
  },
  listItemMeta: {
    fontSize: '12px',
    color: '#64748b'
  },
  listItemAmount: {
    fontSize: '15px',
    fontWeight: '600',
    color: '#1e293b'
  }
};

// Menu principale
const MENU_ITEMS = [
  { id: 'corrispettivi', label: 'Corrispettivi', icon: Banknote, color: '#22c55e', bg: '#dcfce7' },
  { id: 'versamenti', label: 'Versamenti Banca', icon: Building2, color: '#1535a8', bg: '#dbeafe' },
  { id: 'apporto', label: 'Apporto Soci', icon: Users, color: '#8b5cf6', bg: '#ede9fe' },
  { id: 'fatture', label: 'Fatture Ricevute', icon: FileText, color: '#f59e0b', bg: '#fef3c7' },
  { id: 'acconti', label: 'Acconti Dipendenti', icon: Wallet, color: '#ec4899', bg: '#fce7f3' },
  { id: 'presenze', label: 'Presenze', icon: Users, color: '#06b6d4', bg: '#cffafe' }
];

export default function InserimentoRapido() {
  const { anno } = useAnnoGlobale();
  const navigate = useNavigate();
  const currentYear = new Date().getFullYear();
  const today = new Date().toISOString().split('T')[0];
  const defaultDate = anno === currentYear ? today : `${anno}-01-01`;
  const [activeSection, setActiveSection] = useState(null);
  const [message, setMessage] = useState(null);
  const [loading, setLoading] = useState(false);

  // Form states
  const [formData, setFormData] = useState({});
  const [dipendenti, setDipendenti] = useState([]);
  const [fatture, setFatture] = useState([]);
  const [ultimiInserimenti, setUltimiInserimenti] = useState([]);

  // Carica dipendenti
  useEffect(() => {
    api.get('/api/rapido/dipendenti-attivi').then(res => {
      setDipendenti(res.data?.dipendenti || []);
    }).catch(() => {
      api.get('/api/dipendenti').then(res => {
        setDipendenti((res.data || []).filter(d => d.in_carico !== false));
      }).catch(() => {});
    });
  }, []);

  // Carica ultimi inserimenti
  const loadUltimiInserimenti = useCallback(() => {
    api.get('/api/rapido/ultimi-inserimenti?limit=5').then(res => {
      setUltimiInserimenti(res.data?.inserimenti || []);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    loadUltimiInserimenti();
  }, [loadUltimiInserimenti]);

  // Carica fatture da pagare
  useEffect(() => {
    if (activeSection === 'fatture') {
      // Le fatture sono nella collezione "invoices"
      api.get(`/api/invoices?limit=100&anno=${anno}`).then(res => {
        const data = res.data?.items || res.data?.invoices || res.data || [];
        // Filtra quelle senza metodo pagamento assegnato (stringa vuota, null, undefined, "None")
        const daPagare = data.filter(f => {
          const m = f.metodo_pagamento;
          return !m || m === '' || m === 'None' || m === 'null';
        });
        setFatture(daPagare.slice(0, 30));
      }).catch(() => {
        // Fallback fatture-ricevute
        api.get('/api/fatture-ricevute/archivio').then(res => {
          const data = res.data?.items || res.data || [];
          const nonPagate = data.filter(f => !f.pagata && !f.metodo_pagamento);
          setFatture(nonPagate.slice(0, 30));
        }).catch(() => setFatture([]));
      });
    }
  }, [activeSection]);

  const showMessage = (text, type = 'success') => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 3000);
    // Ricarica ultimi inserimenti dopo salvataggio
    if (type === 'success') {
      setTimeout(() => loadUltimiInserimenti(), 500);
    }
  };

  const resetForm = () => {
    setFormData({});
  };

  // === HANDLERS ===

  const handleSaveCorrispettivo = async () => {
    if (!formData.importo || formData.importo <= 0) {
      showMessage('Inserisci un importo valido', 'error');
      return;
    }
    setLoading(true);
    try {
      await api.post('/api/rapido/corrispettivo', {
        data: formData.data || defaultDate,
        importo: parseFloat(formData.importo),
        descrizione: formData.descrizione || 'Corrispettivo giornaliero',
        tipo: 'CONTANTI'
      });
      showMessage('Corrispettivo salvato!');
      resetForm();
    } catch (err) {
      showMessage(err.response?.data?.detail || 'Errore salvataggio', 'error');
    }
    setLoading(false);
  };

  const handleSaveVersamento = async () => {
    if (!formData.importo || formData.importo <= 0) {
      showMessage('Inserisci un importo valido', 'error');
      return;
    }
    setLoading(true);
    try {
      await api.post('/api/rapido/versamento-banca', {
        data: formData.data || defaultDate,
        importo: parseFloat(formData.importo),
        descrizione: formData.descrizione || 'Versamento in banca',
        tipo: 'VERSAMENTO_BANCA',
        conto_dare: 'BANCA',
        conto_avere: 'CASSA'
      });
      showMessage('Versamento salvato!');
      resetForm();
    } catch (err) {
      showMessage(err.response?.data?.detail || 'Errore salvataggio', 'error');
    }
    setLoading(false);
  };

  const handleSaveApporto = async () => {
    if (!formData.importo || formData.importo <= 0) {
      showMessage('Inserisci un importo valido', 'error');
      return;
    }
    setLoading(true);
    try {
      await api.post('/api/rapido/apporto-soci', {
        data: formData.data || defaultDate,
        importo: parseFloat(formData.importo),
        descrizione: formData.descrizione || 'Apporto soci',
        tipo: 'APPORTO_SOCI',
        conto_dare: formData.destinazione === 'banca' ? 'BANCA' : 'CASSA',
        conto_avere: 'CAPITALE_SOCIALE'
      });
      showMessage('Apporto salvato!');
      resetForm();
    } catch (err) {
      showMessage(err.response?.data?.detail || 'Errore salvataggio', 'error');
    }
    setLoading(false);
  };

  const handlePagaFattura = async (fattura, metodo) => {
    setLoading(true);
    try {
      const id = fattura.id || fattura._id;
      const importo = fattura.total_amount || fattura.importo || 0;
      
      // Usa l'endpoint rapido
      await api.post(`/api/rapido/paga-fattura?invoice_id=${id}&metodo_pagamento=${metodo}&importo=${importo}`);
      
      showMessage(`Fattura pagata in ${metodo}!`);
      setFatture(prev => prev.filter(f => (f.id || f._id) !== id));
    } catch (err) {
      showMessage(err.response?.data?.detail || 'Errore', 'error');
    }
    setLoading(false);
  };

  const handleSaveAcconto = async () => {
    if (!formData.dipendente_id || !formData.importo) {
      showMessage('Seleziona dipendente e importo', 'error');
      return;
    }
    setLoading(true);
    try {
      await api.post('/api/rapido/acconto-dipendente', {
        dipendente_id: formData.dipendente_id,
        importo: parseFloat(formData.importo),
        data: formData.data || defaultDate,
        note: formData.note || ''
      });
      showMessage('Acconto salvato!');
      resetForm();
    } catch (err) {
      showMessage(err.response?.data?.detail || 'Errore', 'error');
    }
    setLoading(false);
  };

  const handleSavePresenza = async () => {
    if (!formData.dipendente_id || !formData.tipo_presenza) {
      showMessage('Seleziona dipendente e tipo', 'error');
      return;
    }
    setLoading(true);
    try {
      await api.post('/api/rapido/presenza', {
        dipendente_id: formData.dipendente_id,
        data: formData.data || defaultDate,
        tipo: formData.tipo_presenza,
        ore: formData.ore ? parseFloat(formData.ore) : null,
        note: formData.note || ''
      });
      showMessage('Presenza salvata!');
      resetForm();
    } catch (err) {
      showMessage(err.response?.data?.detail || 'Errore', 'error');
    }
    setLoading(false);
  };

  // === RENDER FORMS ===

  const renderCorrispettiviForm = () => (
    <div style={styles.form}>
      <h3 style={styles.formTitle}>
        <Banknote size={20} color="#22c55e" />
        Nuovo Corrispettivo
      </h3>
      
      <div style={styles.inputGroup}>
        <label style={styles.label}>Data</label>
        <input
          type="date"
          style={styles.input}
          value={formData.data || defaultDate}
          onChange={e => setFormData({...formData, data: e.target.value})}
        />
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Importo (€)</label>
        <input
          type="number"
          inputMode="decimal"
          placeholder="0.00"
          style={styles.input}
          value={formData.importo || ''}
          onChange={e => setFormData({...formData, importo: e.target.value})}
        />
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Note (opzionale)</label>
        <input
          type="text"
          placeholder="Es: Incasso giornaliero"
          style={styles.input}
          value={formData.descrizione || ''}
          onChange={e => setFormData({...formData, descrizione: e.target.value})}
        />
      </div>

      <button 
        style={{...styles.btn, ...styles.btnSuccess, width: '100%'}}
        onClick={handleSaveCorrispettivo}
        disabled={loading}
      >
        <Save size={18} />
        {loading ? 'Salvataggio...' : 'Salva Corrispettivo'}
      </button>
    </div>
  );

  const renderVersamentiForm = () => (
    <div style={styles.form}>
      <h3 style={styles.formTitle}>
        <Building2 size={20} color="#1535a8" />
        Versamento in Banca
      </h3>
      
      <div style={styles.inputGroup}>
        <label style={styles.label}>Data</label>
        <input
          type="date"
          style={styles.input}
          value={formData.data || defaultDate}
          onChange={e => setFormData({...formData, data: e.target.value})}
        />
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Importo (€)</label>
        <input
          type="number"
          inputMode="decimal"
          placeholder="0.00"
          style={styles.input}
          value={formData.importo || ''}
          onChange={e => setFormData({...formData, importo: e.target.value})}
        />
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Note (opzionale)</label>
        <input
          type="text"
          placeholder="Es: Versamento settimanale"
          style={styles.input}
          value={formData.descrizione || ''}
          onChange={e => setFormData({...formData, descrizione: e.target.value})}
        />
      </div>

      <button 
        style={{...styles.btn, ...styles.btnPrimary, width: '100%'}}
        onClick={handleSaveVersamento}
        disabled={loading}
      >
        <Save size={18} />
        {loading ? 'Salvataggio...' : 'Salva Versamento'}
      </button>
    </div>
  );

  const renderApportoForm = () => (
    <div style={styles.form}>
      <h3 style={styles.formTitle}>
        <Users size={20} color="#8b5cf6" />
        Apporto Soci
      </h3>
      
      <div style={styles.inputGroup}>
        <label style={styles.label}>Data</label>
        <input
          type="date"
          style={styles.input}
          value={formData.data || defaultDate}
          onChange={e => setFormData({...formData, data: e.target.value})}
        />
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Importo (€)</label>
        <input
          type="number"
          inputMode="decimal"
          placeholder="0.00"
          style={styles.input}
          value={formData.importo || ''}
          onChange={e => setFormData({...formData, importo: e.target.value})}
        />
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Destinazione</label>
        <div style={styles.btnRow}>
          <button
            style={{
              ...styles.btn,
              ...(formData.destinazione === 'cassa' ? styles.btnOutlineActive : styles.btnOutline)
            }}
            onClick={() => setFormData({...formData, destinazione: 'cassa'})}
          >
            <Wallet size={16} /> Cassa
          </button>
          <button
            style={{
              ...styles.btn,
              ...(formData.destinazione === 'banca' ? styles.btnOutlineActive : styles.btnOutline)
            }}
            onClick={() => setFormData({...formData, destinazione: 'banca'})}
          >
            <Building2 size={16} /> Banca
          </button>
        </div>
      </div>

      <button 
        style={{...styles.btn, background: '#8b5cf6', color: 'white', width: '100%'}}
        onClick={handleSaveApporto}
        disabled={loading}
      >
        <Save size={18} />
        {loading ? 'Salvataggio...' : 'Salva Apporto'}
      </button>
    </div>
  );

  const renderFattureList = () => (
    <div style={styles.form}>
      <h3 style={styles.formTitle}>
        <FileText size={20} color="#f59e0b" />
        Fatture da Pagare
      </h3>
      
      {fatture.length === 0 ? (
        <p style={{textAlign: 'center', color: '#64748b', padding: '20px'}}>
          Nessuna fattura da pagare
        </p>
      ) : (
        <div style={styles.list}>
          {fatture.map(f => (
            <div key={f.id} style={styles.listItem}>
              <div style={styles.listItemLeft}>
                <span style={styles.listItemDesc}>
                  {f.supplier_name || f.fornitore || 'Fornitore'}
                </span>
                <span style={styles.listItemMeta}>
                  {f.invoice_number || f.numero} • {formatDateIT(f.invoice_date || f.data)}
                </span>
              </div>
              <div style={{display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '6px'}}>
                <span style={styles.listItemAmount}>
                  {formatEuro(f.total_amount || f.importo || 0)}
                </span>
                <div style={{display: 'flex', gap: '4px'}}>
                  <button
                    style={{...styles.btn, padding: '8px 12px', fontSize: '12px', ...styles.btnOutline}}
                    onClick={() => handlePagaFattura(f, 'CASSA')}
                  >
                    <Wallet size={14} /> Cassa
                  </button>
                  <button
                    style={{...styles.btn, padding: '8px 12px', fontSize: '12px', ...styles.btnPrimary}}
                    onClick={() => handlePagaFattura(f, 'BANCA')}
                  >
                    <Building2 size={14} /> Banca
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const renderAccontiForm = () => (
    <div style={styles.form}>
      <h3 style={styles.formTitle}>
        <Wallet size={20} color="#ec4899" />
        Acconto Dipendente
      </h3>
      
      <div style={styles.inputGroup}>
        <label style={styles.label}>Dipendente</label>
        <select
          style={styles.input}
          value={formData.dipendente_id || ''}
          onChange={e => setFormData({...formData, dipendente_id: e.target.value})}
        >
          <option value="">Seleziona...</option>
          {dipendenti.map(d => (
            <option key={d.id} value={d.id}>
              {d.cognome} {d.nome}
            </option>
          ))}
        </select>
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Data</label>
        <input
          type="date"
          style={styles.input}
          value={formData.data || defaultDate}
          onChange={e => setFormData({...formData, data: e.target.value})}
        />
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Importo (€)</label>
        <input
          type="number"
          inputMode="decimal"
          placeholder="0.00"
          style={styles.input}
          value={formData.importo || ''}
          onChange={e => setFormData({...formData, importo: e.target.value})}
        />
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Note (opzionale)</label>
        <input
          type="text"
          placeholder="Es: Anticipo stipendio"
          style={styles.input}
          value={formData.note || ''}
          onChange={e => setFormData({...formData, note: e.target.value})}
        />
      </div>

      <button 
        style={{...styles.btn, background: '#ec4899', color: 'white', width: '100%'}}
        onClick={handleSaveAcconto}
        disabled={loading}
      >
        <Save size={18} />
        {loading ? 'Salvataggio...' : 'Salva Acconto'}
      </button>
    </div>
  );

  const renderPresenzeForm = () => (
    <div style={styles.form}>
      <h3 style={styles.formTitle}>
        <Users size={20} color="#06b6d4" />
        Registra Presenza/Assenza
      </h3>
      
      <div style={styles.inputGroup}>
        <label style={styles.label}>Dipendente</label>
        <select
          style={styles.input}
          value={formData.dipendente_id || ''}
          onChange={e => setFormData({...formData, dipendente_id: e.target.value})}
        >
          <option value="">Seleziona...</option>
          {dipendenti.map(d => (
            <option key={d.id} value={d.id}>
              {d.cognome} {d.nome}
            </option>
          ))}
        </select>
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Data</label>
        <input
          type="date"
          style={styles.input}
          value={formData.data || defaultDate}
          onChange={e => setFormData({...formData, data: e.target.value})}
        />
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Tipo</label>
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px'}}>
          {[
            { id: 'PRESENTE', label: 'Presente', color: '#22c55e' },
            { id: 'FERIE', label: 'Ferie', color: '#f59e0b' },
            { id: 'MALATTIA', label: 'Malattia', color: '#ef4444' },
            { id: 'PERMESSO', label: 'Permesso', color: '#8b5cf6' }
          ].map(tipo => (
            <button
              key={tipo.id}
              style={{
                ...styles.btn,
                padding: '12px',
                fontSize: '13px',
                background: formData.tipo_presenza === tipo.id ? tipo.color : '#f8fafc',
                color: formData.tipo_presenza === tipo.id ? 'white' : '#475569',
                border: `1px solid ${formData.tipo_presenza === tipo.id ? tipo.color : '#e2e8f0'}`
              }}
              onClick={() => setFormData({...formData, tipo_presenza: tipo.id})}
            >
              {tipo.label}
            </button>
          ))}
        </div>
      </div>

      {formData.tipo_presenza === 'PRESENTE' && (
        <div style={styles.inputGroup}>
          <label style={styles.label}>Ore lavorate</label>
          <input
            type="number"
            inputMode="decimal"
            placeholder="8"
            style={styles.input}
            value={formData.ore || ''}
            onChange={e => setFormData({...formData, ore: e.target.value})}
          />
        </div>
      )}

      <button 
        style={{...styles.btn, background: '#06b6d4', color: 'white', width: '100%'}}
        onClick={handleSavePresenza}
        disabled={loading}
      >
        <Save size={18} />
        {loading ? 'Salvataggio...' : 'Salva Presenza'}
      </button>
    </div>
  );

  const renderActiveForm = () => {
    switch (activeSection) {
      case 'corrispettivi': return renderCorrispettiviForm();
      case 'versamenti': return renderVersamentiForm();
      case 'apporto': return renderApportoForm();
      case 'fatture': return renderFattureList();
      case 'acconti': return renderAccontiForm();
      case 'presenze': return renderPresenzeForm();
      default: return null;
    }
  };

  return (
    <PageLayout title="Inserimento Rapido" subtitle="Gestione veloce da mobile">
    <div style={{...styles.container, padding: 0}}>
      {/* Header */}
      <div style={styles.header}>
        <h1 style={styles.headerTitle}>Inserimento Rapido</h1>
        <p style={styles.headerSub}>Gestione veloce da mobile</p>
      </div>

      {/* Messaggio */}
      {message && (
        <div style={{
          ...styles.message,
          ...(message.type === 'error' ? styles.messageError : styles.messageSuccess)
        }}>
          {message.text}
        </div>
      )}

      {/* Menu principale o form attivo */}
      {!activeSection ? (
        <>
          <div style={styles.grid}>
            {MENU_ITEMS.map(item => (
              <div
                key={item.id}
                style={styles.card}
                onClick={() => {
                  setActiveSection(item.id);
                  resetForm();
                }}
              >
                <div style={{...styles.cardIcon, background: item.bg}}>
                  <item.icon size={22} color={item.color} />
                </div>
                <span style={styles.cardLabel}>{item.label}</span>
              </div>
            ))}
          </div>

          {/* Ultimi Inserimenti */}
          {ultimiInserimenti.length > 0 && (
            <div style={{...styles.form, marginTop: '8px'}}>
              <h3 style={{...styles.formTitle, fontSize: '14px', marginBottom: '12px'}}>
                <History size={16} color="#64748b" />
                Ultimi Inserimenti
              </h3>
              <div style={{display: 'flex', flexDirection: 'column', gap: '8px'}}>
                {ultimiInserimenti.map((ins, idx) => (
                  <div key={idx} style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '10px 12px',
                    background: '#f8fafc',
                    borderRadius: '8px',
                    borderLeft: `3px solid ${
                      ins.tipo === 'corrispettivo' ? '#22c55e' :
                      ins.tipo === 'versamento' ? '#1535a8' :
                      ins.tipo === 'acconto' ? '#ec4899' :
                      ins.tipo === 'presenza' ? '#06b6d4' : '#64748b'
                    }`
                  }}>
                    <div>
                      <div style={{fontSize: '13px', fontWeight: '500', color: '#1e293b'}}>
                        {ins.descrizione}
                      </div>
                      <div style={{fontSize: '11px', color: '#64748b'}}>
                        {ins.data}
                      </div>
                    </div>
                    {ins.importo && (
                      <span style={{fontSize: '14px', fontWeight: '600', color: '#1e293b'}}>
                        {formatEuro(ins.importo)}
                      </span>
                    )}
                    {ins.ore && (
                      <span style={{fontSize: '13px', color: '#64748b'}}>
                        {ins.ore}h
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      ) : (
        <>
          {/* Back button */}
          <button
            style={{
              ...styles.btn,
              ...styles.btnOutline,
              marginBottom: '16px',
              justifyContent: 'flex-start'
            }}
            onClick={() => {
              setActiveSection(null);
              resetForm();
            }}
          >
            <ArrowLeft size={18} />
            Torna al menu
          </button>

          {/* Form attivo */}
          {renderActiveForm()}
        </>
      )}
    </div>
    </PageLayout>
  );
}
