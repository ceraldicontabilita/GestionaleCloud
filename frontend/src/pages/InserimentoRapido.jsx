import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, formatDateIT, COLORS, SHADOWS, BORDER_RADIUS, useIsMobile } from '../lib/utils';
import api from '../api';
import { PageLayout } from '../components/PageLayout';
import { Button, Input, Select } from '../components/ds';
import {
  Banknote,
  Building2,
  Users,
  FileText,
  ArrowLeft,
  Plus,
  Check,
  CreditCard,
  Wallet,
  Save,
  ChevronRight,
  Clock,
  History,
} from 'lucide-react';

// Stili inline per massima semplicità mobile (token del design system)
const styles = {
  container: {
    minHeight: '100vh',
    background: COLORS.bg,
    padding: '12px',
    paddingBottom: '80px',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: '1fr',
    gap: '12px',
    marginBottom: '20px',
  },
  card: {
    background: COLORS.card,
    borderRadius: BORDER_RADIUS.md,
    padding: '16px',
    boxShadow: SHADOWS.sm,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    border: '2px solid transparent',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '8px',
    minHeight: '100px',
  },
  cardIcon: {
    width: '40px',
    height: '40px',
    borderRadius: BORDER_RADIUS.lg,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  cardLabel: {
    fontSize: '13px',
    fontWeight: '500',
    textAlign: 'center',
    color: COLORS.text,
  },
  form: {
    background: COLORS.card,
    borderRadius: BORDER_RADIUS.md,
    padding: '16px',
    boxShadow: SHADOWS.sm,
  },
  formTitle: {
    fontSize: '16px',
    fontWeight: '600',
    marginBottom: '16px',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    color: COLORS.text,
  },
  inputGroup: {
    marginBottom: '16px',
  },
  label: {
    display: 'block',
    fontSize: '13px',
    fontWeight: '500',
    marginBottom: '6px',
    color: COLORS.gray[600],
  },
  btnRow: {
    display: 'flex',
    gap: '8px',
    marginBottom: '12px',
  },
  message: {
    padding: '12px',
    borderRadius: BORDER_RADIUS.sm,
    marginBottom: '12px',
    fontSize: '14px',
  },
  messageSuccess: {
    background: COLORS.successLight,
    color: COLORS.success,
  },
  messageError: {
    background: COLORS.dangerLight,
    color: COLORS.danger,
  },
  list: {
    marginTop: '16px',
  },
  listItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '12px',
    background: COLORS.bgAlt,
    borderRadius: BORDER_RADIUS.sm,
    marginBottom: '8px',
  },
  listItemLeft: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  },
  listItemDesc: {
    fontSize: '14px',
    fontWeight: '500',
    color: COLORS.text,
  },
  listItemMeta: {
    fontSize: '12px',
    color: COLORS.textMuted,
  },
  listItemAmount: {
    fontSize: '15px',
    fontWeight: '600',
    color: COLORS.text,
  },
};

// Menu principale
const MENU_ITEMS = [
  { id: 'corrispettivi', label: 'Corrispettivi', icon: Banknote, color: COLORS.success, bg: COLORS.successLight },
  { id: 'pos', label: 'POS Serale', icon: CreditCard, color: COLORS.info, bg: COLORS.infoLight },
  { id: 'versamenti', label: 'Versamenti Banca', icon: Building2, color: COLORS.info, bg: COLORS.infoLight },
  { id: 'apporto', label: 'Apporto Soci', icon: Users, color: COLORS.accent, bg: COLORS.accentSoft },
  { id: 'fatture', label: 'Fatture Ricevute', icon: FileText, color: COLORS.warning, bg: COLORS.warningLight },
  { id: 'acconti', label: 'Acconti Dipendenti', icon: Wallet, color: COLORS.danger, bg: COLORS.dangerLight },
  { id: 'presenze', label: 'Presenze', icon: Users, color: COLORS.info, bg: COLORS.infoLight },
];

