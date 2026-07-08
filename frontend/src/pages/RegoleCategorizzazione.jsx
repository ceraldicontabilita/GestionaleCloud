import React, { useState, useEffect, useCallback } from 'react';
import api from '../api';
import { COLORS, BORDER_RADIUS, FONT } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import {
  Button,
  Badge,
  StatCard,
  Input,
  Select,
  Tabs,
  TableWrap,
  Table,
  Th,
  Td,
} from '../components/ds';

// Palette categoriale dedicata: 12 categorie contabili devono restare
// distinguibili a colpo d'occhio. Non è mappabile sui token di stato
// (success/danger/warning/info) senza far collassare più categorie sullo
// stesso colore, quindi resta una palette custom di dominio (non chrome UI).
const CATEGORIA_COLORS = {
  acquisti_merci: { bg: '#dbeafe', text: '#1e40af', label: 'Acquisti Merci' },
  acquisti_servizi: { bg: '#fef3c7', text: '#92400e', label: 'Servizi' },
  utenze: { bg: '#fce7f3', text: '#9d174d', label: 'Utenze' },
  affitti: { bg: '#d1fae5', text: '#065f46', label: 'Affitti' },
  assicurazioni: { bg: '#e0e7ff', text: '#3730a3', label: 'Assicurazioni' },
  manutenzioni: { bg: '#fed7aa', text: '#9a3412', label: 'Manutenzioni' },
  consulenze: { bg: '#f5d0fe', text: '#86198f', label: 'Consulenze' },
  trasporti: { bg: '#a5f3fc', text: '#0e7490', label: 'Trasporti' },
  noleggi: { bg: '#fda4af', text: '#9f1239', label: 'Noleggi' },
  telefonia: { bg: '#c4b5fd', text: '#5b21b6', label: 'Telefonia' },
  pubblicita: { bg: '#fde68a', text: '#92400e', label: 'Pubblicità' },
  non_categorizzato: { bg: COLORS.gray[100], text: COLORS.gray[700], label: 'Non Categorizzato' },
};

