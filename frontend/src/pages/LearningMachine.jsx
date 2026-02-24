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

import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';
import { formatEuro, formatDateIT, STYLES, COLORS, button, badge } from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { 
  Brain, RefreshCw, CheckCircle, AlertCircle, Tag, ChevronRight, 
  Lightbulb, TrendingUp, FileText, CreditCard, BarChart3, Zap,
  Trash2, Settings, Search, Filter, Download, Play, Pause
} from 'lucide-react';

// ============================================================
// COMPONENTI RIUTILIZZABILI
// ============================================================

function StatCard({ icon: Icon, label, value, subValue, color, bgGradient }) {
  return (
    <div style={{ 
      background: bgGradient || 'linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)', 
      borderRadius: 12, 
      padding: 20, 
      border: `1px solid ${color}20`
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        {Icon && <Icon size={18} color={color} />}
        <span style={{ fontSize: 12, color: '#6080a0' }}>{label}</span>
      </div>
      <div style={{ fontSize: 28, fontWeight: 'bold', color: color || '#1f2937' }}>
        {value}
      </div>
      {subValue && (
        <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 4 }}>{subValue}</div>
      )}
    </div>
  );
}

function MessageBanner({ message, onClose }) {
  if (!message) return null;
  
  const isSuccess = message.type === 'success';
  return (
    <div style={{
      background: isSuccess ? '#dcfce7' : '#fee2e2',
      border: `1px solid ${isSuccess ? '#86efac' : '#fecaca'}`,
      borderRadius: 12, 
      padding: 12, 
      marginBottom: 16,
      display: 'flex', 
      alignItems: 'center', 
      gap: 8
    }}>
      {isSuccess ? 
        <CheckCircle size={18} color="#16a34a" /> : 
        <AlertCircle size={18} color="#dc2626" />
      }
      <span style={{ color: isSuccess ? '#166534' : '#991b1b', fontWeight: 500 }}>
        {message.text}
      </span>
      <button 
        onClick={onClose} 
        style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', fontSize: 18 }}
      >
        ×
      </button>
    </div>
  );
}

function LoadingSpinner({ text = 'Caricamento...' }) {
  return (
    <div style={{ textAlign: 'center', padding: 60, color: '#6080a0' }}>
      <RefreshCw size={32} className="animate-spin" style={{ margin: '0 auto 12px' }} />
      <p>{text}</p>
    </div>
  );
}

// ============================================================
// COMPONENTE PRINCIPALE
// ============================================================