export default function InserimentoRapido() {
  const isMobile = useIsMobile();
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
    api
      .get('/api/rapido/dipendenti-attivi')
      .then(res => {
        setDipendenti(res.data?.dipendenti || []);
      })
      .catch(() => {
        api
          .get('/api/dipendenti')
          .then(res => {
            setDipendenti((res.data || []).filter(d => d.in_carico !== false));
          })
          .catch(() => {});
      });
  }, []);

  // Carica ultimi inserimenti
  const loadUltimiInserimenti = useCallback(() => {
    api
      .get('/api/rapido/ultimi-inserimenti?limit=5')
      .then(res => {
        setUltimiInserimenti(res.data?.inserimenti || []);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadUltimiInserimenti();
  }, [loadUltimiInserimenti]);

  // Carica fatture da pagare
  useEffect(() => {
    if (activeSection === 'fatture') {
      // Le fatture sono nella collezione "invoices"
      api
        .get(`/api/invoices?limit=100&anno=${anno}`)
        .then(res => {
          const data = res.data?.items || res.data?.invoices || res.data || [];
          // Filtra quelle senza metodo pagamento assegnato (stringa vuota, null, undefined, "None")
          const daPagare = data.filter(f => {
            const m = f.metodo_pagamento;
            return !m || m === '' || m === 'None' || m === 'null';
          });
          setFatture(daPagare.slice(0, 30));
        })
        .catch(() => {
          // Fallback fatture-ricevute
          api
            .get('/api/fatture-ricevute/archivio')
            .then(res => {
              const data = res.data?.items || res.data || [];
              const nonPagate = data.filter(f => !f.pagata && !f.metodo_pagamento);
              setFatture(nonPagate.slice(0, 30));
            })
            .catch(() => setFatture([]));
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
        tipo: 'CONTANTI',
      });
      showMessage('Corrispettivo salvato!');
      resetForm();
    } catch (err) {
      showMessage(err.response?.data?.detail || 'Errore salvataggio', 'error');
    }
    setLoading(false);
  };

  const handleSavePos = async () => {
    if (formData.importo === undefined || formData.importo === '' || formData.importo < 0) {
      showMessage('Inserisci un importo valido (anche 0 se non hai incassato POS)', 'error');
      return;
    }
    setLoading(true);
    try {
      await api.put('/api/pos-corrispettivi/chiusura-giornaliera', {
        data: formData.data || defaultDate,
        importo: parseFloat(formData.importo),
        note: formData.note || '',
      });
      showMessage('Incasso POS serale salvato!');
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
        conto_avere: 'CASSA',
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
        conto_avere: 'CAPITALE_SOCIALE',
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
      await api.post(
        `/api/rapido/paga-fattura?invoice_id=${id}&metodo_pagamento=${metodo}&importo=${importo}`
      );

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
        note: formData.note || '',
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
        note: formData.note || '',
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
        <Banknote size={20} color={COLORS.success} />
        Nuovo Corrispettivo
      </h3>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Data</label>
        <Input
          type="date"
          value={formData.data || defaultDate}
          onChange={e => setFormData({ ...formData, data: e.target.value })}
        />
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Importo (€)</label>
        <Input
          type="number"
          inputMode="decimal"
          placeholder="0.00"
          value={formData.importo || ''}
          onChange={e => setFormData({ ...formData, importo: e.target.value })}
        />
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Note (opzionale)</label>
        <Input
          type="text"
          placeholder="Es: Incasso giornaliero"
          value={formData.descrizione || ''}
          onChange={e => setFormData({ ...formData, descrizione: e.target.value })}
        />
      </div>

      <Button
        variant="success"
        style={{ width: '100%' }}
        onClick={handleSaveCorrispettivo}
        disabled={loading}
        iconLeft={<Save size={18} />}
      >
        {loading ? 'Salvataggio...' : 'Salva Corrispettivo'}
      </Button>
    </div>
  );

  const renderPosForm = () => (
    <div style={styles.form}>
      <h3 style={styles.formTitle}>
        <CreditCard size={20} color={COLORS.info} />
        Incasso POS Serale
      </h3>
      <p style={{ fontSize: '13px', color: COLORS.textMuted, marginTop: '-8px', marginBottom: '16px' }}>
        Inserisci qui l'incasso POS reale in chiusura cassa, per confrontarlo con gli accrediti
        in banca (vedi Coerenza POS Corrispettivi).
      </p>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Data</label>
        <Input
          type="date"
          value={formData.data || defaultDate}
          onChange={e => setFormData({ ...formData, data: e.target.value })}
        />
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Incasso POS (€)</label>
        <Input
          type="number"
          inputMode="decimal"
          placeholder="0.00"
          value={formData.importo ?? ''}
          onChange={e => setFormData({ ...formData, importo: e.target.value })}
        />
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Note (opzionale)</label>
        <Input
          type="text"
          placeholder="Es: scontrino POS n. 123"
          value={formData.note || ''}
          onChange={e => setFormData({ ...formData, note: e.target.value })}
        />
      </div>

      <Button
        variant="info"
        style={{ width: '100%' }}
        onClick={handleSavePos}
        disabled={loading}
        iconLeft={<Save size={18} />}
      >
        {loading ? 'Salvataggio...' : 'Salva Incasso POS'}
      </Button>
    </div>
  );

  const renderVersamentiForm = () => (
    <div style={styles.form}>
      <h3 style={styles.formTitle}>
        <Building2 size={20} color={COLORS.info} />
        Versamento in Banca
      </h3>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Data</label>
        <Input
          type="date"
          value={formData.data || defaultDate}
          onChange={e => setFormData({ ...formData, data: e.target.value })}
        />
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Importo (€)</label>
        <Input
          type="number"
          inputMode="decimal"
          placeholder="0.00"
          value={formData.importo || ''}
          onChange={e => setFormData({ ...formData, importo: e.target.value })}
        />
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Note (opzionale)</label>
        <Input
          type="text"
          placeholder="Es: Versamento settimanale"
          value={formData.descrizione || ''}
          onChange={e => setFormData({ ...formData, descrizione: e.target.value })}
        />
      </div>

      <Button
        variant="primary"
        style={{ width: '100%' }}
        onClick={handleSaveVersamento}
        disabled={loading}
        iconLeft={<Save size={18} />}
      >
        {loading ? 'Salvataggio...' : 'Salva Versamento'}
      </Button>
    </div>
  );

  const renderApportoForm = () => (
    <div style={styles.form}>
      <h3 style={styles.formTitle}>
        <Users size={20} color={COLORS.accent} />
        Apporto Soci
      </h3>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Data</label>
        <Input
          type="date"
          value={formData.data || defaultDate}
          onChange={e => setFormData({ ...formData, data: e.target.value })}
        />
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Importo (€)</label>
        <Input
          type="number"
          inputMode="decimal"
          placeholder="0.00"
          value={formData.importo || ''}
          onChange={e => setFormData({ ...formData, importo: e.target.value })}
        />
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Destinazione</label>
        <div style={styles.btnRow}>
          <Button
            variant="secondary"
            style={{
              flex: 1,
              ...(formData.destinazione === 'cassa'
                ? { background: COLORS.primarySoft, color: COLORS.primary, borderColor: COLORS.primary }
                : {}),
            }}
            onClick={() => setFormData({ ...formData, destinazione: 'cassa' })}
            iconLeft={<Wallet size={16} />}
          >
            Cassa
          </Button>
          <Button
            variant="secondary"
            style={{
              flex: 1,
              ...(formData.destinazione === 'banca'
                ? { background: COLORS.primarySoft, color: COLORS.primary, borderColor: COLORS.primary }
                : {}),
            }}
            onClick={() => setFormData({ ...formData, destinazione: 'banca' })}
            iconLeft={<Building2 size={16} />}
          >
            Banca
          </Button>
        </div>
      </div>

      <Button
        style={{ width: '100%', background: COLORS.accent, borderColor: COLORS.accent }}
        onClick={handleSaveApporto}
        disabled={loading}
        iconLeft={<Save size={18} />}
      >
        {loading ? 'Salvataggio...' : 'Salva Apporto'}
      </Button>
    </div>
  );

  const renderFattureList = () => (
    <div style={styles.form}>
      <h3 style={styles.formTitle}>
        <FileText size={20} color={COLORS.warning} />
        Fatture da Pagare
      </h3>

      {fatture.length === 0 ? (
        <p style={{ textAlign: 'center', color: COLORS.textMuted, padding: '20px' }}>
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
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'flex-end',
                  gap: '6px',
                }}
              >
                <span style={styles.listItemAmount}>
                  {formatEuro(f.total_amount || f.importo || 0)}
                </span>
                <div style={{ display: 'flex', gap: '4px' }}>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => handlePagaFattura(f, 'CASSA')}
                    iconLeft={<Wallet size={14} />}
                  >
                    Cassa
                  </Button>
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() => handlePagaFattura(f, 'BANCA')}
                    iconLeft={<Building2 size={14} />}
                  >
                    Banca
                  </Button>
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
        <Wallet size={20} color={COLORS.danger} />
        Acconto Dipendente
      </h3>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Dipendente</label>
        <Select
          value={formData.dipendente_id || ''}
          onChange={e => setFormData({ ...formData, dipendente_id: e.target.value })}
        >
          <option value="">Seleziona...</option>
          {dipendenti.map(d => (
            <option key={d.id} value={d.id}>
              {d.cognome} {d.nome}
            </option>
          ))}
        </Select>
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Data</label>
        <Input
          type="date"
          value={formData.data || defaultDate}
          onChange={e => setFormData({ ...formData, data: e.target.value })}
        />
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Importo (€)</label>
        <Input
          type="number"
          inputMode="decimal"
          placeholder="0.00"
          value={formData.importo || ''}
          onChange={e => setFormData({ ...formData, importo: e.target.value })}
        />
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Note (opzionale)</label>
        <Input
          type="text"
          placeholder="Es: Anticipo stipendio"
          value={formData.note || ''}
          onChange={e => setFormData({ ...formData, note: e.target.value })}
        />
      </div>

      <Button
        variant="danger"
        style={{ width: '100%' }}
        onClick={handleSaveAcconto}
        disabled={loading}
        iconLeft={<Save size={18} />}
      >
        {loading ? 'Salvataggio...' : 'Salva Acconto'}
      </Button>
    </div>
  );

  const renderPresenzeForm = () => (
    <div style={styles.form}>
      <h3 style={styles.formTitle}>
        <Users size={20} color={COLORS.info} />
        Registra Presenza/Assenza
      </h3>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Dipendente</label>
        <Select
          value={formData.dipendente_id || ''}
          onChange={e => setFormData({ ...formData, dipendente_id: e.target.value })}
        >
          <option value="">Seleziona...</option>
          {dipendenti.map(d => (
            <option key={d.id} value={d.id}>
              {d.cognome} {d.nome}
            </option>
          ))}
        </Select>
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Data</label>
        <Input
          type="date"
          value={formData.data || defaultDate}
          onChange={e => setFormData({ ...formData, data: e.target.value })}
        />
      </div>

      <div style={styles.inputGroup}>
        <label style={styles.label}>Tipo</label>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, 1fr)',
            gap: '8px',
          }}
        >
          {[
            { id: 'PRESENTE', label: 'Presente', variant: 'success' },
            { id: 'FERIE', label: 'Ferie', variant: 'warning' },
            { id: 'MALATTIA', label: 'Malattia', variant: 'danger' },
            { id: 'PERMESSO', label: 'Permesso', accent: true },
          ].map(tipo => {
            const active = formData.tipo_presenza === tipo.id;
            return (
              <Button
                key={tipo.id}
                variant={active && !tipo.accent ? tipo.variant : 'secondary'}
                style={active && tipo.accent ? { background: COLORS.accent, borderColor: COLORS.accent, color: '#fff' } : {}}
                onClick={() => setFormData({ ...formData, tipo_presenza: tipo.id })}
              >
                {tipo.label}
              </Button>
            );
          })}
        </div>
      </div>

      {formData.tipo_presenza === 'PRESENTE' && (
        <div style={styles.inputGroup}>
          <label style={styles.label}>Ore lavorate</label>
          <Input
            type="number"
            inputMode="decimal"
            placeholder="8"
            value={formData.ore || ''}
            onChange={e => setFormData({ ...formData, ore: e.target.value })}
          />
        </div>
      )}

      <Button
        variant="info"
        style={{ width: '100%' }}
        onClick={handleSavePresenza}
        disabled={loading}
        iconLeft={<Save size={18} />}
      >
        {loading ? 'Salvataggio...' : 'Salva Presenza'}
      </Button>
    </div>
  );

  const renderActiveForm = () => {
    switch (activeSection) {
      case 'corrispettivi':
        return renderCorrispettiviForm();
      case 'pos':
        return renderPosForm();
      case 'versamenti':
        return renderVersamentiForm();
      case 'apporto':
        return renderApportoForm();
      case 'fatture':
        return renderFattureList();
      case 'acconti':
        return renderAccontiForm();
      case 'presenze':
        return renderPresenzeForm();
      default:
        return null;
    }
  };

  return (
    <PageLayout title="Inserimento Rapido" subtitle="Gestione veloce da mobile">
      <div style={{ ...styles.container, padding: 0 }}>
        {/* Messaggio */}
        {message && (
          <div
            style={{
              ...styles.message,
              ...(message.type === 'error' ? styles.messageError : styles.messageSuccess),
            }}
          >
            {message.text}
          </div>
        )}

        {/* Menu principale o form attivo */}
        {!activeSection ? (
          <>
            <div style={{ ...styles.grid, gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, 1fr)' }}>
              {MENU_ITEMS.map(item => (
                <div
                  key={item.id}
                  style={styles.card}
                  onClick={() => {
                    setActiveSection(item.id);
                    resetForm();
                  }}
                >
                  <div style={{ ...styles.cardIcon, background: item.bg }}>
                    <item.icon size={22} color={item.color} />
                  </div>
                  <span style={styles.cardLabel}>{item.label}</span>
                </div>
              ))}
            </div>

            {/* Ultimi Inserimenti */}
            {ultimiInserimenti.length > 0 && (
              <div style={{ ...styles.form, marginTop: '8px' }}>
                <h3 style={{ ...styles.formTitle, fontSize: '14px', marginBottom: '12px' }}>
                  <History size={16} color={COLORS.textMuted} />
                  Ultimi Inserimenti
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {ultimiInserimenti.map((ins, idx) => (
                    <div
                      key={idx}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: '10px 12px',
                        background: COLORS.bgAlt,
                        borderRadius: BORDER_RADIUS.sm,
                        borderLeft: `3px solid ${
                          ins.tipo === 'corrispettivo'
                            ? COLORS.success
                            : ins.tipo === 'versamento'
                              ? COLORS.info
                              : ins.tipo === 'acconto'
                                ? COLORS.danger
                                : ins.tipo === 'presenza'
                                  ? COLORS.info
                                  : COLORS.textMuted
                        }`,
                      }}
                    >
                      <div>
                        <div style={{ fontSize: '13px', fontWeight: '500', color: COLORS.text }}>
                          {ins.descrizione}
                        </div>
                        <div style={{ fontSize: '11px', color: COLORS.textMuted }}>{formatDateIT(ins.data)}</div>
                      </div>
                      {ins.importo && (
                        <span style={{ fontSize: '14px', fontWeight: '600', color: COLORS.text }}>
                          {formatEuro(ins.importo)}
                        </span>
                      )}
                      {ins.ore && (
                        <span style={{ fontSize: '13px', color: COLORS.textMuted }}>{ins.ore}h</span>
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
            <Button
              variant="secondary"
              style={{ marginBottom: '16px', justifyContent: 'flex-start' }}
              onClick={() => {
                setActiveSection(null);
                resetForm();
              }}
              iconLeft={<ArrowLeft size={18} />}
            >
              Torna al menu
            </Button>

            {/* Form attivo */}
            {renderActiveForm()}
          </>
        )}
      </div>
    </PageLayout>
  );
}
