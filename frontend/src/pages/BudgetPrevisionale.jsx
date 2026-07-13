import React, { useState, useEffect } from 'react';
import { toast } from 'sonner';
import api from '../api';
import { useConfirm } from '../components/ui/ConfirmDialog';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { COLORS, BORDER_RADIUS, FONT, formatEuro, useIsMobile } from '../lib/utils';
import { PageLayout, PageSection, PageGrid, PageLoading } from '../components/PageLayout';
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
} from '../components/ds';
import {
  BarChart3,
  Plus,
  Trash2,
  Save,
  Copy,
  Download,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Target,
  X,
  Edit2,
} from 'lucide-react';

const NOMI_MESI = [
  '',
  'Gen',
  'Feb',
  'Mar',
  'Apr',
  'Mag',
  'Giu',
  'Lug',
  'Ago',
  'Set',
  'Ott',
  'Nov',
  'Dic',
];

export default function BudgetPrevisionale() {
  const confirm = useConfirm();
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

  useEffect(() => {
    loadAll();
  }, [anno]);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [budgetRes, confRes] = await Promise.all([
        api.get(`/api/contabilita-gestionale/budget/${anno}`),
        api.get(`/api/contabilita-gestionale/budget-vs-consuntivo/${anno}`),
      ]);
      setBudget(budgetRes.data);
      setConfronto(confRes.data);
    } catch (err) {
      console.error('Errore budget:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadConfronto = async mese => {
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

  const handleMeseChange = m => {
    const val = m ? parseInt(m) : null;
    setMeseConfronto(val);
    loadConfronto(val);
  };

  const resetForm = () => {
    setFormVoce('');
    setFormCategoria('costo');
    setFormImporto('');
    setFormNote('');
    setFormMensili({});
    setEditingVoce(null);
    setShowForm(false);
  };

  const startEdit = voce => {
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
        anno,
        voce: formVoce.trim(),
        categoria: formCategoria,
        importo_annuale: parseFloat(formImporto) || 0,
        note: formNote,
        mensile: formMensili,
      });
      resetForm();
      loadAll();
    } catch (err) {
      toast.error('Errore', { description: err.response?.data?.error || err.message });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async voce => {
    // Azione distruttiva/irreversibile: elimina definitivamente la voce di budget.
    if (!(await confirm({ title: 'Elimina voce budget', message: `Eliminare "${voce}" dal budget ${anno}?`, variant: 'danger' }))) return;
    try {
      await api.delete(`/api/contabilita-gestionale/budget/${anno}/${encodeURIComponent(voce)}`);
      loadAll();
    } catch (err) {
      toast.error('Errore', { description: err.message });
    }
  };

  const handleDuplica = async () => {
    setSaving(true);
    try {
      const res = await api.post(
        `/api/contabilita-gestionale/budget/duplica/${anno}/${annoDestinazione}?variazione_pct=${variazionePct}`
      );
      toast.success(res.data.messaggio);
      setShowDuplica(false);
      loadAll();
    } catch (err) {
      toast.error('Errore', { description: err.message });
    } finally {
      setSaving(false);
    }
  };

  const distribuisciUniforme = () => {
    const importo = parseFloat(formImporto) || 0;
    const mensile = Math.round((importo / 12) * 100) / 100;
    const m = {};
    for (let i = 1; i <= 11; i++) m[i] = mensile;
    m[12] = Math.round((importo - mensile * 11) * 100) / 100;
    setFormMensili(m);
  };

  const exportCSV = () => {
    if (!budget?.voci) return;
    const rows = [
      ['Voce', 'Categoria', 'Importo Annuale', ...NOMI_MESI.slice(1), 'Note'].join(';'),
    ];
    for (const v of budget.voci) {
      const mensili = NOMI_MESI.slice(1).map((_, i) => (v.mensile?.[i + 1] || 0).toFixed(2));
      rows.push(
        [
          `"${v.voce}"`,
          v.categoria,
          v.importo_annuale.toFixed(2),
          ...mensili,
          `"${v.note || ''}"`,
        ].join(';')
      );
    }
    const blob = new Blob(['﻿' + rows.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `budget-${anno}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const getValBadge = val => {
    if (val === 'positivo') return { variant: 'success', icon: '✓' };
    return { variant: 'danger', icon: '✗' };
  };

  // ---- RENDER ----
  return (
    <PageLayout
      title="Budget e Previsionale"
      icon={<BarChart3 size={28} />}
      subtitle={`Budget annuale, distribuzione mensile e confronto con consuntivo – Anno ${anno}`}
      actions={
        <Button
          variant="secondary"
          onClick={loadAll}
          disabled={loading}
          iconLeft={<RefreshCw size={14} />}
        >
          Aggiorna
        </Button>
      }
    >
      {/* Tabs */}
      <div style={{ marginBottom: 24 }}>
        <Tabs
          items={[
            { key: 'budget', label: 'Budget', icon: <BarChart3 size={16} /> },
            { key: 'confronto', label: 'Budget vs Consuntivo', icon: <Target size={16} /> },
            { key: 'andamento', label: 'Andamento Mensile', icon: <TrendingUp size={16} /> },
          ]}
          value={activeTab}
          onChange={setActiveTab}
        />
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
                  <StatCard
                    icon={<TrendingUp size={18} />}
                    label="Ricavi Budget"
                    value={formatEuro(budget.totali.ricavi_budget)}
                    accent="success"
                  />
                  <StatCard
                    icon={<TrendingDown size={18} />}
                    label="Costi Budget"
                    value={formatEuro(budget.totali.costi_budget)}
                    accent="danger"
                  />
                  <StatCard
                    icon={<Target size={18} />}
                    label="Margine"
                    value={formatEuro(budget.totali.margine_budget)}
                    accent={budget.totali.margine_budget >= 0 ? 'success' : 'danger'}
                  />
                  <StatCard
                    icon={<BarChart3 size={18} />}
                    label="Margine %"
                    value={`${budget.totali.margine_pct}%`}
                    accent="primary"
                  />
                </PageGrid>
              )}

              {/* Actions */}
              <div style={{ display: 'flex', gap: 8, margin: '20px 0', flexWrap: 'wrap' }}>
                <Button
                  variant="primary"
                  iconLeft={<Plus size={14} />}
                  onClick={() => {
                    resetForm();
                    setShowForm(true);
                  }}
                >
                  Nuova Voce
                </Button>
                <Button
                  variant="secondary"
                  iconLeft={<Copy size={14} />}
                  onClick={() => setShowDuplica(true)}
                >
                  Duplica Anno
                </Button>
                <Button variant="primary" iconLeft={<Download size={14} />} onClick={exportCSV}>
                  CSV
                </Button>
              </div>

              {/* Form */}
              {showForm && (
                <Card
                  title={editingVoce ? `Modifica: ${editingVoce}` : 'Nuova voce di budget'}
                  actions={
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={resetForm}
                      aria-label="Chiudi"
                      style={{ padding: 6 }}
                    >
                      <X size={18} />
                    </Button>
                  }
                  style={{ marginBottom: 20 }}
                  bodyStyle={{ background: COLORS.bgAlt }}
                >
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                      gap: 12,
                      marginBottom: 16,
                    }}
                  >
                    <div>
                      <label
                        style={{
                          fontSize: 12,
                          fontWeight: 500,
                          color: COLORS.gray[600],
                          display: 'block',
                          marginBottom: 4,
                        }}
                      >
                        Voce
                      </label>
                      <Input
                        value={formVoce}
                        onChange={e => setFormVoce(e.target.value)}
                        disabled={!!editingVoce}
                        placeholder="es. Materie prime"
                      />
                    </div>
                    <div>
                      <label
                        style={{
                          fontSize: 12,
                          fontWeight: 500,
                          color: COLORS.gray[600],
                          display: 'block',
                          marginBottom: 4,
                        }}
                      >
                        Categoria
                      </label>
                      <Select value={formCategoria} onChange={e => setFormCategoria(e.target.value)}>
                        <option value="costo">Costo</option>
                        <option value="ricavo">Ricavo</option>
                      </Select>
                    </div>
                    <div>
                      <label
                        style={{
                          fontSize: 12,
                          fontWeight: 500,
                          color: COLORS.gray[600],
                          display: 'block',
                          marginBottom: 4,
                        }}
                      >
                        Importo annuo €
                      </label>
                      <Input
                        type="number"
                        value={formImporto}
                        onChange={e => setFormImporto(e.target.value)}
                      />
                    </div>
                    <div>
                      <label
                        style={{
                          fontSize: 12,
                          fontWeight: 500,
                          color: COLORS.gray[600],
                          display: 'block',
                          marginBottom: 4,
                        }}
                      >
                        Note
                      </label>
                      <Input value={formNote} onChange={e => setFormNote(e.target.value)} />
                    </div>
                  </div>
                  <div style={{ marginBottom: 16 }}>
                    <div
                      style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}
                    >
                      <span style={{ fontSize: 12, fontWeight: 600, color: COLORS.gray[600] }}>
                        Mensile
                      </span>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={distribuisciUniforme}
                        style={{ padding: '2px 8px', fontSize: 11 }}
                      >
                        Distribuisci uniforme
                      </Button>
                    </div>
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(64px, 1fr))',
                        gap: 4,
                      }}
                    >
                      {NOMI_MESI.slice(1).map((nome, i) => (
                        <div key={i}>
                          <label
                            style={{
                              fontSize: 10,
                              color: COLORS.textSubtle,
                              display: 'block',
                              textAlign: 'center',
                            }}
                          >
                            {nome}
                          </label>
                          <Input
                            type="number"
                            value={formMensili[i + 1] || ''}
                            onChange={e =>
                              setFormMensili(p => ({
                                ...p,
                                [i + 1]: parseFloat(e.target.value) || 0,
                              }))
                            }
                            style={{
                              padding: 4,
                              fontSize: 11,
                              textAlign: 'center',
                              fontFamily: FONT.mono,
                            }}
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                  <Button
                    variant="primary"
                    onClick={handleSave}
                    disabled={saving || !formVoce.trim() || !formImporto}
                    iconLeft={<Save size={16} />}
                  >
                    {saving ? 'Salvataggio...' : editingVoce ? 'Aggiorna' : 'Salva'}
                  </Button>
                </Card>
              )}

              {/* Duplica */}
              {showDuplica && (
                <Card
                  title={`Duplica Budget ${anno} →`}
                  style={{ marginBottom: 20, border: `1px solid ${COLORS.warning}` }}
                  bodyStyle={{ background: COLORS.warningLight }}
                >
                  <div
                    style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}
                  >
                    <div>
                      <label
                        style={{ fontSize: 12, fontWeight: 500, display: 'block', marginBottom: 4 }}
                      >
                        Anno dest.
                      </label>
                      <Input
                        type="number"
                        value={annoDestinazione}
                        onChange={e => setAnnoDestinazione(parseInt(e.target.value))}
                        style={{ width: 100, fontFamily: FONT.mono }}
                      />
                    </div>
                    <div>
                      <label
                        style={{ fontSize: 12, fontWeight: 500, display: 'block', marginBottom: 4 }}
                      >
                        Variazione %
                      </label>
                      <Input
                        type="number"
                        value={variazionePct}
                        onChange={e => setVariazionePct(parseFloat(e.target.value) || 0)}
                        style={{ width: 100, fontFamily: FONT.mono }}
                      />
                    </div>
                    <Button variant="primary" onClick={handleDuplica} disabled={saving}>
                      Duplica
                    </Button>
                    <Button variant="secondary" onClick={() => setShowDuplica(false)}>
                      Annulla
                    </Button>
                  </div>
                </Card>
              )}

              {/* Tabella Budget */}
              {budget?.voci?.length > 0 ? (
                <TableWrap>
                  <Table>
                    <thead>
                      <tr>
                        <Th>Voce</Th>
                        <Th align="center" style={{ width: 70 }}>
                          Tipo
                        </Th>
                        <Th align="right" style={{ width: 110 }}>
                          Annuale
                        </Th>
                        {NOMI_MESI.slice(1).map((m, i) => (
                          <Th key={i} align="right" style={{ width: 65, padding: '10px 2px' }}>
                            {m}
                          </Th>
                        ))}
                        <Th style={{ width: 70 }} />
                      </tr>
                    </thead>
                    <tbody>
                      {budget.voci.map((v, idx) => {
                        const isR = v.categoria === 'ricavo';
                        return (
                          <tr
                            key={v.voce}
                            style={{ background: idx % 2 === 0 ? COLORS.card : COLORS.bgAlt }}
                          >
                            <Td style={{ fontWeight: 500 }}>{v.voce}</Td>
                            <Td align="center">
                              <Badge variant={isR ? 'success' : 'danger'}>
                                {isR ? 'RIC' : 'COSTO'}
                              </Badge>
                            </Td>
                            <Td
                              align="right"
                              mono
                              style={{ fontWeight: 700, color: isR ? COLORS.success : COLORS.danger }}
                            >
                              {formatEuro(v.importo_annuale)}
                            </Td>
                            {NOMI_MESI.slice(1).map((_, i) => (
                              <Td
                                key={i}
                                align="right"
                                mono
                                style={{ padding: '8px 2px', fontSize: 11, color: COLORS.textMuted }}
                              >
                                {v.mensile?.[i + 1] ? formatEuro(v.mensile[i + 1]) : '-'}
                              </Td>
                            ))}
                            <Td align="center" style={{ padding: '8px 4px' }}>
                              <RowActions>
                                <RowActionButton
                                  variant="primary"
                                  onClick={() => startEdit(v)}
                                  title="Modifica"
                                >
                                  <Edit2 size={14} />
                                </RowActionButton>
                                <RowActionButton
                                  variant="danger"
                                  onClick={() => handleDelete(v.voce)}
                                  title="Elimina"
                                >
                                  <Trash2 size={14} />
                                </RowActionButton>
                              </RowActions>
                            </Td>
                          </tr>
                        );
                      })}
                    </tbody>
                    <tfoot>
                      <tr style={{ background: COLORS.primary, color: '#fff' }}>
                        <Td colSpan={2} style={{ color: '#fff', fontWeight: 700 }}>
                          TOTALI
                        </Td>
                        <Td align="right" mono style={{ color: '#fff', fontWeight: 700 }}>
                          {formatEuro(budget.totali.ricavi_budget - budget.totali.costi_budget)}
                        </Td>
                        <Td colSpan={13} style={{ color: '#fff' }} />
                      </tr>
                    </tfoot>
                  </Table>
                </TableWrap>
              ) : (
                <div style={{ textAlign: 'center', padding: 60, color: COLORS.textMuted }}>
                  <BarChart3 size={48} style={{ margin: '0 auto 16px', opacity: 0.3 }} />
                  <p>Nessuna voce di budget per {anno}</p>
                  <p style={{ fontSize: 13 }}>
                    Clicca "Nuova Voce" per iniziare a creare il budget previsionale.
                  </p>
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
                <Select value={meseConfronto || ''} onChange={e => handleMeseChange(e.target.value)}>
                  <option value="">Anno intero</option>
                  {NOMI_MESI.slice(1).map((m, i) => (
                    <option key={i} value={i + 1}>
                      {m}
                    </option>
                  ))}
                </Select>
              </div>

              {/* Summary */}
              {confronto.totali && (
                <PageGrid cols={3} gap={16}>
                  {['ricavi', 'costi', 'margine'].map(key => {
                    const t = confronto.totali[key];
                    const color =
                      key === 'ricavi'
                        ? COLORS.success
                        : key === 'costi'
                          ? COLORS.danger
                          : t.consuntivo >= t.budget
                            ? COLORS.success
                            : COLORS.danger;
                    return (
                      <Card
                        key={key}
                        style={{ borderLeft: `4px solid ${COLORS.primary}` }}
                        bodyStyle={{ padding: 16 }}
                      >
                        <div
                          style={{
                            fontSize: 12,
                            fontWeight: 600,
                            color: COLORS.gray[600],
                            textTransform: 'uppercase',
                            marginBottom: 12,
                          }}
                        >
                          {key}
                        </div>
                        <div
                          style={{
                            display: 'grid',
                            gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
                            gap: 8,
                          }}
                        >
                          <div>
                            <div style={{ fontSize: 11, color: COLORS.textSubtle }}>Budget</div>
                            <div
                              style={{
                                fontSize: 18,
                                fontWeight: 700,
                                color: COLORS.gray[600],
                                fontFamily: FONT.mono,
                              }}
                            >
                              {formatEuro(t.budget)}
                            </div>
                          </div>
                          <div>
                            <div style={{ fontSize: 11, color: COLORS.textSubtle }}>Consuntivo</div>
                            <div
                              style={{ fontSize: 18, fontWeight: 700, color, fontFamily: FONT.mono }}
                            >
                              {formatEuro(t.consuntivo)}
                            </div>
                          </div>
                        </div>
                        <div
                          style={{
                            marginTop: 8,
                            padding: '4px 8px',
                            borderRadius: BORDER_RADIUS.sm,
                            background: t.scostamento >= 0 ? COLORS.successLight : COLORS.dangerLight,
                            textAlign: 'center',
                            fontSize: 13,
                            fontWeight: 600,
                            fontFamily: FONT.mono,
                            color: t.scostamento >= 0 ? COLORS.success : COLORS.danger,
                          }}
                        >
                          Scost: {t.scostamento >= 0 ? '+' : ''}
                          {formatEuro(t.scostamento)}
                          {t.scostamento_pct !== undefined &&
                            ` (${t.scostamento_pct >= 0 ? '+' : ''}${t.scostamento_pct}%)`}
                        </div>
                      </Card>
                    );
                  })}
                </PageGrid>
              )}

              {/* Tabella confronto voci */}
              {confronto.confronto_voci?.length > 0 && (
                <TableWrap style={{ marginTop: 20 }}>
                  <Table>
                    <thead>
                      <tr>
                        <Th>Voce</Th>
                        <Th align="center" style={{ width: 70 }}>
                          Tipo
                        </Th>
                        <Th align="right" style={{ width: 120 }}>
                          Budget
                        </Th>
                        <Th align="right" style={{ width: 120 }}>
                          Consuntivo
                        </Th>
                        <Th align="right" style={{ width: 120 }}>
                          Scostamento
                        </Th>
                        <Th align="center" style={{ width: 80 }}>
                          %
                        </Th>
                        <Th align="center" style={{ width: 80 }}>
                          Esito
                        </Th>
                      </tr>
                    </thead>
                    <tbody>
                      {confronto.confronto_voci.map((v, idx) => {
                        const vb = getValBadge(v.valutazione);
                        const isR = v.categoria === 'ricavo';
                        return (
                          <tr
                            key={v.voce}
                            style={{ background: idx % 2 === 0 ? COLORS.card : COLORS.bgAlt }}
                          >
                            <Td style={{ fontWeight: 500 }}>{v.voce}</Td>
                            <Td align="center">
                              <Badge variant={isR ? 'success' : 'danger'}>
                                {isR ? 'RIC' : 'COSTO'}
                              </Badge>
                            </Td>
                            <Td align="right" mono style={{ color: COLORS.gray[600] }}>
                              {formatEuro(v.budget)}
                            </Td>
                            <Td
                              align="right"
                              mono
                              style={{ fontWeight: 600, color: isR ? COLORS.success : COLORS.danger }}
                            >
                              {formatEuro(v.consuntivo)}
                            </Td>
                            <Td
                              align="right"
                              mono
                              style={{
                                fontWeight: 600,
                                color: v.scostamento >= 0 ? COLORS.success : COLORS.danger,
                              }}
                            >
                              {v.scostamento >= 0 ? '+' : ''}
                              {formatEuro(v.scostamento)}
                            </Td>
                            <Td
                              align="center"
                              style={{
                                fontSize: 12,
                                color: v.scostamento_pct >= 0 ? COLORS.success : COLORS.danger,
                              }}
                            >
                              {v.scostamento_pct >= 0 ? '+' : ''}
                              {v.scostamento_pct}%
                            </Td>
                            <Td align="center">
                              <Badge variant={vb.variant}>{vb.icon}</Badge>
                            </Td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </Table>
                </TableWrap>
              )}

              {(!confronto.confronto_voci || confronto.confronto_voci.length === 0) && (
                <div style={{ textAlign: 'center', padding: 60, color: COLORS.textMuted }}>
                  <Target size={48} style={{ margin: '0 auto 16px', opacity: 0.3 }} />
                  <p>Nessun confronto disponibile. Crea prima il budget nella tab "Budget".</p>
                </div>
              )}
            </>
          )}

          {/* ==================== TAB ANDAMENTO ==================== */}
          {activeTab === 'andamento' && confronto?.andamento_mensile && (
            <>
              <TableWrap>
                <Table>
                  <thead>
                    <tr>
                      {[
                        ['Mese', 'left'],
                        ['Ricavi Budget', 'right'],
                        ['Ricavi Reali', 'right'],
                        ['Δ Ricavi', 'right'],
                        ['Costi Budget', 'right'],
                        ['Costi Reali', 'right'],
                        ['Δ Costi', 'right'],
                        ['Margine Budget', 'right'],
                        ['Margine Reale', 'right'],
                      ].map(([label, align]) => (
                        <Th key={label} align={align}>
                          {label}
                        </Th>
                      ))}
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
                        <tr
                          key={m.mese}
                          style={{
                            background: idx % 2 === 0 ? COLORS.card : COLORS.bgAlt,
                            opacity: hasData ? 1 : 0.5,
                          }}
                        >
                          <Td style={{ fontWeight: 500 }}>{NOMI_MESI[m.mese]}</Td>
                          <Td align="right" mono style={{ color: COLORS.textSubtle }}>
                            {formatEuro(m.ricavi_budget)}
                          </Td>
                          <Td align="right" mono style={{ fontWeight: 600, color: COLORS.success }}>
                            {formatEuro(m.ricavi_consuntivo)}
                          </Td>
                          <Td
                            align="right"
                            mono
                            style={{
                              fontSize: 12,
                              color: deltaRic >= 0 ? COLORS.success : COLORS.danger,
                            }}
                          >
                            {hasData ? `${deltaRic >= 0 ? '+' : ''}${formatEuro(deltaRic)}` : '-'}
                          </Td>
                          <Td
                            align="right"
                            mono
                            style={{ color: COLORS.textSubtle, background: COLORS.bgAlt }}
                          >
                            {formatEuro(m.costi_budget)}
                          </Td>
                          <Td
                            align="right"
                            mono
                            style={{ fontWeight: 600, color: COLORS.danger, background: COLORS.bgAlt }}
                          >
                            {formatEuro(m.costi_consuntivo)}
                          </Td>
                          <Td
                            align="right"
                            mono
                            style={{
                              fontSize: 12,
                              background: COLORS.bgAlt,
                              color: deltaCosti <= 0 ? COLORS.success : COLORS.danger,
                            }}
                          >
                            {hasData
                              ? `${deltaCosti >= 0 ? '+' : ''}${formatEuro(deltaCosti)}`
                              : '-'}
                          </Td>
                          <Td align="right" mono style={{ color: COLORS.textMuted }}>
                            {formatEuro(margineBudget)}
                          </Td>
                          <Td
                            align="right"
                            mono
                            style={{
                              fontWeight: 700,
                              color: margineReale >= 0 ? COLORS.success : COLORS.danger,
                            }}
                          >
                            {hasData ? formatEuro(margineReale) : '-'}
                          </Td>
                        </tr>
                      );
                    })}
                  </tbody>
                  <tfoot>
                    <tr style={{ background: COLORS.primary, color: '#fff' }}>
                      <Td style={{ color: '#fff', fontWeight: 700 }}>TOTALE</Td>
                      <Td align="right" mono style={{ color: '#fff', fontWeight: 700 }}>
                        {formatEuro(
                          confronto.andamento_mensile.reduce((s, m) => s + m.ricavi_budget, 0)
                        )}
                      </Td>
                      <Td align="right" mono style={{ color: '#fff', fontWeight: 700 }}>
                        {formatEuro(
                          confronto.andamento_mensile.reduce((s, m) => s + m.ricavi_consuntivo, 0)
                        )}
                      </Td>
                      <Td style={{ color: '#fff' }} />
                      <Td align="right" mono style={{ color: '#fff', fontWeight: 700 }}>
                        {formatEuro(
                          confronto.andamento_mensile.reduce((s, m) => s + m.costi_budget, 0)
                        )}
                      </Td>
                      <Td align="right" mono style={{ color: '#fff', fontWeight: 700 }}>
                        {formatEuro(
                          confronto.andamento_mensile.reduce((s, m) => s + m.costi_consuntivo, 0)
                        )}
                      </Td>
                      <Td colSpan={3} style={{ color: '#fff' }} />
                    </tr>
                  </tfoot>
                </Table>
              </TableWrap>

              {/* Barra grafica semplice */}
              <PageSection title="Grafico Andamento" style={{ marginTop: 24 }}>
                <div
                  style={{
                    display: 'flex',
                    gap: 4,
                    alignItems: 'flex-end',
                    height: 200,
                    padding: '0 20px',
                  }}
                >
                  {confronto.andamento_mensile.map(m => {
                    const maxVal = Math.max(
                      ...confronto.andamento_mensile.map(x =>
                        Math.max(x.ricavi_consuntivo, x.costi_consuntivo, x.ricavi_budget, 1)
                      )
                    );
                    const hRicavi = (m.ricavi_consuntivo / maxVal) * 180;
                    const hCosti = (m.costi_consuntivo / maxVal) * 180;
                    return (
                      <div
                        key={m.mese}
                        style={{
                          flex: 1,
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'center',
                          gap: 2,
                        }}
                      >
                        <div
                          style={{ display: 'flex', gap: 2, alignItems: 'flex-end', height: 180 }}
                        >
                          <div
                            style={{
                              width: 12,
                              height: Math.max(hRicavi, 2),
                              background: COLORS.success,
                              borderRadius: '3px 3px 0 0',
                            }}
                            title={`Ricavi: ${formatEuro(m.ricavi_consuntivo)}`}
                          />
                          <div
                            style={{
                              width: 12,
                              height: Math.max(hCosti, 2),
                              background: COLORS.danger,
                              borderRadius: '3px 3px 0 0',
                            }}
                            title={`Costi: ${formatEuro(m.costi_consuntivo)}`}
                          />
                        </div>
                        <span style={{ fontSize: 10, color: COLORS.textSubtle }}>
                          {NOMI_MESI[m.mese]}
                        </span>
                      </div>
                    );
                  })}
                </div>
                <div style={{ display: 'flex', gap: 16, justifyContent: 'center', marginTop: 12 }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
                    <span
                      style={{
                        width: 12,
                        height: 12,
                        background: COLORS.success,
                        borderRadius: 2,
                        display: 'inline-block',
                      }}
                    />{' '}
                    Ricavi
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
                    <span
                      style={{
                        width: 12,
                        height: 12,
                        background: COLORS.danger,
                        borderRadius: 2,
                        display: 'inline-block',
                      }}
                    />{' '}
                    Costi
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