export default function LearningMachine() {
  // === TAB STATE ===
  const [activeTab, setActiveTab] = useState('fornitori');
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
        api.get('/api/fornitori-learning/centri-costo-disponibili')
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
        api.get('/api/learning-machine/stats').catch(() => ({ data: null })),
        api.get('/api/learning-machine/regole').catch(() => ({ data: [] }))
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

  const selezionaFornitore = async (fornitore) => {
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
        keywords: keywords.split(',').map(k => k.trim()).filter(k => k),
        centro_costo_suggerito: centroCostoSuggerito || null
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

  const eliminaFornitoreKeywords = async (fornitoreId) => {
    if (!window.confirm('Eliminare questa configurazione?')) return;
    
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
        setMessage({ type: 'success', text: `Riclassificate ${res.data.totale_riclassificate} fatture!` });
        loadFornitoriData();
        loadDashboardStats();
      }
    } catch (error) {
      setMessage({ type: 'error', text: 'Errore riclassificazione' });
    }
    setFornitoriLoading(false);
  };

  const aggiungiKeywordSuggerita = (keyword) => {
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
      setMessage({ type: 'success', text: `Appresi ${res.data.pattern_appresi || 0} nuovi pattern!` });
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
    { id: 'documenti', label: 'Classificazione Documenti', icon: FileText }
  ];

  // ============================================================
  // RENDER
  // ============================================================

  return (
    <div style={{ padding: 20, maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div style={{
        background: 'linear-gradient(135deg, #1535a8 0%, #2050e8 100%)',
        borderRadius: 12,
        padding: 24,
        marginBottom: 20,
        color: 'white'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16 }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 24, fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: 12 }}>
              <Brain size={28} /> Learning Machine
            </h1>
            <p style={{ margin: '8px 0 0 0', opacity: 0.9, fontSize: 14 }}>
              Sistema di apprendimento automatico per classificazione e associazione
            </p>
          </div>
          <div style={{ 
            background: 'rgba(255,255,255,0.15)', 
            padding: '8px 16px', 
            borderRadius: 8,
            display: 'flex',
            alignItems: 'center',
            gap: 8
          }}>
            <Zap size={18} />
            <span style={{ fontWeight: 600 }}>Sistema Attivo</span>
          </div>
        </div>
      </div>

      {/* Messaggio globale */}
      <MessageBanner message={message} onClose={() => setMessage(null)} />

      {/* Tabs */}
      <div style={{ 
        display: 'flex', 
        gap: 4, 
        marginBottom: 20, 
        background: '#f1f5f9', 
        padding: 4, 
        borderRadius: 10 
      }}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              flex: 1,
              padding: '12px 16px',
              border: 'none',
              borderRadius: 8,
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: 13,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              background: activeTab === tab.id ? 'white' : 'transparent',
              color: activeTab === tab.id ? '#1535a8' : '#64748b',
              boxShadow: activeTab === tab.id ? '0 2px 4px rgba(0,0,0,0.1)' : 'none',
              transition: 'all 0.2s'
            }}
          >
            <tab.icon size={16} />
            {tab.label}
          </button>
        ))}
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
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 24 }}>
                <StatCard 
                  icon={Tag}
                  label="Fornitori Configurati"
                  value={dashboardStats?.fornitori_con_keywords || 0}
                  subValue={`${dashboardStats?.copertura_fornitori || 0}% copertura`}
                  color="#16a34a"
                  bgGradient="linear-gradient(135deg, #dcfce7 0%, #f0fdf4 100%)"
                />
                <StatCard 
                  icon={FileText}
                  label="Fatture Classificate"
                  value={`${dashboardStats?.percentuale_fatture || 0}%`}
                  subValue={`${dashboardStats?.fatture_classificate || 0}/${dashboardStats?.totale_fatture || 0}`}
                  color="#1535a8"
                  bgGradient="linear-gradient(135deg, #dbeafe 0%, #eff6ff 100%)"
                />
                <StatCard 
                  icon={CreditCard}
                  label="Pattern Assegni"
                  value={assegniStats?.pattern_totali || 0}
                  subValue={`${assegniStats?.accuracy || 0}% accuracy`}
                  color="#9333ea"
                  bgGradient="linear-gradient(135deg, #f3e8ff 0%, #faf5ff 100%)"
                />
                <StatCard 
                  icon={TrendingUp}
                  label="F24 Classificati"
                  value={`${dashboardStats?.percentuale_f24 || 0}%`}
                  subValue={`${dashboardStats?.f24_classificati || 0}/${dashboardStats?.totale_f24 || 0}`}
                  color="#f59e0b"
                  bgGradient="linear-gradient(135deg, #fef3c7 0%, #fffbeb 100%)"
                />
              </div>

              {/* Quick Actions */}
              <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}>
                <h3 style={{ margin: '0 0 16px 0', fontSize: 16, fontWeight: 600, color: '#1535a8' }}>
                  Azioni Rapide
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
                  <button
                    onClick={() => { setActiveTab('fornitori'); riclassificaFatture(); }}
                    style={{
                      padding: 16,
                      background: 'linear-gradient(135deg, #1535a8 0%, #2050e8 100%)',
                      color: 'white',
                      border: 'none',
                      borderRadius: 10,
                      cursor: 'pointer',
                      fontWeight: 600,
                      fontSize: 13,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8
                    }}
                  >
                    <Play size={18} /> Riclassifica Tutte le Fatture
                  </button>
                  <button
                    onClick={() => { setActiveTab('assegni'); handleLearnAssegni(); }}
                    style={{
                      padding: 16,
                      background: 'linear-gradient(135deg, #ec4899 0%, #8b5cf6 100%)',
                      color: 'white',
                      border: 'none',
                      borderRadius: 10,
                      cursor: 'pointer',
                      fontWeight: 600,
                      fontSize: 13,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8
                    }}
                  >
                    <Brain size={18} /> Apprendi Pattern Assegni
                  </button>
                  <button
                    onClick={loadDashboardStats}
                    style={{
                      padding: 16,
                      background: '#f1f5f9',
                      color: '#374151',
                      border: '1px solid #dce8f4',
                      borderRadius: 10,
                      cursor: 'pointer',
                      fontWeight: 600,
                      fontSize: 13,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8
                    }}
                  >
                    <RefreshCw size={18} /> Aggiorna Statistiche
                  </button>
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
          <div style={{
            background: 'white',
            borderRadius: 12,
            padding: 20,
            marginBottom: 16,
            boxShadow: '0 2px 8px rgba(0,0,0,0.08)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
              <div>
                <h2 style={{ margin: 0, fontSize: 18, fontWeight: 'bold', color: '#1535a8' }}>
                  Classificazione Fornitori
                </h2>
                <p style={{ color: '#6080a0', fontSize: 13, margin: '4px 0 0 0' }}>
                  Configura keywords per classificare automaticamente i fornitori nei centri di costo
                </p>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button 
                  onClick={loadFornitoriData} 
                  disabled={fornitoriLoading}
                  style={{ ...button('secondary'), opacity: fornitoriLoading ? 0.6 : 1 }}
                >
                  <RefreshCw size={16} className={fornitoriLoading ? 'animate-spin' : ''} />
                  Aggiorna
                </button>
                <button 
                  onClick={riclassificaFatture} 
                  disabled={fornitoriLoading || fornitoriConfigurati.length === 0}
                  style={{ 
                    ...button('primary'),
                    background: 'linear-gradient(135deg, #1535a8 0%, #2050e8 100%)',
                    opacity: fornitoriConfigurati.length === 0 ? 0.5 : 1
                  }}
                >
                  <CheckCircle size={16} />
                  Riclassifica Fatture
                </button>
              </div>
            </div>
          </div>

          {/* Stats */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 20 }}>
            <StatCard 
              icon={AlertCircle}
              label="Da Classificare"
              value={fornitoriNonClassificati.length}
              color="#f59e0b"
              bgGradient="linear-gradient(135deg, #fef3c7 0%, #fffbeb 100%)"
            />
            <StatCard 
              icon={CheckCircle}
              label="Configurati"
              value={fornitoriConfigurati.length}
              color="#16a34a"
              bgGradient="linear-gradient(135deg, #dcfce7 0%, #f0fdf4 100%)"
            />
            <StatCard 
              icon={Tag}
              label="Centri di Costo"
              value={centriCosto.length}
              color="#1535a8"
              bgGradient="linear-gradient(135deg, #dbeafe 0%, #eff6ff 100%)"
            />
          </div>

          {fornitoriLoading ? (
            <LoadingSpinner />
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              {/* Lista fornitori non classificati */}
              <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}>
                <h3 style={{ margin: '0 0 16px 0', fontSize: 16, fontWeight: 600, color: '#1535a8', display: 'flex', alignItems: 'center', gap: 8 }}>
                  <AlertCircle size={18} color="#f59e0b" /> Da Classificare ({fornitoriNonClassificati.length})
                </h3>
                
                <div style={{ maxHeight: 500, overflowY: 'auto' }}>
                  {fornitoriNonClassificati.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: 40, color: '#6080a0' }}>
                      <CheckCircle size={48} color="#16a34a" style={{ marginBottom: 12 }} />
                      <p>Tutti i fornitori sono classificati!</p>
                    </div>
                  ) : (
                    fornitoriNonClassificati.map((f, idx) => (
                      <div 
                        key={idx}
                        onClick={() => selezionaFornitore(f)}
                        style={{
                          padding: 12,
                          borderRadius: 8,
                          marginBottom: 8,
                          cursor: 'pointer',
                          background: selectedFornitore?.fornitore_nome === f.fornitore_nome ? '#e0e7ff' : '#f2f6fd',
                          border: selectedFornitore?.fornitore_nome === f.fornitore_nome ? '2px solid #4f46e5' : '1px solid #dce8f4',
                          transition: 'all 0.2s'
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div>
                            <p style={{ fontWeight: 600, color: '#1f2937', margin: 0, fontSize: 14 }}>{f.fornitore_nome}</p>
                            <p style={{ color: '#6080a0', fontSize: 12, margin: '4px 0 0 0' }}>
                              {f.fatture_count} fatture • {formatEuro(f.totale_fatture || 0)}
                            </p>
                          </div>
                          <ChevronRight size={16} color="#9ca3af" />
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Form configurazione */}
              <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}>
                <h3 style={{ margin: '0 0 16px 0', fontSize: 16, fontWeight: 600, color: '#1535a8', display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Tag size={18} color="#1535a8" /> Configura Keywords
                </h3>

                {selectedFornitore ? (
                  <div>
                    <div style={{ background: '#f0f9ff', borderRadius: 8, padding: 12, marginBottom: 16 }}>
                      <p style={{ margin: 0, fontWeight: 600, color: '#0369a1' }}>{selectedFornitore.fornitore_nome}</p>
                      <p style={{ margin: '4px 0 0 0', fontSize: 12, color: '#0284c7' }}>
                        {selectedFornitore.fatture_count} fatture • {formatEuro(selectedFornitore.totale_fatture || 0)}
                      </p>
                    </div>

                    {/* Keywords suggerite */}
                    {keywordsSuggerite.length > 0 && (
                      <div style={{ marginBottom: 16 }}>
                        <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 8 }}>
                          Keywords Suggerite (clicca per aggiungere)
                        </label>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                          {keywordsSuggerite.map((kw, idx) => (
                            <button
                              key={idx}
                              onClick={() => aggiungiKeywordSuggerita(kw)}
                              style={{
                                padding: '4px 10px',
                                background: '#e0e7ff',
                                color: '#4338ca',
                                border: 'none',
                                borderRadius: 6,
                                cursor: 'pointer',
                                fontSize: 12,
                                fontWeight: 500
                              }}
                            >
                              + {kw}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Input keywords */}
                    <div style={{ marginBottom: 16 }}>
                      <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 6 }}>
                        Keywords (separate da virgola)
                      </label>
                      <input
                        type="text"
                        value={keywords}
                        onChange={(e) => setKeywords(e.target.value)}
                        placeholder="es: bar, caffè, tabacchi"
                        style={{
                          width: '100%',
                          padding: '10px 12px',
                          border: '2px solid #dce8f4',
                          borderRadius: 8,
                          fontSize: 14
                        }}
                      />
                    </div>

                    {/* Select centro costo */}
                    <div style={{ marginBottom: 16 }}>
                      <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 6 }}>
                        Centro di Costo Suggerito
                      </label>
                      <select
                        value={centroCostoSuggerito}
                        onChange={(e) => setCentroCostoSuggerito(e.target.value)}
                        style={{
                          width: '100%',
                          padding: '10px 12px',
                          border: '2px solid #dce8f4',
                          borderRadius: 8,
                          fontSize: 14,
                          background: 'white'
                        }}
                      >
                        <option value="">-- Seleziona --</option>
                        {centriCosto.map(cdc => (
                          <option key={cdc.id || cdc.codice} value={cdc.id || cdc.codice}>
                            {cdc.nome || cdc.descrizione}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Bottoni */}
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button
                        onClick={salvaFornitore}
                        disabled={saving || !keywords.trim()}
                        style={{
                          ...button('primary'),
                          flex: 1,
                          justifyContent: 'center',
                          opacity: saving || !keywords.trim() ? 0.6 : 1
                        }}
                      >
                        {saving ? 'Salvataggio...' : 'Salva Keywords'}
                      </button>
                      <button
                        onClick={() => setSelectedFornitore(null)}
                        style={{ ...button('secondary') }}
                      >
                        Annulla
                      </button>
                    </div>
                  </div>
                ) : (
                  <div style={{ textAlign: 'center', padding: 40, color: '#6080a0' }}>
                    <Lightbulb size={48} color="#dce8f4" style={{ marginBottom: 12 }} />
                    <p>Seleziona un fornitore dalla lista per configurare le keywords</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Lista fornitori configurati */}
          {fornitoriConfigurati.length > 0 && (
            <div style={{ background: 'white', borderRadius: 12, padding: 20, marginTop: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}>
              <h3 style={{ margin: '0 0 16px 0', fontSize: 16, fontWeight: 600, color: '#1535a8', display: 'flex', alignItems: 'center', gap: 8 }}>
                <CheckCircle size={18} color="#16a34a" /> Fornitori Configurati ({fornitoriConfigurati.length})
              </h3>
              
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
                {fornitoriConfigurati.map((f, idx) => (
                  <div key={idx} style={{
                    padding: 12,
                    background: '#f2f6fd',
                    borderRadius: 8,
                    border: '1px solid #dce8f4'
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <div>
                        <p style={{ fontWeight: 600, color: '#1f2937', margin: 0, fontSize: 14 }}>{f.fornitore_nome}</p>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
                          {(f.keywords || []).map((kw, i) => (
                            <span key={i} style={{
                              padding: '2px 8px',
                              background: '#dbeafe',
                              color: '#1535a8',
                              borderRadius: 4,
                              fontSize: 11
                            }}>
                              {kw}
                            </span>
                          ))}
                        </div>
                      </div>
                      <button
                        onClick={() => eliminaFornitoreKeywords(f.id)}
                        style={{
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          color: '#ef4444',
                          padding: 4
                        }}
                      >
                        <Trash2 size={16} />
                      </button>
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
          <div style={{
            background: 'white',
            borderRadius: 12,
            padding: 20,
            marginBottom: 16,
            boxShadow: '0 2px 8px rgba(0,0,0,0.08)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
              <div>
                <h2 style={{ margin: 0, fontSize: 18, fontWeight: 'bold', color: '#1535a8' }}>
                  Pattern Assegni
                </h2>
                <p style={{ color: '#6080a0', fontSize: 13, margin: '4px 0 0 0' }}>
                  Apprende dalle associazioni esistenti per suggerire automaticamente beneficiari
                </p>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button 
                  onClick={loadAssegniStats} 
                  disabled={assegniLoading}
                  style={{ ...button('secondary'), opacity: assegniLoading ? 0.6 : 1 }}
                >
                  <RefreshCw size={16} className={assegniLoading ? 'animate-spin' : ''} />
                  Aggiorna
                </button>
              </div>
            </div>
          </div>

          {/* Stats Assegni */}
          {assegniStats && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16, marginBottom: 20 }}>
              <StatCard 
                icon={Brain}
                label="Pattern Appresi"
                value={assegniStats.pattern_totali || 0}
                color="#9333ea"
              />
              <StatCard 
                icon={CheckCircle}
                label="Accuracy"
                value={`${assegniStats.accuracy || 0}%`}
                color="#16a34a"
              />
              <StatCard 
                icon={CreditCard}
                label="Assegni Totali"
                value={assegniStats.totale_assegni || 0}
                color="#1535a8"
              />
              <StatCard 
                icon={AlertCircle}
                label="Non Associati"
                value={assegniStats.non_associati || 0}
                color="#f59e0b"
              />
            </div>
          )}

          {/* Azioni */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
            {/* Card: Apprendi */}
            <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}>
              <h3 style={{ margin: '0 0 12px 0', fontSize: 16, fontWeight: 600, color: '#1535a8', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Brain size={18} color="#9333ea" /> Apprendi Pattern
              </h3>
              <p style={{ color: '#6080a0', fontSize: 13, marginBottom: 16 }}>
                Analizza le associazioni esistenti tra assegni e fatture per apprendere nuovi pattern.
              </p>
              <button
                onClick={handleLearnAssegni}
                disabled={assegniLoading}
                style={{
                  ...button('primary'),
                  width: '100%',
                  justifyContent: 'center',
                  background: 'linear-gradient(135deg, #9333ea 0%, #7c3aed 100%)'
                }}
              >
                <Brain size={16} /> {assegniLoading ? 'Apprendimento...' : 'Avvia Learning'}
              </button>
              
              {learningResult && (
                <div style={{ marginTop: 12, padding: 12, background: '#f3e8ff', borderRadius: 8 }}>
                  <p style={{ margin: 0, fontSize: 13, color: '#7c3aed' }}>
                    ✅ Appresi <strong>{learningResult.pattern_appresi}</strong> pattern da {learningResult.assegni_analizzati} assegni
                  </p>
                </div>
              )}
            </div>

            {/* Card: Associa Intelligente */}
            <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}>
              <h3 style={{ margin: '0 0 12px 0', fontSize: 16, fontWeight: 600, color: '#1535a8', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Zap size={18} color="#f59e0b" /> Associazione Intelligente
              </h3>
              <p style={{ color: '#6080a0', fontSize: 13, marginBottom: 16 }}>
                Usa i pattern appresi per associare automaticamente gli assegni alle fatture.
              </p>
              <button
                onClick={handleAssociaIntelligente}
                disabled={assegniLoading}
                style={{
                  ...button('primary'),
                  width: '100%',
                  justifyContent: 'center',
                  background: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)'
                }}
              >
                <Zap size={16} /> {assegniLoading ? 'Associazione...' : 'Associa Automaticamente'}
              </button>
            </div>

            {/* Card: Pulizia Duplicati */}
            <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}>
              <h3 style={{ margin: '0 0 12px 0', fontSize: 16, fontWeight: 600, color: '#1535a8', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Trash2 size={18} color="#ef4444" /> Pulizia Duplicati
              </h3>
              <p style={{ color: '#6080a0', fontSize: 13, marginBottom: 16 }}>
                Trova e rimuove assegni duplicati dal database.
              </p>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  onClick={() => handlePuliziaDuplicati(true)}
                  disabled={assegniLoading}
                  style={{ ...button('secondary'), flex: 1, justifyContent: 'center' }}
                >
                  Anteprima
                </button>
                <button
                  onClick={() => handlePuliziaDuplicati(false)}
                  disabled={assegniLoading || !puliziaResult}
                  style={{ ...button('danger'), flex: 1, justifyContent: 'center' }}
                >
                  Elimina
                </button>
              </div>
              
              {puliziaResult && (
                <div style={{ marginTop: 12, padding: 12, background: '#fee2e2', borderRadius: 8 }}>
                  <p style={{ margin: 0, fontSize: 13, color: '#991b1b' }}>
                    Trovati <strong>{puliziaResult.duplicati_trovati || 0}</strong> duplicati
                    {puliziaResult.record_eliminati > 0 && ` - Eliminati: ${puliziaResult.record_eliminati}`}
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
          <div style={{
            background: 'white',
            borderRadius: 12,
            padding: 20,
            marginBottom: 16,
            boxShadow: '0 2px 8px rgba(0,0,0,0.08)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
              <div>
                <h2 style={{ margin: 0, fontSize: 18, fontWeight: 'bold', color: '#1535a8' }}>
                  Classificazione Documenti
                </h2>
                <p style={{ color: '#6080a0', fontSize: 13, margin: '4px 0 0 0' }}>
                  Sistema di classificazione automatica documenti con apprendimento iterativo
                </p>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button 
                  onClick={loadDocumentiStats} 
                  disabled={documentiLoading}
                  style={{ ...button('secondary'), opacity: documentiLoading ? 0.6 : 1 }}
                >
                  <RefreshCw size={16} className={documentiLoading ? 'animate-spin' : ''} />
                  Aggiorna
                </button>
                <Link to="/classificazione-email" style={{ ...button('primary'), textDecoration: 'none' }}>
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
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 20 }}>
                  <StatCard 
                    icon={FileText}
                    label="Documenti Classificati"
                    value={documentiStats.totale_classificati || 0}
                    color="#1535a8"
                  />
                  <StatCard 
                    icon={Brain}
                    label="Regole Apprese"
                    value={regoleApprese.length}
                    color="#9333ea"
                  />
                  <StatCard 
                    icon={CheckCircle}
                    label="Accuracy Media"
                    value={`${documentiStats.accuracy || 0}%`}
                    color="#16a34a"
                  />
                  <StatCard 
                    icon={TrendingUp}
                    label="Feedback Ricevuti"
                    value={documentiStats.feedback_count || 0}
                    color="#f59e0b"
                  />
                </div>
              )}

              {/* Info */}
              <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}>
                <h3 style={{ margin: '0 0 16px 0', fontSize: 16, fontWeight: 600, color: '#1535a8' }}>
                  Come Funziona
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: 16 }}>
                  <div style={{ padding: 16, background: '#f0f9ff', borderRadius: 8 }}>
                    <h4 style={{ margin: '0 0 8px 0', color: '#0369a1', fontSize: 14 }}>1. Scansione Email</h4>
                    <p style={{ margin: 0, fontSize: 13, color: '#6080a0' }}>
                      Il sistema scansiona le email e identifica automaticamente il tipo di documento (F24, fattura, cedolino, etc.)
                    </p>
                  </div>
                  <div style={{ padding: 16, background: '#f0fdf4', borderRadius: 8 }}>
                    <h4 style={{ margin: '0 0 8px 0', color: '#166534', fontSize: 14 }}>2. Classificazione</h4>
                    <p style={{ margin: 0, fontSize: 13, color: '#6080a0' }}>
                      Ogni documento viene classificato usando regole predefinite e pattern appresi
                    </p>
                  </div>
                  <div style={{ padding: 16, background: '#fef3c7', borderRadius: 8 }}>
                    <h4 style={{ margin: '0 0 8px 0', color: '#92400e', fontSize: 14 }}>3. Feedback Loop</h4>
                    <p style={{ margin: 0, fontSize: 13, color: '#6080a0' }}>
                      Quando correggi una classificazione, il sistema apprende e migliora
                    </p>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
