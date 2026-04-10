import React, { useState, useEffect } from 'react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, useIsMobile } from '../lib/utils';
import { PageLayout, PageSection, PageGrid, PageLoading } from '../components/PageLayout';
import { 
  BarChart3, Plus, Trash2, Save, Copy, Download, RefreshCw,
  TrendingUp, TrendingDown, Target, X, Edit2
} from 'lucide-react';

const NOMI_MESI = ['', 'Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic'];

export default function BudgetPrevisionale() {
  const isMobile = useIsMobile();
  const { anno } = useAnnoGlobale();
  const [activeTab, setActiveTab] = useState('budget');
  const [budget, setBudget] = useState(null);
  const [confronto, setConfronto] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [formVoce, setFormVoce] = useState('');
  const [formCategoria, setFormCategoria] = useState('costo');
  const [formImporto, setFormImporto] = useState('');
  const [formNote, setFormNote] = useState('');
  const [formMensili, setFormMensili] = useState({});
  const [editingVoce, setEditingVoce] = useState(null);
  const [showDuplica, setShowDuplica] = useState(false);
  const [annoDestinazione, setAnnoDestinazione] = useState(anno + 1);
  const [variazionePct, setVariazionePct] = useState(0);
  const [meseConfronto, setMeseConfronto] = useState(null);

  useEffect(() => { loadAll(); }, [anno]);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [budgetRes, confRes] = await Promise.all([
        api.get(`/api/contabilita-gestionale/budget/${anno}`),
        api.get(`/api/contabilita-gestionale/budget-vs-consuntivo/${anno}`)
      ]);
      setBudget(budgetRes.data);
      setConfronto(confRes.data);
    } catch (err) {
      console.error('Errore budget:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadConfronto = async (mese) => {
    try {
      const url = mese
        ? `/api/contabilita-gestionale/budget-vs-consuntivo/${anno}?mese=${mese}`
        : `/api/contabilita-gestionale/budget-vs-consuntivo/${anno}`;
      const res = await api.get(url);
      setConfronto(res.data);
    } catch (err) {
      console.error('Errore confronto:', err);
    }
  };

  const handleMeseChange = (m) => {
    const val = m ? parseInt(m) : null;
    setMeseConfronto(val);
    loadConfronto(val);
  };

  const resetForm = () => {
    setFormVoce(''); setFormCategoria('costo'); setFormImporto(''); setFormNote(''); setFormMensili({});
    setEditingVoce(null); setShowForm(false);
  };

  const startEdit = (voce) => {
    setFormVoce(voce.voce);
    setFormCategoria(voce.categoria);
    setFormImporto(voce.importo_annuale.toString());
    setFormNote(voce.note || '');
    setFormMensili(voce.mensile || {});
    setEditingVoce(voce.voce);
    setShowForm(true);
  };

  const handleSave = async () => {
    if (!formVoce.trim() || !formImporto) return;
    setSaving(true);
    try {
      await api.post('/api/contabilita-gestionale/budget', {
        anno, voce: formVoce.trim(), categoria: formCategoria,
        importo_annuale: parseFloat(formImporto) || 0, note: formNote, mensile: formMensili
      });
      resetForm();
      loadAll();
    } catch (err) {
      alert('Errore: ' + (err.response?.data?.error || err.message));
    } finally { setSaving(false); }
  };

  const handleDelete = async (voce) => {
    if (!confirm(`Eliminare "${voce}" dal budget ${anno}?`)) return;
    try {
      await api.delete(`/api/contabilita-gestionale/budget/${anno}/${encodeURIComponent(voce)}`);
      loadAll();
    } catch (err) { alert('Errore: ' + err.message); }
  };

  const handleDuplica = async () => {
    setSaving(true);
    try {
      const res = await api.post(`/api/contabilita-gestionale/budget/duplica/${anno}/${annoDestinazione}?variazione_pct=${variazionePct}`);
      alert(res.data.messaggio);
      setShowDuplica(false);
    } catch (err) { alert('Errore: ' + err.message); }
    finally { setSaving(false); }
  };

  const distribuisciUniforme = () => {
    const importo = parseFloat(formImporto) || 0;
    const mensile = Math.round(importo / 12 * 100) / 100;
    const m = {};
    for (let i = 1; i <= 11; i++) m[i] = mensile;
    m[12] = Math.round((importo - mensile * 11) * 100) / 100;
    setFormMensili(m);
  };

  const exportCSV = () => {
    if (!budget?.voci) return;
    const rows = [['Voce', 'Categoria', 'Importo Annuale', ...NOMI_MESI.slice(1), 'Note'].join(';')];
    for (const v of budget.voci) {
      const mensili = NOMI_MESI.slice(1).map((_, i) => (v.mensile?.[i + 1] || 0).toFixed(2));
      rows.push([`"${v.voce}"`, v.categoria, v.importo_annuale.toFixed(2), ...mensili, `"${v.note || ''}"`].join(';'));
    }
    const blob = new Blob(['\uFEFF' + rows.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = `budget-${anno}.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  const getValBadge = (val) => {
    if (val === 'positivo') return { bg: '#dcfce7', color: '#16a34a', icon: '✓' };
    return { bg: '#fee2e2', color: '#dc2626', icon: '✗' };
  };

  // ---- RENDER ----
  return (
    <PageLayout
      title="Budget e Previsionale"
      icon={<BarChart3 size={28} />}
      subtitle={`Budget annuale, distribuzione mensile e confronto con consuntivo – Anno ${anno}`}
      actions={
        <button onClick={loadAll} disabled={loading}
          style={{ padding: '8px 16px', borderRadius: 8, border: '1px solid #e2e8f0', background: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 500 }}>
          <RefreshCw size={14} /> Aggiorna
        </button>
      }
    >
      {/* Tabs */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 24, borderBottom: '2px solid #e2e8f0' }}>
        {[
          { id: 'budget', label: 'Budget', icon: <BarChart3 size={16} /> },
          { id: 'confronto', label: 'Budget vs Consuntivo', icon: <Target size={16} /> },
          { id: 'andamento', label: 'Andamento Mensile', icon: <TrendingUp size={16} /> }
        ].map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '14px 24px', border: 'none',
              background: activeTab === tab.id ? '#1e293b' : 'transparent',
              color: activeTab === tab.id ? 'white' : '#64748b',
              fontSize: 14, fontWeight: 600, cursor: 'pointer', borderRadius: '8px 8px 0 0',
              display: 'flex', alignItems: 'center', gap: 8
            }}>
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>

      {loading ? (
        <PageLoading message="Caricamento budget..." />
      ) : (
        <>
          {/* ==================== TAB BUDGET ==================== */}
          {activeTab === 'budget' && (
            <>
              {/* Summary Cards */}
              {budget?.totali && (
                <PageGrid cols={4} gap={16}>
                  <div style={{ background: '#f0fdf4', padding: 16, borderRadius: 12, textAlign: 'center' }}>
                    <div style={{ fontSize: 12, color: '#059669', fontWeight: 600 }}>RICAVI BUDGET</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: '#059669', marginTop: 4 }}>{formatEuro(budget.totali.ricavi_budget)}</div>
                  </div>
                  <div style={{ background: '#fef2f2', padding: 16, borderRadius: 12, textAlign: 'center' }}>
                    <div style={{ fontSize: 12, color: '#dc2626', fontWeight: 600 }}>COSTI BUDGET</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: '#dc2626', marginTop: 4 }}>{formatEuro(budget.totali.costi_budget)}</div>
                  </div>
                  <div style={{ background: budget.totali.margine_budget >= 0 ? '#ecfdf5' : '#fef2f2', padding: 16, borderRadius: 12, textAlign: 'center', border: `2px solid ${budget.totali.margine_budget >= 0 ? '#22c55e' : '#ef4444'}` }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: budget.totali.margine_budget >= 0 ? '#059669' : '#dc2626' }}>MARGINE</div>
                    <div style={{ fontSize: 20, fontWeight: 700, marginTop: 4, color: budget.totali.margine_budget >= 0 ? '#059669' : '#dc2626' }}>{formatEuro(budget.totali.margine_budget)}</div>
                  </div>
                  <div style={{ background: '#f8fafc', padding: 16, borderRadius: 12, textAlign: 'center' }}>
                    <div style={{ fontSize: 12, color: '#475569', fontWeight: 600 }}>MARGINE %</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: '#1e293b', marginTop: 4 }}>{budget.totali.margine_pct}%</div>
                  </div>
                </PageGrid>
              )}

              {/* Actions */}
              <div style={{ display: 'flex', gap: 8, margin: '20px 0', flexWrap: 'wrap' }}>
                <button onClick={() => { resetForm(); setShowForm(true); }}
                  style={{ padding: '8px 16px', borderRadius: 8, border: 'none', background: '#059669', color: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 600 }}>
                  <Plus size={14} /> Nuova Voce
                </button>
                <button onClick={() => setShowDuplica(true)}
                  style={{ padding: '8px 16px', borderRadius: 8, border: '1px solid #e2e8f0', background: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 500 }}>
                  <Copy size={14} /> Duplica Anno
                </button>
                <button onClick={exportCSV}
                  style={{ padding: '8px 16px', borderRadius: 8, border: 'none', background: '#1e3a5f', color: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 600 }}>
                  <Download size={14} /> CSV
                </button>
              </div>

              {/* Form */}
              {showForm && (
                <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 12, padding: 20, marginBottom: 20 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
                    <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>{editingVoce ? `Modifica: ${editingVoce}` : 'Nuova voce di budget'}</h3>
                    <button onClick={resetForm} style={{ background: 'none', border: 'none', cursor: 'pointer' }}><X size={20} /></button>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 2fr', gap: 12, marginBottom: 16 }}>
                    <div>
                      <label style={{ fontSize: 12, fontWeight: 500, color: '#475569', display: 'block', marginBottom: 4 }}>Voce</label>
                      <input value={formVoce} onChange={e => setFormVoce(e.target.value)} disabled={!!editingVoce} placeholder="es. Materie prime"
                        style={{ width: '100%', padding: '8px 12px', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 14 }} />
                    </div>
                    <div>
                      <label style={{ fontSize: 12, fontWeight: 500, color: '#475569', display: 'block', marginBottom: 4 }}>Categoria</label>
                      <select value={formCategoria} onChange={e => setFormCategoria(e.target.value)}
                        style={{ width: '100%', padding: '8px 12px', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 14 }}>
                        <option value="costo">Costo</option>
                        <option value="ricavo">Ricavo</option>
                      </select>
                    </div>
                    <div>
                      <label style={{ fontSize: 12, fontWeight: 500, color: '#475569', display: 'block', marginBottom: 4 }}>Importo annuo €</label>
                      <input type="number" value={formImporto} onChange={e => setFormImporto(e.target.value)}
                        style={{ width: '100%', padding: '8px 12px', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 14 }} />
                    </div>
                    <div>
                      <label style={{ fontSize: 12, fontWeight: 500, color: '#475569', display: 'block', marginBottom: 4 }}>Note</label>
                      <input value={formNote} onChange={e => setFormNote(e.target.value)}
                        style={{ width: '100%', padding: '8px 12px', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 14 }} />
                    </div>
                  </div>
                  <div style={{ marginBottom: 16 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                      <span style={{ fontSize: 12, fontWeight: 600, color: '#475569' }}>Mensile</span>
                      <button onClick={distribuisciUniforme}
                        style={{ fontSize: 11, padding: '2px 8px', border: '1px solid #cbd5e1', borderRadius: 4, background: 'white', cursor: 'pointer' }}>
                        Distribuisci uniforme
                      </button>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: 4 }}>
                      {NOMI_MESI.slice(1).map((nome, i) => (
                        <div key={i}>
                          <label style={{ fontSize: 10, color: '#94a3b8', display: 'block', textAlign: 'center' }}>{nome}</label>
                          <input type="number" value={formMensili[i + 1] || ''} onChange={e => setFormMensili(p => ({ ...p, [i + 1]: parseFloat(e.target.value) || 0 }))}
                            style={{ width: '100%', padding: '4px', border: '1px solid #e2e8f0', borderRadius: 4, fontSize: 11, textAlign: 'center' }} />
                        </div>
                      ))}
                    </div>
                  </div>
                  <button onClick={handleSave} disabled={saving || !formVoce.trim() || !formImporto}
                    style={{ padding: '10px 24px', borderRadius: 8, border: 'none', background: '#059669', color: 'white', cursor: 'pointer', fontSize: 14, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Save size={16} /> {saving ? 'Salvataggio...' : (editingVoce ? 'Aggiorna' : 'Salva')}
                  </button>
                </div>
              )}

              {/* Duplica */}
              {showDuplica && (
                <div style={{ background: '#fffbeb', border: '1px solid #fbbf24', borderRadius: 12, padding: 20, marginBottom: 20 }}>
                  <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 600 }}>Duplica Budget {anno} →</h3>
                  <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
                    <div>
                      <label style={{ fontSize: 12, fontWeight: 500, display: 'block', marginBottom: 4 }}>Anno dest.</label>
                      <input type="number" value={annoDestinazione} onChange={e => setAnnoDestinazione(parseInt(e.target.value))}
                        style={{ padding: '8px 12px', border: '1px solid #e2e8f0', borderRadius: 8, width: 100 }} />
                    </div>
                    <div>
                      <label style={{ fontSize: 12, fontWeight: 500, display: 'block', marginBottom: 4 }}>Variazione %</label>
                      <input type="number" value={variazionePct} onChange={e => setVariazionePct(parseFloat(e.target.value) || 0)}
                        style={{ padding: '8px 12px', border: '1px solid #e2e8f0', borderRadius: 8, width: 100 }} />
                    </div>
                    <button onClick={handleDuplica} disabled={saving}
                      style={{ padding: '8px 16px', borderRadius: 8, border: 'none', background: '#d97706', color: 'white', cursor: 'pointer', fontSize: 13, fontWeight: 600 }}>
                      Duplica
                    </button>
                    <button onClick={() => setShowDuplica(false)}
                      style={{ padding: '8px 16px', borderRadius: 8, border: '1px solid #e2e8f0', background: 'white', cursor: 'pointer', fontSize: 13 }}>
                      Annulla
                    </button>
                  </div>
                </div>
              )}

              {/* Tabella Budget */}
              {budget?.voci?.length > 0 ? (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead>
                      <tr style={{ background: '#1e293b', color: 'white' }}>
                        <th style={{ padding: '10px 8px', textAlign: 'left' }}>Voce</th>
                        <th style={{ padding: '10px 8px', textAlign: 'center', width: 70 }}>Tipo</th>
                        <th style={{ padding: '10px 8px', textAlign: 'right', width: 110 }}>Annuale</th>
                        {NOMI_MESI.slice(1).map((m, i) => (
                          <th key={i} style={{ padding: '10px 2px', textAlign: 'right', width: 65, fontSize: 11 }}>{m}</th>
                        ))}
                        <th style={{ padding: '10px 4px', width: 70 }}></th>
                      </tr>
                    </thead>
                    <tbody>
                      {budget.voci.map((v, idx) => {
                        const isR = v.categoria === 'ricavo';
                        return (
                          <tr key={v.voce} style={{ background: idx % 2 === 0 ? 'white' : '#fafafa', borderBottom: '1px solid #f1f5f9' }}>
                            <td style={{ padding: '8px', fontWeight: 500 }}>{v.voce}</td>
                            <td style={{ padding: '8px', textAlign: 'center' }}>
                              <span style={{ padding: '2px 6px', borderRadius: 8, fontSize: 10, fontWeight: 600, background: isR ? '#dcfce7' : '#fee2e2', color: isR ? '#16a34a' : '#dc2626' }}>
                                {isR ? 'RIC' : 'COSTO'}
                              </span>
                            </td>
                            <td style={{ padding: '8px', textAlign: 'right', fontWeight: 700, color: isR ? '#059669' : '#dc2626' }}>
                              {formatEuro(v.importo_annuale)}
                            </td>
                            {NOMI_MESI.slice(1).map((_, i) => (
                              <td key={i} style={{ padding: '8px 2px', textAlign: 'right', fontSize: 11, color: '#64748b' }}>
                                {v.mensile?.[i + 1] ? formatEuro(v.mensile[i + 1]) : '-'}
                              </td>
                            ))}
                            <td style={{ padding: '8px 4px', textAlign: 'center' }}>
                              <button onClick={() => startEdit(v)} style={{ background: 'none', border: 'none', cursor: 'pointer', marginRight: 4 }} title="Modifica">
                                <Edit2 size={14} color="#6b7280" />
                              </button>
                              <button onClick={() => handleDelete(v.voce)} style={{ background: 'none', border: 'none', cursor: 'pointer' }} title="Elimina">
                                <Trash2 size={14} color="#ef4444" />
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                    <tfoot>
                      <tr style={{ background: '#1e293b', color: 'white', fontWeight: 700 }}>
                        <td colSpan={2} style={{ padding: '12px 8px' }}>TOTALI</td>
                        <td style={{ padding: '12px 8px', textAlign: 'right' }}>{formatEuro(budget.totali.ricavi_budget - budget.totali.costi_budget)}</td>
                        <td colSpan={13}></td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              ) : (
                <div style={{ textAlign: 'center', padding: 60, color: '#64748b' }}>
                  <BarChart3 size={48} style={{ margin: '0 auto 16px', opacity: 0.3 }} />
                  <p>Nessuna voce di budget per {anno}</p>
                  <p style={{ fontSize: 13 }}>Clicca "Nuova Voce" per iniziare a creare il budget previsionale.</p>
                </div>
              )}
            </>
          )}

          {/* ==================== TAB CONFRONTO ==================== */}
          {activeTab === 'confronto' && confronto && (
            <>
              {/* Filtro mese */}
              <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 20 }}>
                <label style={{ fontSize: 13, fontWeight: 500 }}>Periodo:</label>
                <select value={meseConfronto || ''} onChange={e => handleMeseChange(e.target.value)}
                  style={{ padding: '8px 16px', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 13, fontWeight: 500 }}>
                  <option value="">Anno intero</option>
                  {NOMI_MESI.slice(1).map((m, i) => (
                    <option key={i} value={i + 1}>{m}</option>
                  ))}
                </select>
              </div>

              {/* Summary */}
              {confronto.totali && (
                <PageGrid cols={3} gap={16}>
                  {['ricavi', 'costi', 'margine'].map(key => {
                    const t = confronto.totali[key];
                    const color = key === 'ricavi' ? '#059669' : key === 'costi' ? '#dc2626' : (t.consuntivo >= t.budget ? '#059669' : '#dc2626');
                    return (
                      <div key={key} style={{ background: '#f8fafc', padding: 16, borderRadius: 12, border: '1px solid #e2e8f0' }}>
                        <div style={{ fontSize: 12, fontWeight: 600, color: '#475569', textTransform: 'uppercase', marginBottom: 12 }}>{key}</div>
                        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 8 }}>
                          <div>
                            <div style={{ fontSize: 11, color: '#94a3b8' }}>Budget</div>
                            <div style={{ fontSize: 18, fontWeight: 700, color: '#475569' }}>{formatEuro(t.budget)}</div>
                          </div>
                          <div>
                            <div style={{ fontSize: 11, color: '#94a3b8' }}>Consuntivo</div>
                            <div style={{ fontSize: 18, fontWeight: 700, color }}>{formatEuro(t.consuntivo)}</div>
                          </div>
                        </div>
                        <div style={{ marginTop: 8, padding: '4px 8px', borderRadius: 6, background: t.scostamento >= 0 ? '#dcfce7' : '#fee2e2', textAlign: 'center', fontSize: 13, fontWeight: 600, color: t.scostamento >= 0 ? '#16a34a' : '#dc2626' }}>
                          Scost: {t.scostamento >= 0 ? '+' : ''}{formatEuro(t.scostamento)}
                          {t.scostamento_pct !== undefined && ` (${t.scostamento_pct >= 0 ? '+' : ''}${t.scostamento_pct}%)`}
                        </div>
                      </div>
                    );
                  })}
                </PageGrid>
              )}

              {/* Tabella confronto voci */}
              {confronto.confronto_voci?.length > 0 && (
                <div style={{ overflowX: 'auto', marginTop: 20 }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                    <thead>
                      <tr style={{ background: '#1e293b', color: 'white' }}>
                        <th style={{ padding: '12px 8px', textAlign: 'left' }}>Voce</th>
                        <th style={{ padding: '12px 8px', textAlign: 'center', width: 70 }}>Tipo</th>
                        <th style={{ padding: '12px 8px', textAlign: 'right', width: 120 }}>Budget</th>
                        <th style={{ padding: '12px 8px', textAlign: 'right', width: 120 }}>Consuntivo</th>
                        <th style={{ padding: '12px 8px', textAlign: 'right', width: 120 }}>Scostamento</th>
                        <th style={{ padding: '12px 8px', textAlign: 'center', width: 80 }}>%</th>
                        <th style={{ padding: '12px 8px', textAlign: 'center', width: 80 }}>Esito</th>
                      </tr>
                    </thead>
                    <tbody>
                      {confronto.confronto_voci.map((v, idx) => {
                        const vb = getValBadge(v.valutazione);
                        const isR = v.categoria === 'ricavo';
                        return (
                          <tr key={v.voce} style={{ background: idx % 2 === 0 ? 'white' : '#fafafa', borderBottom: '1px solid #f1f5f9' }}>
                            <td style={{ padding: '10px 8px', fontWeight: 500 }}>{v.voce}</td>
                            <td style={{ padding: '10px 8px', textAlign: 'center' }}>
                              <span style={{ padding: '2px 6px', borderRadius: 8, fontSize: 10, fontWeight: 600, background: isR ? '#dcfce7' : '#fee2e2', color: isR ? '#16a34a' : '#dc2626' }}>
                                {isR ? 'RIC' : 'COSTO'}
                              </span>
                            </td>
                            <td style={{ padding: '10px 8px', textAlign: 'right', color: '#475569' }}>{formatEuro(v.budget)}</td>
                            <td style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 600, color: isR ? '#059669' : '#dc2626' }}>{formatEuro(v.consuntivo)}</td>
                            <td style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 600, color: v.scostamento >= 0 ? '#059669' : '#dc2626' }}>
                              {v.scostamento >= 0 ? '+' : ''}{formatEuro(v.scostamento)}
                            </td>
                            <td style={{ padding: '10px 8px', textAlign: 'center', fontSize: 12, color: v.scostamento_pct >= 0 ? '#059669' : '#dc2626' }}>
                              {v.scostamento_pct >= 0 ? '+' : ''}{v.scostamento_pct}%
                            </td>
                            <td style={{ padding: '10px 8px', textAlign: 'center' }}>
                              <span style={{ padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600, background: vb.bg, color: vb.color }}>
                                {vb.icon}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              {(!confronto.confronto_voci || confronto.confronto_voci.length === 0) && (
                <div style={{ textAlign: 'center', padding: 60, color: '#64748b' }}>
                  <Target size={48} style={{ margin: '0 auto 16px', opacity: 0.3 }} />
                  <p>Nessun confronto disponibile. Crea prima il budget nella tab "Budget".</p>
                </div>
              )}
            </>
          )}

          {/* ==================== TAB ANDAMENTO ==================== */}
          {activeTab === 'andamento' && confronto?.andamento_mensile && (
            <>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: '#1e293b', color: 'white' }}>
                      <th style={{ padding: '12px 8px', textAlign: 'left' }}>Mese</th>
                      <th style={{ padding: '12px 8px', textAlign: 'right' }}>Ricavi Budget</th>
                      <th style={{ padding: '12px 8px', textAlign: 'right' }}>Ricavi Reali</th>
                      <th style={{ padding: '12px 8px', textAlign: 'right' }}>Δ Ricavi</th>
                      <th style={{ padding: '12px 8px', textAlign: 'right', background: '#334155' }}>Costi Budget</th>
                      <th style={{ padding: '12px 8px', textAlign: 'right', background: '#334155' }}>Costi Reali</th>
                      <th style={{ padding: '12px 8px', textAlign: 'right', background: '#334155' }}>Δ Costi</th>
                      <th style={{ padding: '12px 8px', textAlign: 'right' }}>Margine Budget</th>
                      <th style={{ padding: '12px 8px', textAlign: 'right' }}>Margine Reale</th>
                    </tr>
                  </thead>
                  <tbody>
                    {confronto.andamento_mensile.map((m, idx) => {
                      const deltaRic = m.ricavi_consuntivo - m.ricavi_budget;
                      const deltaCosti = m.costi_consuntivo - m.costi_budget;
                      const margineBudget = m.ricavi_budget - m.costi_budget;
                      const margineReale = m.ricavi_consuntivo - m.costi_consuntivo;
                      const hasData = m.ricavi_consuntivo > 0 || m.costi_consuntivo > 0;
                      return (
                        <tr key={m.mese} style={{ background: idx % 2 === 0 ? 'white' : '#fafafa', borderBottom: '1px solid #f1f5f9', opacity: hasData ? 1 : 0.5 }}>
                          <td style={{ padding: '10px 8px', fontWeight: 500 }}>{NOMI_MESI[m.mese]}</td>
                          <td style={{ padding: '10px 8px', textAlign: 'right', color: '#94a3b8' }}>{formatEuro(m.ricavi_budget)}</td>
                          <td style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 600, color: '#059669' }}>{formatEuro(m.ricavi_consuntivo)}</td>
                          <td style={{ padding: '10px 8px', textAlign: 'right', fontSize: 12, color: deltaRic >= 0 ? '#059669' : '#dc2626' }}>
                            {hasData ? `${deltaRic >= 0 ? '+' : ''}${formatEuro(deltaRic)}` : '-'}
                          </td>
                          <td style={{ padding: '10px 8px', textAlign: 'right', color: '#94a3b8', background: '#fafbfc' }}>{formatEuro(m.costi_budget)}</td>
                          <td style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 600, color: '#dc2626', background: '#fafbfc' }}>{formatEuro(m.costi_consuntivo)}</td>
                          <td style={{ padding: '10px 8px', textAlign: 'right', fontSize: 12, background: '#fafbfc', color: deltaCosti <= 0 ? '#059669' : '#dc2626' }}>
                            {hasData ? `${deltaCosti >= 0 ? '+' : ''}${formatEuro(deltaCosti)}` : '-'}
                          </td>
                          <td style={{ padding: '10px 8px', textAlign: 'right', color: '#64748b' }}>{formatEuro(margineBudget)}</td>
                          <td style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 700, color: margineReale >= 0 ? '#059669' : '#dc2626' }}>
                            {hasData ? formatEuro(margineReale) : '-'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                  <tfoot>
                    <tr style={{ background: '#1e293b', color: 'white', fontWeight: 700 }}>
                      <td style={{ padding: '12px 8px' }}>TOTALE</td>
                      <td style={{ padding: '12px 8px', textAlign: 'right' }}>{formatEuro(confronto.andamento_mensile.reduce((s, m) => s + m.ricavi_budget, 0))}</td>
                      <td style={{ padding: '12px 8px', textAlign: 'right' }}>{formatEuro(confronto.andamento_mensile.reduce((s, m) => s + m.ricavi_consuntivo, 0))}</td>
                      <td style={{ padding: '12px 8px' }}></td>
                      <td style={{ padding: '12px 8px', textAlign: 'right' }}>{formatEuro(confronto.andamento_mensile.reduce((s, m) => s + m.costi_budget, 0))}</td>
                      <td style={{ padding: '12px 8px', textAlign: 'right' }}>{formatEuro(confronto.andamento_mensile.reduce((s, m) => s + m.costi_consuntivo, 0))}</td>
                      <td colSpan={3}></td>
                    </tr>
                  </tfoot>
                </table>
              </div>

              {/* Barra grafica semplice */}
              <PageSection title="Grafico Andamento" style={{ marginTop: 24 }}>
                <div style={{ display: 'flex', gap: 4, alignItems: 'flex-end', height: 200, padding: '0 20px' }}>
                  {confronto.andamento_mensile.map(m => {
                    const maxVal = Math.max(...confronto.andamento_mensile.map(x => Math.max(x.ricavi_consuntivo, x.costi_consuntivo, x.ricavi_budget, 1)));
                    const hRicavi = (m.ricavi_consuntivo / maxVal) * 180;
                    const hCosti = (m.costi_consuntivo / maxVal) * 180;
                    return (
                      <div key={m.mese} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
                        <div style={{ display: 'flex', gap: 2, alignItems: 'flex-end', height: 180 }}>
                          <div style={{ width: 12, height: Math.max(hRicavi, 2), background: '#22c55e', borderRadius: '3px 3px 0 0' }} title={`Ricavi: ${formatEuro(m.ricavi_consuntivo)}`} />
                          <div style={{ width: 12, height: Math.max(hCosti, 2), background: '#ef4444', borderRadius: '3px 3px 0 0' }} title={`Costi: ${formatEuro(m.costi_consuntivo)}`} />
                        </div>
                        <span style={{ fontSize: 10, color: '#94a3b8' }}>{NOMI_MESI[m.mese]}</span>
                      </div>
                    );
                  })}
                </div>
                <div style={{ display: 'flex', gap: 16, justifyContent: 'center', marginTop: 12 }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
                    <span style={{ width: 12, height: 12, background: '#22c55e', borderRadius: 2, display: 'inline-block' }} /> Ricavi
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
                    <span style={{ width: 12, height: 12, background: '#ef4444', borderRadius: 2, display: 'inline-block' }} /> Costi
                  </span>
                </div>
              </PageSection>
            </>
          )}
        </>
      )}
    </PageLayout>
  );
}
