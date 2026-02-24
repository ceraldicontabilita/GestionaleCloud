import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro } from '../lib/utils';
import { PageLayout, PageSection, PageGrid, PageLoading } from '../components/PageLayout';
import { FileText, Download, TrendingUp, TrendingDown, Scale } from 'lucide-react';

export default function Bilancio() {
  const { anno } = useAnnoGlobale();
  const [statoPatrimoniale, setStatoPatrimoniale] = useState(null);
  const [contoEconomico, setContoEconomico] = useState(null);
  const [loading, setLoading] = useState(true);
  const [mese, setMese] = useState(null);
  const navigate = useNavigate();
  const location = useLocation();
  
  const getTabFromPath = () => {
    const match = location.pathname.match(/\/bilancio\/([\w-]+)/);
    return match ? match[1] : 'patrimoniale';
  };
  
  const [activeTab, setActiveTab] = useState(getTabFromPath());
  
  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    navigate(`/bilancio/${tabId}`);
  };
  
  useEffect(() => {
    const tab = getTabFromPath();
    if (tab !== activeTab) setActiveTab(tab);
  }, [location.pathname]);

  const mesi = [
    { value: null, label: 'Anno intero' },
    { value: 1, label: 'Gennaio' }, { value: 2, label: 'Febbraio' }, { value: 3, label: 'Marzo' },
    { value: 4, label: 'Aprile' }, { value: 5, label: 'Maggio' }, { value: 6, label: 'Giugno' },
    { value: 7, label: 'Luglio' }, { value: 8, label: 'Agosto' }, { value: 9, label: 'Settembre' },
    { value: 10, label: 'Ottobre' }, { value: 11, label: 'Novembre' }, { value: 12, label: 'Dicembre' },
  ];

  useEffect(() => { loadBilancio(); }, [anno, mese]);

  const loadBilancio = async () => {
    try {
      setLoading(true);
      const [spRes, ceRes] = await Promise.all([
        api.get(`/api/bilancio/stato-patrimoniale?anno=${anno}${mese ? `&mese=${mese}` : ''}`),
        api.get(`/api/bilancio/conto-economico?anno=${anno}${mese ? `&mese=${mese}` : ''}`)
      ]);
      setStatoPatrimoniale(spRes.data);
      setContoEconomico(ceRes.data);
    } catch (error) {
      console.error('Errore caricamento bilancio:', error);
    } finally {
      setLoading(false);
    }
  };

  const StatoPatrimonialeView = () => {
    if (!statoPatrimoniale) return null;
    const { attivo, passivo } = statoPatrimoniale;
    return (
      <PageGrid cols={2} gap={24}>
        {/* ATTIVO */}
        <div style={{ background: '#f0fdf4', borderRadius: 12, padding: 24 }}>
          <h3 style={{ color: '#166534', marginBottom: 20, borderBottom: '2px solid #22c55e', paddingBottom: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
            <TrendingUp size={20} /> ATTIVO
          </h3>
          <div style={{ marginBottom: 20 }}>
            <h4 style={{ color: '#15803d', fontSize: 14, marginBottom: 12 }}>Disponibilità Liquide</h4>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <tbody>
                <tr><td style={{ padding: '8px 0', color: '#374151' }}>Cassa</td><td style={{ padding: '8px 0', textAlign: 'right', fontWeight: 500 }}>{formatEuro(attivo.disponibilita_liquide.cassa)}</td></tr>
                <tr><td style={{ padding: '8px 0', color: '#374151' }}>Banca</td><td style={{ padding: '8px 0', textAlign: 'right', fontWeight: 500 }}>{formatEuro(attivo.disponibilita_liquide.banca)}</td></tr>
                <tr style={{ borderTop: '1px solid #86efac' }}><td style={{ padding: '8px 0', fontWeight: 600 }}>Totale</td><td style={{ padding: '8px 0', textAlign: 'right', fontWeight: 600 }}>{formatEuro(attivo.disponibilita_liquide.totale)}</td></tr>
              </tbody>
            </table>
          </div>
          <div style={{ marginBottom: 20 }}>
            <h4 style={{ color: '#15803d', fontSize: 14, marginBottom: 12 }}>Crediti</h4>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <tbody><tr><td style={{ padding: '8px 0', color: '#374151' }}>Crediti vs Clienti</td><td style={{ padding: '8px 0', textAlign: 'right', fontWeight: 500 }}>{formatEuro(attivo.crediti.crediti_vs_clienti)}</td></tr></tbody>
            </table>
          </div>
          <div style={{ marginTop: 20, padding: 16, background: '#22c55e', color: 'white', borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 18, fontWeight: 600 }}>TOTALE ATTIVO</span>
            <span style={{ fontSize: 24, fontWeight: 700 }}>{formatEuro(attivo.totale_attivo)}</span>
          </div>
        </div>

        {/* PASSIVO */}
        <div style={{ background: '#fef2f2', borderRadius: 12, padding: 24 }}>
          <h3 style={{ color: '#991b1b', marginBottom: 20, borderBottom: '2px solid #ef4444', paddingBottom: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
            <TrendingDown size={20} /> PASSIVO
          </h3>
          <div style={{ marginBottom: 20 }}>
            <h4 style={{ color: '#b91c1c', fontSize: 14, marginBottom: 12 }}>Debiti</h4>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <tbody><tr><td style={{ padding: '8px 0', color: '#374151' }}>Debiti vs Fornitori</td><td style={{ padding: '8px 0', textAlign: 'right', fontWeight: 500 }}>{formatEuro(passivo.debiti.debiti_vs_fornitori)}</td></tr></tbody>
            </table>
          </div>
          <div style={{ marginBottom: 20 }}>
            <h4 style={{ color: '#15803d', fontSize: 14, marginBottom: 12 }}>Patrimonio Netto</h4>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <tbody><tr><td style={{ padding: '8px 0', color: '#374151' }}>Capitale</td><td style={{ padding: '8px 0', textAlign: 'right', fontWeight: 600, color: passivo.patrimonio_netto >= 0 ? '#16a34a' : '#dc2626' }}>{formatEuro(passivo.patrimonio_netto)}</td></tr></tbody>
            </table>
          </div>
          <div style={{ marginTop: 20, padding: 16, background: '#ef4444', color: 'white', borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 18, fontWeight: 600 }}>TOTALE PASSIVO</span>
            <span style={{ fontSize: 24, fontWeight: 700 }}>{formatEuro(passivo.totale_passivo)}</span>
          </div>
        </div>
      </PageGrid>
    );
  };

  const ContoEconomicoView = () => {
    if (!contoEconomico) return null;
    const { ricavi, costi, risultato } = contoEconomico;
    const isProfit = risultato.utile_perdita >= 0;
    return (
      <div style={{ maxWidth: 800, margin: '0 auto' }}>
        {/* RICAVI */}
        <div style={{ background: '#f0fdf4', borderRadius: 12, padding: 24, marginBottom: 20 }}>
          <h3 style={{ color: '#166534', marginBottom: 20, borderBottom: '2px solid #22c55e', paddingBottom: 10 }}>RICAVI (Vendite al Pubblico)</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <tbody>
              <tr><td style={{ padding: '12px 0', color: '#374151', fontSize: 15 }}>Corrispettivi (Imponibile)</td><td style={{ padding: '12px 0', textAlign: 'right', fontWeight: 500, fontSize: 16 }}>{formatEuro(ricavi.corrispettivi)}</td></tr>
              {ricavi.corrispettivi_lordi && <tr><td style={{ padding: '12px 0', color: '#6080a0', fontSize: 13, fontStyle: 'italic' }}>(Lordo incl. IVA: {formatEuro(ricavi.corrispettivi_lordi)})</td><td></td></tr>}
              <tr style={{ borderTop: '2px solid #22c55e', background: '#dcfce7' }}><td style={{ padding: '12px 0', fontWeight: 700, fontSize: 16 }}>TOTALE RICAVI</td><td style={{ padding: '12px 0', textAlign: 'right', fontWeight: 700, fontSize: 18, color: '#16a34a' }}>{formatEuro(ricavi.totale_ricavi)}</td></tr>
            </tbody>
          </table>
        </div>

        {/* COSTI */}
        <div style={{ background: '#fef2f2', borderRadius: 12, padding: 24, marginBottom: 20 }}>
          <h3 style={{ color: '#991b1b', marginBottom: 20, borderBottom: '2px solid #ef4444', paddingBottom: 10 }}>COSTI (Fatture Ricevute da Fornitori)</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <tbody>
              <tr><td style={{ padding: '12px 0', color: '#374151', fontSize: 15 }}>Acquisti (Imponibile)</td><td style={{ padding: '12px 0', textAlign: 'right', fontWeight: 500, fontSize: 16 }}>{formatEuro(costi.acquisti)}</td></tr>
              {costi.note_credito > 0 && <tr><td style={{ padding: '12px 0', color: '#16a34a', fontSize: 15 }}>- Note di Credito Ricevute</td><td style={{ padding: '12px 0', textAlign: 'right', fontWeight: 500, fontSize: 16, color: '#16a34a' }}>-{formatEuro(costi.note_credito)}</td></tr>}
              <tr style={{ borderTop: '2px solid #ef4444', background: '#fee2e2' }}><td style={{ padding: '12px 0', fontWeight: 700, fontSize: 16 }}>TOTALE COSTI (Netto)</td><td style={{ padding: '12px 0', textAlign: 'right', fontWeight: 700, fontSize: 18, color: '#dc2626' }}>{formatEuro(costi.totale_costi)}</td></tr>
            </tbody>
          </table>
        </div>

        {/* RISULTATO */}
        <div style={{ background: isProfit ? 'linear-gradient(135deg, #166534, #22c55e)' : 'linear-gradient(135deg, #991b1b, #ef4444)', borderRadius: 16, padding: 32, color: 'white', textAlign: 'center' }}>
          <div style={{ fontSize: 14, opacity: 0.9, marginBottom: 8 }}>{isProfit ? 'UTILE DI ESERCIZIO' : 'PERDITA DI ESERCIZIO'}</div>
          <div style={{ fontSize: 42, fontWeight: 700 }}>{formatEuro(Math.abs(risultato.utile_perdita))}</div>
          <div style={{ marginTop: 16, padding: '8px 16px', background: 'rgba(255,255,255,0.2)', borderRadius: 20, display: 'inline-block', fontSize: 13 }}>Margine: {risultato.margine_percentuale}%</div>
        </div>
      </div>
    );
  };

  return (
    <PageLayout
      title="Bilancio"
      icon={<Scale size={28} />}
      subtitle={`Stato Patrimoniale e Conto Economico - Anno ${anno}`}
      actions={
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <select value={mese || ''} onChange={(e) => setMese(e.target.value ? parseInt(e.target.value) : null)} data-testid="bilancio-mese-select"
            style={{ padding: '10px 16px', borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 14, fontWeight: 500, cursor: 'pointer' }}>
            {mesi.map(m => (<option key={m.label} value={m.value || ''}>{m.label}</option>))}
          </select>
          <button onClick={() => window.open(`${api.defaults.baseURL}/api/bilancio/export-pdf?anno=${anno}`, '_blank')} data-testid="export-pdf-btn"
            style={{ padding: '10px 20px', borderRadius: 8, border: 'none', background: '#1e293b', color: 'white', fontSize: 14, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>
            <Download size={16} /> PDF {anno}
          </button>
          <button onClick={() => window.open(`${api.defaults.baseURL}/api/bilancio/export/pdf/confronto?anno_corrente=${anno}&anno_precedente=${anno - 1}`, '_blank')} data-testid="export-confronto-pdf-btn"
            style={{ padding: '10px 20px', borderRadius: 8, border: 'none', background: '#7c3aed', color: 'white', fontSize: 14, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>
            <FileText size={16} /> Confronto {anno - 1}/{anno}
          </button>
        </div>
      }
    >
      {/* Tabs */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 24, borderBottom: '2px solid #e2e8f0' }}>
        <button onClick={() => handleTabChange('patrimoniale')} data-testid="tab-stato-patrimoniale"
          style={{ padding: '14px 28px', border: 'none', background: activeTab === 'patrimoniale' ? '#1e293b' : 'transparent', color: activeTab === 'patrimoniale' ? 'white' : '#64748b', fontSize: 15, fontWeight: 600, cursor: 'pointer', borderRadius: '8px 8px 0 0' }}>
          Stato Patrimoniale
        </button>
        <button onClick={() => handleTabChange('economico')} data-testid="tab-conto-economico"
          style={{ padding: '14px 28px', border: 'none', background: activeTab === 'economico' ? '#1e293b' : 'transparent', color: activeTab === 'economico' ? 'white' : '#64748b', fontSize: 15, fontWeight: 600, cursor: 'pointer', borderRadius: '8px 8px 0 0' }}>
          Conto Economico
        </button>
      </div>

      {loading ? (
        <PageLoading message="Caricamento bilancio..." />
      ) : (
        <>
          {activeTab === 'patrimoniale' && <StatoPatrimonialeView />}
          {activeTab === 'economico' && <ContoEconomicoView />}
        </>
      )}

      {/* Info */}
      <PageSection title="Note" icon="ℹ️" style={{ marginTop: 30 }}>
        <p style={{ margin: 0, fontSize: 13, color: '#64748b' }}>
          I dati sono calcolati in base ai movimenti registrati in Prima Nota e alle fatture caricate.
          Lo Stato Patrimoniale mostra la situazione alla data selezionata, il Conto Economico mostra i flussi del periodo.
        </p>
      </PageSection>
    </PageLayout>
  );
}
