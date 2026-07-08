/**
 * LearningMachine.jsx - Pagina Centralizzata Learning Machine
 * ============================================================
 *
 * Centralizza tutte le funzionalità di apprendimento automatico:
 * - Tab 1: Fornitori & Keywords (ex Fornitori.jsx)
 * - Tab 2: Pattern Assegni (ex GestioneAssegni.jsx)
 * - Tab 3: Classificazione Documenti
 * - Tab 4: Dashboard & Statistiche
 *
 * Creato: 4 Febbraio 2026
 */

import React, { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import api from '../api';
import {
  formatEuro,
  formatDateIT,
  COLORS,
  SHADOWS,
  BORDER_RADIUS,
  useIsMobile,
} from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { useConfirm } from '../components/ui/ConfirmDialog';
import { Button, Badge, StatCard, Tabs, Input, Select } from '../components/ds';
import {
  Brain,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Tag,
  ChevronRight,
  Lightbulb,
  TrendingUp,
  FileText,
  CreditCard,
  BarChart3,
  Zap,
  Trash2,
  Settings,
  Search,
  Filter,
  Download,
  Play,
  Pause,
} from 'lucide-react';

const RegoleCategorizzazioneLazy = lazy(() => import('./RegoleCategorizzazione.jsx'));
const LearningUniversaleLazy = lazy(() => import('./LearningMachineUniversale.jsx'));

// ============================================================
// COMPONENTI RIUTILIZZABILI
// ============================================================

function MessageBanner({ message, onClose }) {
  if (!message) return null;

  const isSuccess = message.type === 'success';
  return (
    <div
      style={{
        background: isSuccess ? COLORS.successLight : COLORS.dangerLight,
        border: `1px solid ${isSuccess ? COLORS.success : COLORS.danger}`,
        borderRadius: BORDER_RADIUS.md,
        padding: 12,
        marginBottom: 16,
        display: 'flex',
        alignItems: 'center',
        gap: 8,
      }}
    >
      {isSuccess ? (
        <CheckCircle size={18} color={COLORS.success} />
      ) : (
        <AlertCircle size={18} color={COLORS.danger} />
      )}
      <span style={{ color: isSuccess ? COLORS.success : COLORS.danger, fontWeight: 500 }}>
        {message.text}
      </span>
      <Button
        variant="ghost"
        size="sm"
        onClick={onClose}
        style={{ marginLeft: 'auto', padding: '2px 8px', fontSize: 18 }}
      >
        ×
      </Button>
    </div>
  );
}

function LoadingSpinner({ text = 'Caricamento...' }) {
  return (
    <div style={{ textAlign: 'center', padding: 60, color: COLORS.textMuted }}>
      <RefreshCw size={32} className="animate-spin" style={{ margin: '0 auto 12px' }} />
      <p>{text}</p>
    </div>
  );
}

// ============================================================
// COMPONENTE PRINCIPALE
// ============================================================

export default function LearningMachine() {
  const isMobile = useIsMobile();
  const confirm = useConfirm();
  // === URL TAB NAVIGATION ===
  const navigate = useNavigate();
  const location = useLocation();

  const getTabFromPath = () => {
    const match = location.pathname.match(/\/learning-machine\/(\w+)/);
    const validTabs = ['dashboard', 'fornitori', 'assegni', 'documenti', 'regole'];
    if (match && validTabs.includes(match[1])) return match[1];
    return 'fornitori';
  };

  const [activeTab, setActiveTab] = useState(getTabFromPath());
  const [message, setMessage] = useState(null);

  // === FORNITORI STATE ===
  const [fornitoriNonClassificati, setFornitoriNonClassificati] = useState([]);
  const [fornitoriConfigurati, setFornitoriConfigurati] = useState([]);
  const [centriCosto, setCentriCosto] = useState([]);
  const [fornitoriLoading, setFornitoriLoading] = useState(false);
  const [selectedFornitore, setSelectedFornitore] = useState(null);
  const [keywords, setKeywords] = useState('');
  const [centroCostoSuggerito, setCentroCostoSuggerito] = useState('');
  const [keywordsSuggerite, setKeywordsSuggerite] = useState([]);
  const [saving, setSaving] = useState(false);

  // === ASSEGNI STATE ===
  const [assegniStats, setAssegniStats] = useState(null);
  const [assegniLoading, setAssegniLoading] = useState(false);
  const [learningResult, setLearningResult] = useState(null);
  const [puliziaResult, setPuliziaResult] = useState(null);

  // === DOCUMENTI STATE ===
  const [documentiStats, setDocumentiStats] = useState(null);
  const [documentiLoading, setDocumentiLoading] = useState(false);
  const [regoleApprese, setRegoleApprese] = useState([]);

  // === DASHBOARD STATE ===
  const [dashboardStats, setDashboardStats] = useState(null);
  const [dashboardLoading, setDashboardLoading] = useState(true);

  // ============================================================
  // CARICAMENTO DATI
  // ============================================================

  // Carica stats dashboard (generale)
  const loadDashboardStats = useCallback(async () => {
    setDashboardLoading(true);
    try {
      const res = await api.get('/api/fornitori-learning/stats');
      setDashboardStats(res.data);
    } catch (error) {
      console.error('Errore caricamento dashboard:', error);
    }
    setDashboardLoading(false);
  }, []);

  // Carica dati fornitori
  const loadFornitoriData = useCallback(async () => {
    setFornitoriLoading(true);
    try {
      const [nonClass, config, cdc] = await Promise.all([
        api.get('/api/fornitori-learning/non-classificati?limit=100'),
        api.get('/api/fornitori-learning/lista'),
        api.get('/api/fornitori-learning/centri-costo-disponibili'),
      ]);

      setFornitoriNonClassificati(nonClass.data.fornitori || []);
      setFornitoriConfigurati(config.data.fornitori || []);
      setCentriCosto(cdc.data || []);
    } catch (error) {
      console.error('Errore caricamento fornitori:', error);
      setMessage({ type: 'error', text: 'Errore nel caricamento dei fornitori' });
    }
    setFornitoriLoading(false);
  }, []);

  // Carica stats assegni
  const loadAssegniStats = useCallback(async () => {
    setAssegniLoading(true);
    try {
      const res = await api.get('/api/assegni/learning/stats-avanzate');
      setAssegniStats(res.data);
    } catch (error) {
      console.error('Errore caricamento stats assegni:', error);
    }
    setAssegniLoading(false);
  }, []);

  // Carica stats documenti
  const loadDocumentiStats = useCallback(async () => {
    setDocumentiLoading(true);
    try {
      const [statsRes, regoleRes] = await Promise.all([
        api.get('/api/learning-machine/dashboard').catch(() => ({ data: null })),
        api.get('/api/learning-machine/regole-apprese').catch(() => ({ data: [] })),
      ]);
      setDocumentiStats(statsRes.data);
      setRegoleApprese(regoleRes.data || []);
    } catch (error) {
      console.error('Errore caricamento documenti:', error);
    }
    setDocumentiLoading(false);
  }, []);

  // Carica dati in base al tab attivo
  useEffect(() => {
    loadDashboardStats();
  }, [loadDashboardStats]);

  useEffect(() => {
    if (activeTab === 'fornitori') loadFornitoriData();
    if (activeTab === 'assegni') loadAssegniStats();
    if (activeTab === 'documenti') loadDocumentiStats();
  }, [activeTab, loadFornitoriData, loadAssegniStats, loadDocumentiStats]);

  // ============================================================
  // AZIONI FORNITORI
  // ============================================================

  const selezionaFornitore = async fornitore => {
    setSelectedFornitore(fornitore);
    setKeywords('');
    setCentroCostoSuggerito('');

    try {
      const res = await api.get(
        `/api/fornitori-learning/suggerisci-keywords/${encodeURIComponent(fornitore.fornitore_nome)}`
      );
      setKeywordsSuggerite(res.data.keywords_suggerite || []);
    } catch (error) {
      console.error('Errore suggerimenti:', error);
    }
  };

  const salvaFornitore = async () => {
    if (!selectedFornitore || !keywords.trim()) {
      setMessage({ type: 'error', text: 'Inserisci almeno una keyword' });
      return;
    }

    setSaving(true);
    try {
      const res = await api.post('/api/fornitori-learning/salva', {
        fornitore_nome: selectedFornitore.fornitore_nome,
        keywords: keywords
          .split(',')
          .map(k => k.trim())
          .filter(k => k),
        centro_costo_suggerito: centroCostoSuggerito || null,
      });

      if (res.data.success) {
        setMessage({ type: 'success', text: 'Fornitore salvato!' });
        setSelectedFornitore(null);
        setKeywords('');
        loadFornitoriData();
        loadDashboardStats();
      }
    } catch (error) {
      setMessage({ type: 'error', text: 'Errore nel salvataggio' });
    }
    setSaving(false);
  };

  const eliminaFornitoreKeywords = async fornitoreId => {
    const confirmed = await confirm({
      title: 'Elimina configurazione',
      message: 'Eliminare questa configurazione?',
      variant: 'danger',
    });
    if (!confirmed) return;

    try {
      await api.delete(`/api/fornitori-learning/${fornitoreId}`);
      setMessage({ type: 'success', text: 'Eliminato' });
      loadFornitoriData();
    } catch (error) {
      setMessage({ type: 'error', text: 'Errore eliminazione' });
    }
  };

  const riclassificaFatture = async () => {
    setFornitoriLoading(true);
    try {
      const res = await api.post('/api/fornitori-learning/riclassifica-con-keywords');
      if (res.data.success) {
        setMessage({
          type: 'success',
          text: `Riclassificate ${res.data.totale_riclassificate} fatture!`,
        });
        loadFornitoriData();
        loadDashboardStats();
      }
    } catch (error) {
      setMessage({ type: 'error', text: 'Errore riclassificazione' });
    }
    setFornitoriLoading(false);
  };

  const aggiungiKeywordSuggerita = keyword => {
    const current = keywords ? keywords.split(',').map(k => k.trim()) : [];
    if (!current.includes(keyword)) {
      setKeywords([...current, keyword].join(', '));
    }
  };

  // ============================================================
  // AZIONI ASSEGNI
  // ============================================================

  const handleLearnAssegni = async () => {
    setAssegniLoading(true);
    setLearningResult(null);
    try {
      const res = await api.post('/api/assegni/learning/learn');
      setLearningResult(res.data);
      loadAssegniStats();
      setMessage({
        type: 'success',
        text: `Appresi ${res.data.pattern_appresi || 0} nuovi pattern!`,
      });
    } catch (error) {
      setMessage({ type: 'error', text: 'Errore nel learning' });
    }
    setAssegniLoading(false);
  };

  const handleAssociaIntelligente = async () => {
    setAssegniLoading(true);
    try {
      const res = await api.post('/api/assegni/learning/associa-intelligente');
      setMessage({ type: 'success', text: `Associati ${res.data.associati || 0} assegni!` });
      loadAssegniStats();
    } catch (error) {
      setMessage({ type: 'error', text: 'Errore associazione' });
    }
    setAssegniLoading(false);
  };

  const handlePuliziaDuplicati = async (dryRun = true) => {
    setAssegniLoading(true);
    setPuliziaResult(null);
    try {
      const res = await api.post(`/api/assegni/learning/pulizia-duplicati?dry_run=${dryRun}`);
      setPuliziaResult(res.data);
      if (!dryRun && res.data.record_eliminati > 0) {
        loadAssegniStats();
        setMessage({ type: 'success', text: `Eliminati ${res.data.record_eliminati} duplicati!` });
      }
    } catch (error) {
      setMessage({ type: 'error', text: 'Errore pulizia' });
    }
    setAssegniLoading(false);
  };

  // ============================================================
  // TABS
  // ============================================================

  const TABS = [
    { id: 'dashboard', label: 'Dashboard', icon: BarChart3 },
    { id: 'fornitori', label: 'Fornitori & Keywords', icon: Tag },
    { id: 'assegni', label: 'Pattern Assegni', icon: CreditCard },
    { id: 'documenti', label: 'Classificazione Documenti', icon: FileText },
    { id: 'regole', label: '⚙️ Regole Categorizzazione', icon: Settings },
    { id: 'universale', label: '🌐 Training Universale', icon: RefreshCw },
  ];

  // ============================================================
  // RENDER
  // ============================================================

  return (
    <div style={{ padding: 20, maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div
        style={{
          background: COLORS.primary,
          borderRadius: BORDER_RADIUS.md,
          padding: 24,
          marginBottom: 20,
          color: 'white',
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 16,
          }}
        >
          <div>
            <h1
              style={{
                margin: 0,
                fontSize: 24,
                fontWeight: 'bold',
                display: 'flex',
                alignItems: 'center',
                gap: 12,
              }}
            >
              <Brain size={28} /> Learning Machine
            </h1>
            <p style={{ margin: '8px 0 0 0', opacity: 0.9, fontSize: 14 }}>
              Sistema di apprendimento automatico per classificazione e associazione
            </p>
          </div>
          <div
            style={{
              background: 'rgba(255,255,255,0.15)',
              padding: '8px 16px',
              borderRadius: 8,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <Zap size={18} />
            <span style={{ fontWeight: 600 }}>Sistema Attivo</span>
          </div>
        </div>
      </div>

      {/* Messaggio globale */}
      <MessageBanner message={message} onClose={() => setMessage(null)} />

      {/* Tabs */}
      <div
        style={{
          marginBottom: 20,
          background: COLORS.bgAlt,
          padding: 4,
          borderRadius: BORDER_RADIUS.lg,
        }}
      >
        <Tabs
          items={TABS.map(tab => ({
            key: tab.id,
            label: tab.label,
            icon: <tab.icon size={16} />,
          }))}
          value={activeTab}
          onChange={tabId => {
            setActiveTab(tabId);
            navigate(tabId === 'fornitori' ? '/learning-machine' : `/learning-machine/${tabId}`);
          }}
        />
      </div>

      {/* ============================================================ */}
      {/* TAB: DASHBOARD */}
      {/* ============================================================ */}
      {activeTab === 'dashboard' && (
        <div>
          {dashboardLoading ? (
            <LoadingSpinner text="Caricamento statistiche..." />
          ) : (
            <>
              {/* Stats Overview */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                  gap: 16,
                  marginBottom: 24,
                }}
              >
                <StatCard
                  icon={<Tag size={18} />}
                  label="Fornitori Configurati"
                  value={dashboardStats?.fornitori_con_keywords || 0}
                  subtext={`${dashboardStats?.copertura_fornitori || 0}% copertura`}
                  accent="success"
                />
                <StatCard
                  icon={<FileText size={18} />}
                  label="Fatture Classificate"
                  value={`${dashboardStats?.percentuale_fatture || 0}%`}
                  subtext={`${dashboardStats?.fatture_classificate || 0}/${dashboardStats?.totale_fatture || 0}`}
                  accent="info"
                />
                <StatCard
                  icon={<CreditCard size={18} />}
                  label="Pattern Assegni"
                  value={assegniStats?.pattern_totali || 0}
                  subtext={`${assegniStats?.accuracy || 0}% accuracy`}
                  accent="accent"
                />
                <StatCard
                  icon={<TrendingUp size={18} />}
                  label="F24 Classificati"
                  value={`${dashboardStats?.percentuale_f24 || 0}%`}
                  subtext={`${dashboardStats?.f24_classificati || 0}/${dashboardStats?.totale_f24 || 0}`}
                  accent="warning"
                />
              </div>

              {/* Quick Actions */}
              <div
                style={{
                  background: COLORS.card,
                  borderRadius: BORDER_RADIUS.md,
                  padding: 20,
                  boxShadow: SHADOWS.md,
                }}
              >
                <h3
                  style={{
                    margin: '0 0 16px 0',
                    fontSize: 16,
                    fontWeight: 600,
                    color: COLORS.primaryLight,
                  }}
                >
                  Azioni Rapide
                </h3>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                    gap: 12,
                  }}
                >
                  <Button
                    variant="primary"
                    size="lg"
                    onClick={() => {
                      setActiveTab('fornitori');
                      riclassificaFatture();
                    }}
                    style={{ justifyContent: 'flex-start' }}
                  >
                    <Play size={18} /> Riclassifica Tutte le Fatture
                  </Button>
                  <Button
                    variant="danger"
                    size="lg"
                    onClick={() => {
                      setActiveTab('assegni');
                      handleLearnAssegni();
                    }}
                    style={{ justifyContent: 'flex-start' }}
                  >
                    <Brain size={18} /> Apprendi Pattern Assegni
                  </Button>
                  <Button
                    variant="secondary"
                    size="lg"
                    onClick={loadDashboardStats}
                    style={{ justifyContent: 'flex-start' }}
                  >
                    <RefreshCw size={18} /> Aggiorna Statistiche
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* ============================================================ */}
      {/* TAB: FORNITORI & KEYWORDS */}
      {/* ============================================================ */}
      {activeTab === 'fornitori' && (
        <div>
          {/* Header con azioni */}
          <div
            style={{
              background: COLORS.card,
              borderRadius: BORDER_RADIUS.md,
              padding: 20,
              marginBottom: 16,
              boxShadow: SHADOWS.md,
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: 12,
              }}
            >
              <div>
                <h2 style={{ margin: 0, fontSize: 18, fontWeight: 'bold', color: COLORS.primaryLight }}>
                  Classificazione Fornitori
                </h2>
                <p style={{ color: COLORS.textMuted, fontSize: 13, margin: '4px 0 0 0' }}>
                  Configura keywords per classificare automaticamente i fornitori nei centri di
                  costo
                </p>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <Button variant="secondary" onClick={loadFornitoriData} disabled={fornitoriLoading}>
                  <RefreshCw size={16} className={fornitoriLoading ? 'animate-spin' : ''} />
                  Aggiorna
                </Button>
                <Button
                  variant="primary"
                  onClick={riclassificaFatture}
                  disabled={fornitoriLoading || fornitoriConfigurati.length === 0}
                >
                  <CheckCircle size={16} />
                  Riclassifica Fatture
                </Button>
              </div>
            </div>
          </div>

          {/* Stats */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)',
              gap: 16,
              marginBottom: 20,
            }}
          >
            <StatCard
              icon={<AlertCircle size={18} />}
              label="Da Classificare"
              value={fornitoriNonClassificati.length}
              accent="warning"
            />
            <StatCard
              icon={<CheckCircle size={18} />}
              label="Configurati"
              value={fornitoriConfigurati.length}
              accent="success"
            />
            <StatCard
              icon={<Tag size={18} />}
              label="Centri di Costo"
              value={centriCosto.length}
              accent="info"
            />
          </div>

          {fornitoriLoading ? (
            <LoadingSpinner />
          ) : (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
                gap: 16,
              }}
            >
              {/* Lista fornitori non classificati */}
              <div
                style={{
                  background: COLORS.card,
                  borderRadius: BORDER_RADIUS.md,
                  padding: 20,
                  boxShadow: SHADOWS.md,
                }}
              >
                <h3
                  style={{
                    margin: '0 0 16px 0',
                    fontSize: 16,
                    fontWeight: 600,
                    color: COLORS.primaryLight,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                  }}
                >
                  <AlertCircle size={18} color={COLORS.warning} /> Da Classificare (
                  {fornitoriNonClassificati.length})
                </h3>

                <div style={{ maxHeight: 500, overflowY: 'auto' }}>
                  {fornitoriNonClassificati.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: 40, color: COLORS.textMuted }}>
                      <CheckCircle size={48} color={COLORS.success} style={{ marginBottom: 12 }} />
                      <p>Tutti i fornitori sono classificati!</p>
                    </div>
                  ) : (
                    fornitoriNonClassificati.map((f, idx) => (
                      <div
                        key={idx}
                        onClick={() => selezionaFornitore(f)}
                        style={{
                          padding: 12,
                          borderRadius: BORDER_RADIUS.md,
                          marginBottom: 8,
                          cursor: 'pointer',
                          background:
                            selectedFornitore?.fornitore_nome === f.fornitore_nome
                              ? COLORS.primarySoft
                              : COLORS.bgAlt,
                          border:
                            selectedFornitore?.fornitore_nome === f.fornitore_nome
                              ? `2px solid ${COLORS.primary}`
                              : `1px solid ${COLORS.border}`,
                          transition: 'all 0.2s',
                        }}
                      >
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                          }}
                        >
                          <div>
                            <p
                              style={{ fontWeight: 600, color: COLORS.text, margin: 0, fontSize: 14 }}
                            >
                              {f.fornitore_nome}
                            </p>
                            <p style={{ color: COLORS.textMuted, fontSize: 12, margin: '4px 0 0 0' }}>
                              {f.fatture_count} fatture • {formatEuro(f.totale_fatture || 0)}
                            </p>
                          </div>
                          <ChevronRight size={16} color={COLORS.textSubtle} />
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Form configurazione */}
              <div
                style={{
                  background: COLORS.card,
                  borderRadius: BORDER_RADIUS.md,
                  padding: 20,
                  boxShadow: SHADOWS.md,
                }}
              >
                <h3
                  style={{
                    margin: '0 0 16px 0',
                    fontSize: 16,
                    fontWeight: 600,
                    color: COLORS.primaryLight,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                  }}
                >
                  <Tag size={18} color={COLORS.primaryLight} /> Configura Keywords
                </h3>

                {selectedFornitore ? (
                  <div>
                    <div
                      style={{
                        background: COLORS.infoLight,
                        borderRadius: BORDER_RADIUS.md,
                        padding: 12,
                        marginBottom: 16,
                      }}
                    >
                      <p style={{ margin: 0, fontWeight: 600, color: COLORS.info }}>
                        {selectedFornitore.fornitore_nome}
                      </p>
                      <p style={{ margin: '4px 0 0 0', fontSize: 12, color: COLORS.info }}>
                        {selectedFornitore.fatture_count} fatture •{' '}
                        {formatEuro(selectedFornitore.totale_fatture || 0)}
                      </p>
                    </div>

                    {/* Keywords suggerite */}
                    {keywordsSuggerite.length > 0 && (
                      <div style={{ marginBottom: 16 }}>
                        <label
                          style={{
                            fontSize: 12,
                            fontWeight: 600,
                            color: COLORS.gray[700],
                            display: 'block',
                            marginBottom: 8,
                          }}
                        >
                          Keywords Suggerite (clicca per aggiungere)
                        </label>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                          {keywordsSuggerite.map((kw, idx) => (
                            <Button
                              key={idx}
                              variant="outline"
                              size="sm"
                              onClick={() => aggiungiKeywordSuggerita(kw)}
                              style={{ padding: '4px 10px', fontSize: 12 }}
                            >
                              + {kw}
                            </Button>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Input keywords */}
                    <div style={{ marginBottom: 16 }}>
                      <label
                        style={{
                          fontSize: 12,
                          fontWeight: 600,
                          color: COLORS.gray[700],
                          display: 'block',
                          marginBottom: 6,
                        }}
                      >
                        Keywords (separate da virgola)
                      </label>
                      <Input
                        type="text"
                        value={keywords}
                        onChange={e => setKeywords(e.target.value)}
                        placeholder="es: bar, caffè, tabacchi"
                        style={{ fontSize: 14 }}
                      />
                    </div>

                    {/* Select centro costo */}
                    <div style={{ marginBottom: 16 }}>
                      <label
                        style={{
                          fontSize: 12,
                          fontWeight: 600,
                          color: COLORS.gray[700],
                          display: 'block',
                          marginBottom: 6,
                        }}
                      >
                        Centro di Costo Suggerito
                      </label>
                      <Select
                        value={centroCostoSuggerito}
                        onChange={e => setCentroCostoSuggerito(e.target.value)}
                        style={{ width: '100%', fontSize: 14 }}
                      >
                        <option value="">-- Seleziona --</option>
                        {centriCosto.map(cdc => (
                          <option key={cdc.id || cdc.codice} value={cdc.id || cdc.codice}>
                            {cdc.nome || cdc.descrizione}
                          </option>
                        ))}
                      </Select>
                    </div>

                    {/* Bottoni */}
                    <div style={{ display: 'flex', gap: 8 }}>
                      <Button
                        variant="primary"
                        onClick={salvaFornitore}
                        disabled={saving || !keywords.trim()}
                        style={{ flex: 1, justifyContent: 'center' }}
                      >
                        {saving ? 'Salvataggio...' : 'Salva Keywords'}
                      </Button>
                      <Button variant="secondary" onClick={() => setSelectedFornitore(null)}>
                        Annulla
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div style={{ textAlign: 'center', padding: 40, color: COLORS.textMuted }}>
                    <Lightbulb size={48} color={COLORS.border} style={{ marginBottom: 12 }} />
                    <p>Seleziona un fornitore dalla lista per configurare le keywords</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Lista fornitori configurati */}
          {fornitoriConfigurati.length > 0 && (
            <div
              style={{
                background: COLORS.card,
                borderRadius: BORDER_RADIUS.md,
                padding: 20,
                marginTop: 20,
                boxShadow: SHADOWS.md,
              }}
            >
              <h3
                style={{
                  margin: '0 0 16px 0',
                  fontSize: 16,
                  fontWeight: 600,
                  color: COLORS.primaryLight,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <CheckCircle size={18} color={COLORS.success} /> Fornitori Configurati (
                {fornitoriConfigurati.length})
              </h3>

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
                  gap: 12,
                }}
              >
                {fornitoriConfigurati.map((f, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: 12,
                      background: COLORS.bgAlt,
                      borderRadius: BORDER_RADIUS.md,
                      border: `1px solid ${COLORS.border}`,
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'flex-start',
                      }}
                    >
                      <div>
                        <p style={{ fontWeight: 600, color: COLORS.text, margin: 0, fontSize: 14 }}>
                          {f.fornitore_nome}
                        </p>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
                          {(f.keywords || []).map((kw, i) => (
                            <Badge key={i} variant="info" style={{ textTransform: 'none' }}>
                              {kw}
                            </Badge>
                          ))}
                        </div>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => eliminaFornitoreKeywords(f.id)}
                        style={{ padding: 4, color: COLORS.danger }}
                      >
                        <Trash2 size={16} />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ============================================================ */}
      {/* TAB: PATTERN ASSEGNI */}
      {/* ============================================================ */}
      {activeTab === 'assegni' && (
        <div>
          {/* Header */}
          <div
            style={{
              background: COLORS.card,
              borderRadius: BORDER_RADIUS.md,
              padding: 20,
              marginBottom: 16,
              boxShadow: SHADOWS.md,
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: 12,
              }}
            >
              <div>
                <h2 style={{ margin: 0, fontSize: 18, fontWeight: 'bold', color: COLORS.primaryLight }}>
                  Pattern Assegni
                </h2>
                <p style={{ color: COLORS.textMuted, fontSize: 13, margin: '4px 0 0 0' }}>
                  Apprende dalle associazioni esistenti per suggerire automaticamente beneficiari
                </p>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <Button variant="secondary" onClick={loadAssegniStats} disabled={assegniLoading}>
                  <RefreshCw size={16} className={assegniLoading ? 'animate-spin' : ''} />
                  Aggiorna
                </Button>
              </div>
            </div>
          </div>

          {/* Stats Assegni */}
          {assegniStats && (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                gap: 16,
                marginBottom: 20,
              }}
            >
              <StatCard
                icon={<Brain size={18} />}
                label="Pattern Appresi"
                value={assegniStats.pattern_totali || 0}
                accent="accent"
              />
              <StatCard
                icon={<CheckCircle size={18} />}
                label="Accuracy"
                value={`${assegniStats.accuracy || 0}%`}
                accent="success"
              />
              <StatCard
                icon={<CreditCard size={18} />}
                label="Assegni Totali"
                value={assegniStats.totale_assegni || 0}
                accent="info"
              />
              <StatCard
                icon={<AlertCircle size={18} />}
                label="Non Associati"
                value={assegniStats.non_associati || 0}
                accent="warning"
              />
            </div>
          )}

          {/* Azioni */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
              gap: 16,
            }}
          >
            {/* Card: Apprendi */}
            <div
              style={{
                background: COLORS.card,
                borderRadius: BORDER_RADIUS.md,
                padding: 20,
                boxShadow: SHADOWS.md,
              }}
            >
              <h3
                style={{
                  margin: '0 0 12px 0',
                  fontSize: 16,
                  fontWeight: 600,
                  color: COLORS.primaryLight,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <Brain size={18} color={COLORS.accent} /> Apprendi Pattern
              </h3>
              <p style={{ color: COLORS.textMuted, fontSize: 13, marginBottom: 16 }}>
                Analizza le associazioni esistenti tra assegni e fatture per apprendere nuovi
                pattern.
              </p>
              <Button
                variant="info"
                onClick={handleLearnAssegni}
                disabled={assegniLoading}
                style={{ width: '100%', justifyContent: 'center' }}
              >
                <Brain size={16} /> {assegniLoading ? 'Apprendimento...' : 'Avvia Learning'}
              </Button>

              {learningResult && (
                <div
                  style={{
                    marginTop: 12,
                    padding: 12,
                    background: COLORS.accentSoft,
                    borderRadius: BORDER_RADIUS.md,
                  }}
                >
                  <p style={{ margin: 0, fontSize: 13, color: COLORS.accent }}>
                    ✅ Appresi <strong>{learningResult.pattern_appresi}</strong> pattern da{' '}
                    {learningResult.assegni_analizzati} assegni
                  </p>
                </div>
              )}
            </div>

            {/* Card: Associa Intelligente */}
            <div
              style={{
                background: COLORS.card,
                borderRadius: BORDER_RADIUS.md,
                padding: 20,
                boxShadow: SHADOWS.md,
              }}
            >
              <h3
                style={{
                  margin: '0 0 12px 0',
                  fontSize: 16,
                  fontWeight: 600,
                  color: COLORS.primaryLight,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <Zap size={18} color={COLORS.warning} /> Associazione Intelligente
              </h3>
              <p style={{ color: COLORS.textMuted, fontSize: 13, marginBottom: 16 }}>
                Usa i pattern appresi per associare automaticamente gli assegni alle fatture.
              </p>
              <Button
                variant="warning"
                onClick={handleAssociaIntelligente}
                disabled={assegniLoading}
                style={{ width: '100%', justifyContent: 'center' }}
              >
                <Zap size={16} /> {assegniLoading ? 'Associazione...' : 'Associa Automaticamente'}
              </Button>
            </div>

            {/* Card: Pulizia Duplicati */}
            <div
              style={{
                background: COLORS.card,
                borderRadius: BORDER_RADIUS.md,
                padding: 20,
                boxShadow: SHADOWS.md,
              }}
            >
              <h3
                style={{
                  margin: '0 0 12px 0',
                  fontSize: 16,
                  fontWeight: 600,
                  color: COLORS.primaryLight,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <Trash2 size={18} color={COLORS.danger} /> Pulizia Duplicati
              </h3>
              <p style={{ color: COLORS.textMuted, fontSize: 13, marginBottom: 16 }}>
                Trova e rimuove assegni duplicati dal database.
              </p>
              <div style={{ display: 'flex', gap: 8 }}>
                <Button
                  variant="secondary"
                  onClick={() => handlePuliziaDuplicati(true)}
                  disabled={assegniLoading}
                  style={{ flex: 1, justifyContent: 'center' }}
                >
                  Anteprima
                </Button>
                <Button
                  variant="danger"
                  onClick={() => handlePuliziaDuplicati(false)}
                  disabled={assegniLoading || !puliziaResult}
                  style={{ flex: 1, justifyContent: 'center' }}
                >
                  Elimina
                </Button>
              </div>

              {puliziaResult && (
                <div
                  style={{
                    marginTop: 12,
                    padding: 12,
                    background: COLORS.dangerLight,
                    borderRadius: BORDER_RADIUS.md,
                  }}
                >
                  <p style={{ margin: 0, fontSize: 13, color: COLORS.danger }}>
                    Trovati <strong>{puliziaResult.duplicati_trovati || 0}</strong> duplicati
                    {puliziaResult.record_eliminati > 0 &&
                      ` - Eliminati: ${puliziaResult.record_eliminati}`}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* TAB: CLASSIFICAZIONE DOCUMENTI */}
      {/* ============================================================ */}
      {activeTab === 'documenti' && (
        <div>
          {/* Header */}
          <div
            style={{
              background: COLORS.card,
              borderRadius: BORDER_RADIUS.md,
              padding: 20,
              marginBottom: 16,
              boxShadow: SHADOWS.md,
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: 12,
              }}
            >
              <div>
                <h2 style={{ margin: 0, fontSize: 18, fontWeight: 'bold', color: COLORS.primaryLight }}>
                  Classificazione Documenti
                </h2>
                <p style={{ color: COLORS.textMuted, fontSize: 13, margin: '4px 0 0 0' }}>
                  Sistema di classificazione automatica documenti con apprendimento iterativo
                </p>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <Button variant="secondary" onClick={loadDocumentiStats} disabled={documentiLoading}>
                  <RefreshCw size={16} className={documentiLoading ? 'animate-spin' : ''} />
                  Aggiorna
                </Button>
                <Link
                  to="/classificazione-email"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 7,
                    padding: '8px 16px',
                    borderRadius: BORDER_RADIUS.sm,
                    fontSize: 13,
                    fontWeight: 600,
                    background: COLORS.primary,
                    color: '#fff',
                    border: `1px solid ${COLORS.primary}`,
                    textDecoration: 'none',
                  }}
                >
                  <FileText size={16} /> Vai a Classificazione Email
                </Link>
              </div>
            </div>
          </div>

          {documentiLoading ? (
            <LoadingSpinner />
          ) : (
            <>
              {/* Stats */}
              {documentiStats && (
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                    gap: 16,
                    marginBottom: 20,
                  }}
                >
                  <StatCard
                    icon={<FileText size={18} />}
                    label="Documenti Classificati"
                    value={documentiStats.totale_classificati || 0}
                    accent="info"
                  />
                  <StatCard
                    icon={<Brain size={18} />}
                    label="Regole Apprese"
                    value={regoleApprese.length}
                    accent="accent"
                  />
                  <StatCard
                    icon={<CheckCircle size={18} />}
                    label="Accuracy Media"
                    value={`${documentiStats.accuracy || 0}%`}
                    accent="success"
                  />
                  <StatCard
                    icon={<TrendingUp size={18} />}
                    label="Feedback Ricevuti"
                    value={documentiStats.feedback_count || 0}
                    accent="warning"
                  />
                </div>
              )}

              {/* Info */}
              <div
                style={{
                  background: COLORS.card,
                  borderRadius: BORDER_RADIUS.md,
                  padding: 20,
                  boxShadow: SHADOWS.md,
                }}
              >
                <h3
                  style={{
                    margin: '0 0 16px 0',
                    fontSize: 16,
                    fontWeight: 600,
                    color: COLORS.primaryLight,
                  }}
                >
                  Come Funziona
                </h3>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
                    gap: 16,
                  }}
                >
                  <div
                    style={{
                      padding: 16,
                      background: COLORS.infoLight,
                      borderRadius: BORDER_RADIUS.md,
                    }}
                  >
                    <h4 style={{ margin: '0 0 8px 0', color: COLORS.info, fontSize: 14 }}>
                      1. Scansione Email
                    </h4>
                    <p style={{ margin: 0, fontSize: 13, color: COLORS.textMuted }}>
                      Il sistema scansiona le email e identifica automaticamente il tipo di
                      documento (F24, fattura, cedolino, etc.)
                    </p>
                  </div>
                  <div
                    style={{
                      padding: 16,
                      background: COLORS.successLight,
                      borderRadius: BORDER_RADIUS.md,
                    }}
                  >
                    <h4 style={{ margin: '0 0 8px 0', color: COLORS.success, fontSize: 14 }}>
                      2. Classificazione
                    </h4>
                    <p style={{ margin: 0, fontSize: 13, color: COLORS.textMuted }}>
                      Ogni documento viene classificato usando regole predefinite e pattern appresi
                    </p>
                  </div>
                  <div
                    style={{
                      padding: 16,
                      background: COLORS.warningLight,
                      borderRadius: BORDER_RADIUS.md,
                    }}
                  >
                    <h4 style={{ margin: '0 0 8px 0', color: COLORS.warning, fontSize: 14 }}>
                      3. Feedback Loop
                    </h4>
                    <p style={{ margin: 0, fontSize: 13, color: COLORS.textMuted }}>
                      Quando correggi una classificazione, il sistema apprende e migliora
                    </p>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* === TAB: LEARNING UNIVERSALE === */}
      {activeTab === 'universale' && (
        <Suspense
          fallback={
            <div style={{ textAlign: 'center', padding: 60, color: COLORS.textMuted }}>
              <RefreshCw
                size={32}
                style={{ margin: '0 auto 12px', animation: 'spin 1s linear infinite' }}
              />
              <p>Caricamento Training Universale...</p>
            </div>
          }
        >
          <LearningUniversaleLazy />
        </Suspense>
      )}

      {/* === TAB: REGOLE CATEGORIZZAZIONE === */}
      {activeTab === 'regole' && (
        <Suspense
          fallback={
            <div style={{ textAlign: 'center', padding: 60, color: COLORS.textMuted }}>
              <RefreshCw
                size={32}
                style={{ margin: '0 auto 12px', animation: 'spin 1s linear infinite' }}
              />
              <p>Caricamento Regole...</p>
            </div>
          }
        >
          <RegoleCategorizzazioneLazy />
        </Suspense>
      )}
    </div>
  );
}
