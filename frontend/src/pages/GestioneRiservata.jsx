import React, { useState, useEffect } from 'react';
import { toast } from 'sonner';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { COLORS, SHADOWS, BORDER_RADIUS, FONT, formatEuro, formatDateIT } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import {
  Button,
  Badge,
  StatCard,
  Input,
  Select,
  TableWrap,
  Table,
  Th,
  Td,
  RowActions,
  RowActionButton,
} from '../components/ds';
import {
  Lock,
  Plus,
  Trash2,
  Edit2,
  Save,
  X,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Eye,
  EyeOff,
  AlertTriangle,
  CheckCircle,
} from 'lucide-react';

// Login Component
function LoginGestioneRiservata({ onLogin }) {
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await api.post('/api/gestione-riservata/login', { code });
      if (res.data.success) {
        localStorage.setItem('gestione_riservata_session', 'active');
        onLogin();
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Codice non valido');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        background: COLORS.primary,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 20,
      }}
    >
      <div
        style={{
          background: 'rgba(255,255,255,0.95)',
          borderRadius: BORDER_RADIUS.xl,
          padding: 40,
          width: '100%',
          maxWidth: 400,
          boxShadow: SHADOWS.xl,
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: 30 }}>
          <div
            style={{
              width: 80,
              height: 80,
              borderRadius: BORDER_RADIUS.full,
              background: COLORS.danger,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 20px',
            }}
          >
            <Lock size={40} color="white" />
          </div>
          <h1 style={{ margin: 0, fontSize: 24, color: COLORS.text }}>Gestione Riservata</h1>
          <p style={{ color: COLORS.textMuted, marginTop: 8 }}>Area ad accesso limitato</p>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', marginBottom: 8, color: COLORS.textMuted, fontWeight: 500 }}>
              Codice di Accesso
            </label>
            <Input
              type="password"
              value={code}
              onChange={e => setCode(e.target.value)}
              placeholder="••••••"
              data-testid="riservata-code-input"
              style={{
                padding: '14px 16px',
                fontSize: 20,
                borderRadius: BORDER_RADIUS.md,
                textAlign: 'center',
                letterSpacing: 6,
                fontFamily: FONT.mono,
              }}
              autoFocus
            />
          </div>

          {error && (
            <div
              style={{
                background: COLORS.dangerLight,
                color: COLORS.danger,
                padding: 12,
                borderRadius: BORDER_RADIUS.md,
                marginBottom: 20,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <AlertTriangle size={18} />
              {error}
            </div>
          )}

          <Button
            type="submit"
            variant="danger"
            disabled={loading || !code}
            data-testid="riservata-login-btn"
            style={{ width: '100%', padding: 14, fontSize: 16 }}
          >
            {loading ? 'Verifica...' : 'Accedi'}
          </Button>
        </form>
      </div>
    </div>
  );
}