export default function RegoleCategorizzazione() {
  const [regole, setRegole] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState(null);
  const [activeTab, setActiveTab] = useState('associazioni');
  const [searchTerm, setSearchTerm] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);
  const [newRule, setNewRule] = useState({ pattern: '', categoria: '', note: '' });
  const [editingCategoria, setEditingCategoria] = useState(null);
  const [ricategorizzando, setRicategorizzando] = useState(false);

  const fetchRegole = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/regole');
      setRegole(res.data);
    } catch (err) {
      console.error('Errore caricamento regole:', err);
      setMessage({ type: 'error', text: 'Errore nel caricamento delle regole' });
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchRegole();
  }, [fetchRegole]);

  const handleDownloadExcel = async () => {
    try {
      const res = await api.get('/api/regole/download-regole', { responseType: 'blob' });
      const url = window.URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'regole_categorizzazione.xlsx';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setMessage({ type: 'success', text: '✅ File Excel scaricato!' });
    } catch (err) {
      setMessage({ type: 'error', text: '❌ Errore nel download' });
    }
  };

  const handleUploadExcel = async event => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await api.post('/api/regole/upload-regole', formData);
      if (res.data.success) {
        setMessage({
          type: 'success',
          text: `✅ Caricate: ${res.data.regole_fornitori_caricate} fornitori, ${res.data.regole_descrizioni_caricate} descrizioni`,
        });
        fetchRegole();
      }
    } catch (err) {
      setMessage({ type: 'error', text: '❌ Errore nel caricamento' });
    }
    setUploading(false);
    event.target.value = '';
  };

  const handleAddRule = async () => {
    if (!newRule.pattern || !newRule.categoria) {
      setMessage({ type: 'error', text: '⚠️ Pattern e categoria sono obbligatori' });
      return;
    }
    try {
      const res = await api.post('/api/regole/fornitore', newRule);
      if (res.data.success) {
        setMessage({ type: 'success', text: '✅ Regola aggiunta!' });
        setShowAddForm(false);
        setNewRule({ pattern: '', categoria: '', note: '' });
        fetchRegole();
      } else {
        setMessage({ type: 'error', text: "❌ Aggiunta non riuscita: " + (res.data.message || 'errore sconosciuto') });
      }
    } catch (err) {
      setMessage({ type: 'error', text: "❌ Errore nell'aggiunta della regola" });
    }
  };

  const handleDeleteRule = async (tipo, pattern) => {
    try {
      await api.delete(`/api/regole/elimina/${tipo}/${encodeURIComponent(pattern)}`);
      setMessage({ type: 'success', text: '✅ Regola eliminata!' });
      fetchRegole();
    } catch (err) {
      setMessage({ type: 'error', text: "❌ Errore nell'eliminazione" });
    }
  };

  const handleRicategorizza = async () => {
    setRicategorizzando(true);
    try {
      const res = await api.post('/api/contabilita/ricategorizza-fatture');
      const nErrori = (res.data.errori || []).length;
      if (res.data.success) {
        setMessage({
          type: nErrori > 0 ? 'error' : 'success',
          text:
            `✅ Ricategorizzate ${res.data.fatture_processate} fatture!` +
            (nErrori > 0
              ? ` ⚠️ ${nErrori} con errori: ${res.data.errori.slice(0, 3).join('; ')}${nErrori > 3 ? '…' : ''}`
              : ''),
        });
      } else {
        setMessage({ type: 'error', text: '❌ Ricategorizzazione non riuscita' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: '❌ Errore nella ricategorizzazione' });
    }
    setRicategorizzando(false);
  };

  const filteredRules = rules => {
    if (!searchTerm) return rules || [];
    const term = searchTerm.toLowerCase();
    return (rules || []).filter(
      r => r.pattern?.toLowerCase().includes(term) || r.categoria?.toLowerCase().includes(term)
    );
  };

  const getAssociazioni = () => {
    const assoc = {};
    (regole?.regole_fornitori || []).forEach(r => {
      const cat = r.categoria || 'non_categorizzato';
      if (!assoc[cat]) assoc[cat] = { fornitori: [], descrizioni: [] };
      assoc[cat].fornitori.push(r);
    });
    (regole?.regole_descrizioni || []).forEach(r => {
      const cat = r.categoria || 'non_categorizzato';
      if (!assoc[cat]) assoc[cat] = { fornitori: [], descrizioni: [] };
      assoc[cat].descrizioni.push(r);
    });
    return assoc;
  };

  const getCategoryStyle = catName => {
    return CATEGORIA_COLORS[catName] || CATEGORIA_COLORS.non_categorizzato;
  };

  const formatCategoryName = name => {
    return (name || '').replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
  };

  if (loading) {
    return (
      <div style={{ padding: 24, textAlign: 'center', paddingTop: 100 }}>
        <div style={{ fontSize: 32, marginBottom: 16 }}>⏳</div>
        <div style={{ color: COLORS.textMuted }}>Caricamento regole...</div>
      </div>
    );
  }

  const associazioni = getAssociazioni();
  const totaleRegole =
    (regole?.regole_fornitori?.length || 0) + (regole?.regole_descrizioni?.length || 0);
  const totaleCategorie = Object.keys(associazioni).length;

  return (
    <PageLayout
      title="Regole di Categorizzazione"
      subtitle="Associazioni Fornitore/Descrizione → Categoria Contabile"
    >
      <div data-testid="regole-categorizzazione-page">
        {/* Header */}
        <div style={{ marginBottom: 24 }}>
          <h1
            style={{
              fontSize: 28,
              fontWeight: 700,
              color: COLORS.primaryLight,
              marginBottom: 8,
              display: 'flex',
              alignItems: 'center',
              gap: 10,
            }}
          >
            <span>⚙️</span> Regole di Categorizzazione
          </h1>
          <p style={{ color: COLORS.textMuted }}>
            Associazioni Fornitore/Descrizione → Categoria Contabile
          </p>
        </div>

        {/* Messaggio */}
        {message && (
          <div
            style={{
              padding: 16,
              borderRadius: BORDER_RADIUS.md,
              marginBottom: 20,
              background:
                message.type === 'success'
                  ? COLORS.successLight
                  : message.type === 'error'
                    ? COLORS.dangerLight
                    : COLORS.infoLight,
              color:
                message.type === 'success'
                  ? COLORS.success
                  : message.type === 'error'
                    ? COLORS.danger
                    : COLORS.info,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            {message.text}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setMessage(null)}
              style={{ fontSize: 18, padding: '2px 8px', color: 'inherit' }}
            >
              ✕
            </Button>
          </div>
        )}

        {/* Statistiche */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
            gap: 12,
            marginBottom: 24,
          }}
        >
          <StatCard label="Regole Fornitori" value={regole?.regole_fornitori?.length || 0} accent="info" icon="🏢" />
          <StatCard label="Regole Descrizioni" value={regole?.regole_descrizioni?.length || 0} accent="accent" icon="📝" />
          <StatCard label="Categorie" value={totaleCategorie} accent="success" icon="📁" />
          <StatCard label="Totale Regole" value={totaleRegole} accent="warning" icon="📊" />
        </div>

        {/* Azioni */}
        <div
          style={{
            display: 'flex',
            gap: 12,
            marginBottom: 20,
            flexWrap: 'wrap',
            alignItems: 'center',
            padding: 16,
            background: COLORS.bgAlt,
            borderRadius: BORDER_RADIUS.md,
          }}
        >
          <Button variant="success" onClick={handleDownloadExcel} iconLeft="📥">
            Scarica Excel
          </Button>

          {/* Trigger upload file: deve restare un <label> nativo (wrappa l'<input type="file">
              nascosto che apre il file picker) — <Button> renderizza un <button>, non un <label>,
              quindi non può assolvere a questo ruolo. Stile tokenizzato. */}
          <label
            style={{
              padding: '8px 16px',
              background: uploading ? COLORS.gray[400] : COLORS.info,
              color: '#fff',
              borderRadius: BORDER_RADIUS.sm,
              cursor: uploading ? 'wait' : 'pointer',
              fontWeight: 600,
              fontSize: 13,
              fontFamily: FONT.family,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            📤 {uploading ? 'Caricamento...' : 'Carica Excel'}
            <input
              type="file"
              accept=".xlsx,.xls"
              onChange={handleUploadExcel}
              style={{ display: 'none' }}
              disabled={uploading}
            />
          </label>

          <Button variant="info" onClick={handleRicategorizza} disabled={ricategorizzando} iconLeft="🔄">
            {ricategorizzando ? 'Elaborazione...' : 'Applica alle Fatture'}
          </Button>

          <Button variant="warning" onClick={() => setShowAddForm(!showAddForm)} iconLeft="➕">
            Nuova Regola
          </Button>
        </div>

        {/* Form Nuova Regola */}
        {showAddForm && (
          <div
            style={{
              background: COLORS.card,
              border: `1px solid ${COLORS.border}`,
              borderRadius: BORDER_RADIUS.md,
              padding: 20,
              marginBottom: 20,
            }}
          >
            <h3 style={{ marginTop: 0, marginBottom: 16 }}>➕ Aggiungi Nuova Regola</h3>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <Input
                type="text"
                placeholder="Pattern fornitore (es. ENEL)"
                value={newRule.pattern}
                onChange={e => setNewRule({ ...newRule, pattern: e.target.value })}
                style={{ flex: 1, minWidth: 200 }}
              />
              <Select
                value={newRule.categoria}
                onChange={e => setNewRule({ ...newRule, categoria: e.target.value })}
                style={{ minWidth: 180 }}
              >
                <option value="">-- Seleziona Categoria --</option>
                {Object.keys(CATEGORIA_COLORS).map(cat => (
                  <option key={cat} value={cat}>
                    {formatCategoryName(cat)}
                  </option>
                ))}
              </Select>
              <Button variant="success" onClick={handleAddRule} iconLeft="✅">
                Salva
              </Button>
              <Button variant="secondary" onClick={() => setShowAddForm(false)} iconLeft="✕">
                Annulla
              </Button>
            </div>
          </div>
        )}

        {/* Filtri e Ricerca */}
        <div
          style={{
            display: 'flex',
            gap: 12,
            marginBottom: 20,
            alignItems: 'center',
            flexWrap: 'wrap',
          }}
        >
          <Input
            type="text"
            placeholder="🔍 Cerca regola..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            style={{ minWidth: 250 }}
          />

          <Tabs
            items={[
              { key: 'associazioni', label: 'Associazioni' },
              { key: 'fornitori', label: 'Fornitori' },
              { key: 'descrizioni', label: 'Descrizioni' },
              { key: 'categorie', label: 'Categorie' },
            ]}
            value={activeTab}
            onChange={setActiveTab}
          />
        </div>

        {/* Tab Content */}
        <div
          style={{
            background: COLORS.card,
            borderRadius: BORDER_RADIUS.md,
            border: `1px solid ${COLORS.border}`,
            overflow: 'hidden',
          }}
        >
          {/* Tab Associazioni */}
          {activeTab === 'associazioni' && (
            <div style={{ padding: 20 }}>
              <div style={{ display: 'grid', gap: 16 }}>
                {Object.entries(associazioni).map(([categoria, data]) => {
                  const style = getCategoryStyle(categoria);
                  return (
                    <div
                      key={categoria}
                      style={{ border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.md, overflow: 'hidden' }}
                    >
                      <div
                        style={{
                          padding: '12px 16px',
                          background: style.bg,
                          borderBottom: `1px solid ${COLORS.border}`,
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                        }}
                      >
                        <span style={{ fontWeight: 600, color: style.text }}>
                          {formatCategoryName(categoria)}
                        </span>
                        <span style={{ fontSize: 12, color: style.text }}>
                          {data.fornitori.length} fornitori, {data.descrizioni.length} descrizioni
                        </span>
                      </div>
                      <div style={{ padding: 12 }}>
                        {data.fornitori.length > 0 && (
                          <div style={{ marginBottom: 8 }}>
                            <span
                              style={{ fontSize: 11, color: COLORS.textMuted, textTransform: 'uppercase' }}
                            >
                              Fornitori:
                            </span>
                            <div
                              style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}
                            >
                              {data.fornitori.map((r, i) => (
                                <span
                                  key={i}
                                  style={{
                                    padding: '4px 10px',
                                    background: COLORS.bgAlt,
                                    borderRadius: BORDER_RADIUS.sm,
                                    fontSize: 13,
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: 6,
                                  }}
                                >
                                  {r.pattern}
                                  <button
                                    onClick={() => handleDeleteRule('fornitore', r.pattern)}
                                    style={{
                                      background: 'none',
                                      border: 'none',
                                      cursor: 'pointer',
                                      color: COLORS.danger,
                                      padding: 0,
                                    }}
                                  >
                                    ✕
                                  </button>
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                        {data.descrizioni.length > 0 && (
                          <div>
                            <span
                              style={{ fontSize: 11, color: COLORS.textMuted, textTransform: 'uppercase' }}
                            >
                              Descrizioni:
                            </span>
                            <div
                              style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}
                            >
                              {data.descrizioni.map((r, i) => (
                                <span
                                  key={i}
                                  style={{
                                    padding: '4px 10px',
                                    background: COLORS.infoLight,
                                    borderRadius: BORDER_RADIUS.sm,
                                    fontSize: 13,
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: 6,
                                  }}
                                >
                                  {r.pattern}
                                  <button
                                    onClick={() => handleDeleteRule('descrizione', r.pattern)}
                                    style={{
                                      background: 'none',
                                      border: 'none',
                                      cursor: 'pointer',
                                      color: COLORS.danger,
                                      padding: 0,
                                    }}
                                  >
                                    ✕
                                  </button>
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Tab Fornitori */}
          {activeTab === 'fornitori' && (
            <TableWrap style={{ border: 'none', borderRadius: 0 }}>
              <Table>
                <thead>
                  <tr>
                    <Th>Pattern</Th>
                    <Th>Categoria</Th>
                    <Th align="center">Azioni</Th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRules(regole?.regole_fornitori).map((r, i) => {
                    const style = getCategoryStyle(r.categoria);
                    return (
                      <tr key={i}>
                        <Td style={{ fontWeight: 500 }}>{r.pattern}</Td>
                        <Td>
                          <Badge style={{ background: style.bg, color: style.text }}>
                            {formatCategoryName(r.categoria)}
                          </Badge>
                        </Td>
                        <Td align="center">
                          <Button
                            variant="danger"
                            size="sm"
                            onClick={() => handleDeleteRule('fornitore', r.pattern)}
                            iconLeft="🗑️"
                          >
                            Elimina
                          </Button>
                        </Td>
                      </tr>
                    );
                  })}
                </tbody>
              </Table>
            </TableWrap>
          )}

          {/* Tab Descrizioni */}
          {activeTab === 'descrizioni' && (
            <TableWrap style={{ border: 'none', borderRadius: 0 }}>
              <Table>
                <thead>
                  <tr>
                    <Th>Pattern</Th>
                    <Th>Categoria</Th>
                    <Th align="center">Azioni</Th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRules(regole?.regole_descrizioni).map((r, i) => {
                    const style = getCategoryStyle(r.categoria);
                    return (
                      <tr key={i}>
                        <Td style={{ fontWeight: 500 }}>{r.pattern}</Td>
                        <Td>
                          <Badge style={{ background: style.bg, color: style.text }}>
                            {formatCategoryName(r.categoria)}
                          </Badge>
                        </Td>
                        <Td align="center">
                          <Button
                            variant="danger"
                            size="sm"
                            onClick={() => handleDeleteRule('descrizione', r.pattern)}
                            iconLeft="🗑️"
                          >
                            Elimina
                          </Button>
                        </Td>
                      </tr>
                    );
                  })}
                </tbody>
              </Table>
            </TableWrap>
          )}

          {/* Tab Categorie */}
          {activeTab === 'categorie' && (
            <div style={{ padding: 20 }}>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                  gap: 12,
                }}
              >
                {(regole?.categorie || []).map((cat, i) => {
                  const style = getCategoryStyle(cat.categoria);
                  return (
                    <div
                      key={i}
                      style={{
                        background: style.bg,
                        borderRadius: BORDER_RADIUS.md,
                        padding: 16,
                        border: `1px solid ${style.text}20`,
                      }}
                    >
                      <div style={{ fontWeight: 600, color: style.text, marginBottom: 8 }}>
                        {formatCategoryName(cat.categoria)}
                      </div>
                      <div style={{ fontSize: 12, color: style.text, opacity: 0.8 }}>
                        <div>Conto: {cat.conto || '-'}</div>
                        <div>Ded. IRES: {cat.deducibilita_ires || 100}%</div>
                        <div>Ded. IRAP: {cat.deducibilita_irap || 100}%</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Info Box */}
        <div
          style={{
            background: COLORS.infoLight,
            border: `1px solid ${COLORS.info}40`,
            borderRadius: BORDER_RADIUS.md,
            padding: 16,
            marginTop: 24,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <span>ℹ️</span>
            <strong style={{ color: COLORS.info }}>Come funziona</strong>
          </div>
          <ul style={{ margin: 0, paddingLeft: 20, color: COLORS.info, fontSize: 13 }}>
            <li>
              <strong>Regole Fornitori:</strong> Associa un fornitore ad una categoria (es. "ENEL" →
              "utenze")
            </li>
            <li>
              <strong>Regole Descrizioni:</strong> Associa una descrizione prodotto ad una categoria
            </li>
            <li>
              <strong>Applica alle Fatture:</strong> Ricategorizza tutte le fatture esistenti con le
              nuove regole
            </li>
          </ul>
        </div>
      </div>
    </PageLayout>
  );
}