// Main Dashboard
function DashboardGestioneRiservata({ onLogout }) {
  const [movimenti, setMovimenti] = useState([]);
  const [riepilogo, setRiepilogo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [formData, setFormData] = useState({
    data: new Date().toISOString().split('T')[0],
    tipo: 'incasso',
    descrizione: '',
    importo: '',
    categoria: 'altro',
    note: '',
  });
  const { anno } = useAnnoGlobale(); // Anno dal contesto globale
  const [mese, setMese] = useState(null);

  useEffect(() => {
    loadData();
  }, [anno, mese]);

  async function loadData() {
    setLoading(true);
    try {
      let url = `/api/gestione-riservata/movimenti?`;
      if (anno) url += `anno=${anno}&`;
      if (mese) url += `mese=${mese}`;

      const [movRes, riepRes] = await Promise.all([
        api.get(url),
        api.get(`/api/gestione-riservata/riepilogo?anno=${anno}${mese ? `&mese=${mese}` : ''}`),
      ]);

      setMovimenti(movRes.data || []);
      setRiepilogo(riepRes.data);
    } catch (e) {
      console.error('Errore caricamento:', e);
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    try {
      if (editingId) {
        await api.put(`/api/gestione-riservata/movimenti/${editingId}`, formData);
      } else {
        await api.post('/api/gestione-riservata/movimenti', formData);
      }
      setShowForm(false);
      setEditingId(null);
      setFormData({
        data: new Date().toISOString().split('T')[0],
        tipo: 'incasso',
        descrizione: '',
        importo: '',
        categoria: 'altro',
        note: '',
      });
      loadData();
    } catch (e) {
      toast.error('Errore: ' + (e.response?.data?.detail || e.message));
    }
  }

  async function handleDelete(id) {
    try {
      await api.delete(`/api/gestione-riservata/movimenti/${id}`);
      loadData();
    } catch (e) {
      toast.error('Errore: ' + (e.response?.data?.detail || e.message));
    }
  }

  function handleEdit(mov) {
    setFormData({
      data: mov.data,
      tipo: mov.tipo,
      descrizione: mov.descrizione,
      importo: mov.importo,
      categoria: mov.categoria || 'altro',
      note: mov.note || '',
    });
    setEditingId(mov.id);
    setShowForm(true);
  }

  function handleLogout() {
    localStorage.removeItem('gestione_riservata_session');
    onLogout();
  }

  const mesiNomi = [
    '',
    'Gennaio',
    'Febbraio',
    'Marzo',
    'Aprile',
    'Maggio',
    'Giugno',
    'Luglio',
    'Agosto',
    'Settembre',
    'Ottobre',
    'Novembre',
    'Dicembre',
  ];

  return (
    <PageLayout title="Gestione Riservata" subtitle="Incassi e spese non fatturati">
      <div style={{ minHeight: '100vh', background: COLORS.bg }}>
        {/* Header */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 30,
          }}
        >
          <div>
            <h1
              style={{
                margin: 0,
                color: COLORS.text,
                display: 'flex',
                alignItems: 'center',
                gap: 12,
              }}
            >
              <Lock size={28} /> Gestione Riservata
            </h1>
            <p style={{ color: COLORS.textMuted, marginTop: 4 }}>Incassi e spese non fatturati</p>
          </div>
          <Button variant="secondary" onClick={handleLogout} iconLeft={<EyeOff size={16} />}>
            Esci
          </Button>
        </div>

        {/* Filtri */}
        <div
          style={{
            display: 'flex',
            gap: 15,
            marginBottom: 25,
            flexWrap: 'wrap',
            alignItems: 'center',
          }}
        >
          <div
            style={{
              padding: '10px 16px',
              borderRadius: BORDER_RADIUS.md,
              border: `1px solid ${COLORS.border}`,
              background: COLORS.bgAlt,
              color: COLORS.textMuted,
              fontWeight: 600,
            }}
            data-testid="anno-display"
          >
            {anno} <span style={{ fontSize: 10, opacity: 0.7 }}>(globale)</span>
          </div>
          <Select
            value={mese || ''}
            onChange={e => setMese(e.target.value ? parseInt(e.target.value) : null)}
          >
            <option value="">Tutti i mesi</option>
            {mesiNomi.slice(1).map((m, i) => (
              <option key={i + 1} value={i + 1}>
                {m}
              </option>
            ))}
          </Select>
          <Button
            variant="danger"
            onClick={() => {
              setShowForm(true);
              setEditingId(null);
            }}
            iconLeft={<Plus size={18} />}
            data-testid="add-movimento-btn"
          >
            Nuovo Movimento
          </Button>
        </div>

        {/* Riepilogo Cards */}
        {riepilogo && (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: 20,
              marginBottom: 30,
            }}
          >
            <StatCard
              icon={<TrendingUp size={20} />}
              label="Incassi Non Fatturati"
              value={formatEuro(riepilogo.incassi?.totale || 0)}
              subtext={`${riepilogo.incassi?.count || 0} movimenti`}
              accent="success"
            />
            <StatCard
              icon={<TrendingDown size={20} />}
              label="Spese Non Fatturate"
              value={formatEuro(riepilogo.spese?.totale || 0)}
              subtext={`${riepilogo.spese?.count || 0} movimenti`}
              accent="danger"
            />
            <StatCard
              icon={<DollarSign size={20} />}
              label="Saldo Netto Extra"
              value={formatEuro(riepilogo.saldo_netto || 0)}
              subtext="Da aggiungere al fatturato"
              accent="primary"
            />
          </div>
        )}

        {/* Form Nuovo/Modifica */}
        {showForm && (
          <div
            style={{
              background: COLORS.card,
              borderRadius: BORDER_RADIUS.md,
              padding: 24,
              marginBottom: 25,
              boxShadow: SHADOWS.md,
              border: `1px solid ${COLORS.border}`,
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 20,
              }}
            >
              <h3 style={{ margin: 0, color: COLORS.text }}>
                {editingId ? 'Modifica Movimento' : 'Nuovo Movimento'}
              </h3>
              <button
                onClick={() => {
                  setShowForm(false);
                  setEditingId(null);
                }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex' }}
              >
                <X size={24} color={COLORS.textMuted} />
              </button>
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(3, 1fr)',
                gap: 16,
                marginBottom: 16,
              }}
            >
              <div>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 500, color: COLORS.text }}>
                  Data
                </label>
                <Input
                  type="date"
                  value={formData.data}
                  onChange={e => setFormData({ ...formData, data: e.target.value })}
                />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 500, color: COLORS.text }}>
                  Tipo
                </label>
                <Select
                  value={formData.tipo}
                  onChange={e => setFormData({ ...formData, tipo: e.target.value })}
                >
                  <option value="incasso">Incasso</option>
                  <option value="spesa">💸 Spesa</option>
                </Select>
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 500, color: COLORS.text }}>
                  Importo (€)
                </label>
                <Input
                  type="number"
                  step="0.01"
                  value={formData.importo}
                  onChange={e => setFormData({ ...formData, importo: e.target.value })}
                  placeholder="0.00"
                  data-testid="importo-input"
                />
              </div>
            </div>

            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', marginBottom: 6, fontWeight: 500, color: COLORS.text }}>
                Descrizione
              </label>
              <Input
                type="text"
                value={formData.descrizione}
                onChange={e => setFormData({ ...formData, descrizione: e.target.value })}
                placeholder="es. Mance giornaliere, Vendita extra..."
                data-testid="descrizione-input"
              />
            </div>

            <div
              style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 16, marginBottom: 20 }}
            >
              <div>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 500, color: COLORS.text }}>
                  Categoria
                </label>
                <Select
                  value={formData.categoria}
                  onChange={e => setFormData({ ...formData, categoria: e.target.value })}
                >
                  <option value="mance">Mance</option>
                  <option value="vendita_extra">Vendita Extra</option>
                  <option value="catering">Catering</option>
                  <option value="acquisti">Acquisti</option>
                  <option value="altro">Altro</option>
                </Select>
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 500, color: COLORS.text }}>
                  Note
                </label>
                <Input
                  type="text"
                  value={formData.note}
                  onChange={e => setFormData({ ...formData, note: e.target.value })}
                  placeholder="Note aggiuntive..."
                />
              </div>
            </div>

            <Button
              variant="danger"
              onClick={handleSave}
              iconLeft={<Save size={18} />}
              data-testid="save-movimento-btn"
            >
              {editingId ? 'Aggiorna' : 'Salva'}
            </Button>
          </div>
        )}

        {/* Lista Movimenti */}
        <div
          style={{
            background: COLORS.card,
            borderRadius: BORDER_RADIUS.md,
            boxShadow: SHADOWS.sm,
            border: `1px solid ${COLORS.border}`,
          }}
        >
          <div style={{ padding: '20px 24px', borderBottom: `1px solid ${COLORS.border}` }}>
            <h3 style={{ margin: 0, color: COLORS.text }}>📋 Movimenti ({movimenti.length})</h3>
          </div>

          {loading ? (
            <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>
              Caricamento...
            </div>
          ) : movimenti.length === 0 ? (
            <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>
              Nessun movimento registrato per questo periodo
            </div>
          ) : (
            <TableWrap style={{ border: 'none', borderRadius: 0 }}>
              <Table>
                <thead>
                  <tr>
                    <Th>Data</Th>
                    <Th>Tipo</Th>
                    <Th>Descrizione</Th>
                    <Th>Categoria</Th>
                    <Th align="right">Importo</Th>
                    <Th align="center">Azioni</Th>
                  </tr>
                </thead>
                <tbody>
                  {movimenti.map(mov => (
                    <tr key={mov.id}>
                      <Td>{formatDateIT(mov.data)}</Td>
                      <Td>
                        <Badge variant={mov.tipo === 'incasso' ? 'success' : 'danger'}>
                          {mov.tipo === 'incasso' ? 'Incasso' : 'Spesa'}
                        </Badge>
                      </Td>
                      <Td>{mov.descrizione}</Td>
                      <Td style={{ color: COLORS.textMuted }}>{mov.categoria}</Td>
                      <Td
                        align="right"
                        mono
                        style={{
                          fontWeight: 600,
                          color: mov.tipo === 'incasso' ? COLORS.success : COLORS.danger,
                        }}
                      >
                        {mov.tipo === 'incasso' ? '+' : '-'}
                        {formatEuro(mov.importo)}
                      </Td>
                      <Td align="center">
                        <RowActions style={{ justifyContent: 'center' }}>
                          <RowActionButton variant="info" onClick={() => handleEdit(mov)}>
                            <Edit2 size={14} />
                          </RowActionButton>
                          <RowActionButton variant="danger" onClick={() => handleDelete(mov.id)}>
                            <Trash2 size={14} />
                          </RowActionButton>
                        </RowActions>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableWrap>
          )}
        </div>
      </div>
    </PageLayout>
  );
}

// Main Component
export default function GestioneRiservata() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  useEffect(() => {
    const session = localStorage.getItem('gestione_riservata_session');
    if (session === 'active') {
      setIsLoggedIn(true);
    }
  }, []);

  if (!isLoggedIn) {
    return <LoginGestioneRiservata onLogin={() => setIsLoggedIn(true)} />;
  }

  return <DashboardGestioneRiservata onLogout={() => setIsLoggedIn(false)} />;
}
