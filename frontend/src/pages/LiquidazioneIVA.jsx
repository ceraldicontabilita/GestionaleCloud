import React, { useState, useEffect, useCallback } from 'react';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import api from '../api';
import { formatEuro, STYLES, COLORS, button, badge } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { 
  Calculator, 
  Download, 
  RefreshCw, 
  TrendingUp, 
  TrendingDown,
  FileText,
  AlertCircle,
  CheckCircle,
  ChevronDown,
  ChevronUp
} from 'lucide-react';

const MESI = [
  '', 'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
  'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre'
];

export default function LiquidazioneIVA() {
  const { anno } = useAnnoGlobale();
  const [mese, setMese] = useState(new Date().getMonth() + 1);
  const [creditoPrecedente, setCreditoPrecedente] = useState(0);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [riepilogoAnnuale, setRiepilogoAnnuale] = useState(null);
  const [showDettaglio, setShowDettaglio] = useState(false);
  const [confronto, setConfronto] = useState({ debito: '', credito: '' });
  const [confrontoResult, setConfrontoResult] = useState(null);

  const calcolaLiquidazione = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(
        `/api/liquidazione-iva/calcola/${anno}/${mese}?credito_precedente=${creditoPrecedente}`
      );
      setResult(res.data);
    } catch (err) {
      console.error('Errore:', err);
    } finally {
      setLoading(false);
    }
  }, [anno, mese, creditoPrecedente]);

  const caricaRiepilogoAnnuale = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/api/liquidazione-iva/riepilogo-annuale/${anno}`);
      setRiepilogoAnnuale(res.data);
    } catch (err) {
      console.error('Errore:', err);
    } finally {
      setLoading(false);
    }
  };

  const eseguiConfronto = async () => {
    if (!confronto.debito || !confronto.credito) return;
    
    try {
      const res = await api.get(
        `/api/liquidazione-iva/confronto/${anno}/${mese}?iva_debito_commercialista=${confronto.debito}&iva_credito_commercialista=${confronto.credito}`
      );
      setConfrontoResult(res.data);
    } catch (err) {
      console.error('Errore:', err);
    }
  };

  const scaricaPDF = () => {
    window.open(
      `/api/liquidazione-iva/export/pdf/${anno}/${mese}?credito_precedente=${creditoPrecedente}`,
      '_blank'
    );
  };

  // Stile comune per le card
  const cardStyle = {
    background: 'white',
    borderRadius: 12,
    padding: 20,
    boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
    border: '1px solid #dce8f4',
    marginBottom: 20
  };

  return (
    <PageLayout 
      title="Liquidazione IVA" 
      icon="🧮"
      subtitle="Calcolo preciso IVA mensile per confronto con commercialista"
    >
      <div data-testid="liquidazione-iva-page">
        {/* Filtri */}
        <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.08)', border: '1px solid #dce8f4', marginBottom: 20 }}>
        <h3 style={{ margin: '0 0 16px 0', fontSize: 16, fontWeight: 'bold', color: '#1535a8', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Calculator size={18} />
          Parametri Calcolo
        </h3>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div style={{ padding: '10px 16px', background: '#dbeafe', borderRadius: 8, color: '#1535a8', fontWeight: 600, fontSize: 14, display: 'flex', alignItems: 'center', gap: 6 }}>
            📅 Anno: {anno}
          </div>
          
          <div>
            <label style={{ display: 'block', fontSize: 13, marginBottom: 4, fontWeight: 500, color: '#6080a0' }}>Mese</label>
            <select
              value={mese}
              onChange={(e) => setMese(parseInt(e.target.value))}
              style={{ padding: '10px 12px', borderRadius: 8, border: '2px solid #dce8f4', fontSize: 14, minWidth: 150, background: 'white' }}
              data-testid="select-mese"
            >
              {MESI.slice(1).map((m, i) => (
                <option key={i + 1} value={i + 1}>{m}</option>
              ))}
            </select>
          </div>
          
          <div>
            <label style={{ display: 'block', fontSize: 13, marginBottom: 4, fontWeight: 500, color: '#6080a0' }}>
              Credito Precedente (€)
            </label>
            <input
              type="number"
              value={creditoPrecedente}
              onChange={(e) => setCreditoPrecedente(parseFloat(e.target.value) || 0)}
              placeholder="0.00"
              style={{ padding: '10px 12px', borderRadius: 8, border: '2px solid #dce8f4', fontSize: 14, width: 150 }}
              data-testid="input-credito-precedente"
            />
          </div>
          
          <div style={{ display: 'flex', gap: 8 }}>
            <button 
              onClick={calcolaLiquidazione} 
              disabled={loading}
              style={{ padding: '10px 20px', background: '#15803d', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 'bold', fontSize: 14, display: 'flex', alignItems: 'center', gap: 6 }}
              data-testid="btn-calcola"
            >
              {loading ? <RefreshCw size={16} style={{ animation: 'spin 1s linear infinite' }} /> : <Calculator size={16} />}
              Calcola
            </button>
            <button 
              onClick={scaricaPDF} 
              disabled={!result}
              style={{ padding: '10px 16px', background: result ? '#dce8f4' : '#f3f4f6', color: result ? '#374151' : '#9ca3af', border: 'none', borderRadius: 8, cursor: result ? 'pointer' : 'not-allowed', fontWeight: '600', fontSize: 14 }}
              data-testid="btn-pdf"
            >
              <Download size={16} />
            </button>
          </div>
        </div>
      </div>

      {/* Risultato Liquidazione */}
      {result && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16, marginBottom: 20 }}>
          {/* Card IVA Debito */}
          <div style={{ background: 'linear-gradient(135deg, rgba(220, 38, 38, 0.08), rgba(220, 38, 38, 0.04))', border: '1px solid rgba(220, 38, 38, 0.2)', borderRadius: 12, padding: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <p style={{ fontSize: 13, color: '#64748b', marginBottom: 4 }}>IVA a Debito</p>
                <p style={{ fontSize: 28, fontWeight: 'bold', color: '#dc2626', margin: '0 0 4px 0' }} data-testid="iva-debito">
                  {formatEuro(result.iva_debito)}
                </p>
                <p style={{ fontSize: 13, color: '#6080a0' }}>
                  {result.statistiche?.corrispettivi_count || 0} corrispettivi
                </p>
              </div>
              <TrendingUp size={32} style={{ color: '#fca5a5' }} />
            </div>
          </div>

          {/* Card IVA Credito */}
          <div style={{ background: 'linear-gradient(135deg, rgba(22, 163, 74, 0.08), rgba(22, 163, 74, 0.04))', border: '1px solid rgba(22, 163, 74, 0.2)', borderRadius: 12, padding: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <p style={{ fontSize: 13, color: '#64748b', marginBottom: 4 }}>IVA a Credito</p>
                <p style={{ fontSize: 28, fontWeight: 'bold', color: '#16a34a', margin: '0 0 4px 0' }} data-testid="iva-credito">
                  {formatEuro(result.iva_credito)}
                </p>
                <p style={{ fontSize: 13, color: '#6080a0' }}>
                  {result.statistiche?.fatture_incluse || 0} fatture 
                  {result.statistiche?.note_credito > 0 && ` (${result.statistiche.note_credito} NC)`}
                </p>
              </div>
              <TrendingDown size={32} style={{ color: '#86efac' }} />
            </div>
          </div>

          {/* Card Saldo */}
          <div style={{
            borderRadius: 12,
            padding: 20,
            background: result.iva_da_versare > 0 
              ? 'linear-gradient(135deg, rgba(245, 158, 11, 0.08), rgba(245, 158, 11, 0.04))'
              : 'linear-gradient(135deg, rgba(59, 130, 246, 0.08), rgba(59, 130, 246, 0.04))',
            border: result.iva_da_versare > 0 
              ? '1px solid rgba(245, 158, 11, 0.2)'
              : '1px solid rgba(59, 130, 246, 0.2)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <p style={{ fontSize: 13, color: '#64748b', marginBottom: 4 }}>
                  {result.iva_da_versare > 0 ? 'IVA da Versare' : 'Credito da Riportare'}
                </p>
                <p style={{ fontSize: 28, fontWeight: 'bold', color: result.iva_da_versare > 0 ? '#f59e0b' : '#1535a8', margin: '0 0 4px 0' }} data-testid="saldo-iva">
                  {formatEuro(result.iva_da_versare > 0 ? result.iva_da_versare : result.credito_da_riportare)}
                </p>
                <p style={{ fontSize: 13, color: '#6080a0' }}>{result.stato}</p>
              </div>
              <FileText size={32} style={{ color: result.iva_da_versare > 0 ? '#fcd34d' : '#93c5fd' }} />
            </div>
          </div>
        </div>
      )}

      {/* Dettaglio per Aliquota */}
      {result && (
        <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.08)', border: '1px solid #dce8f4', marginBottom: 20 }}>
          <div 
            style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer', marginBottom: showDettaglio ? 16 : 0 }}
            onClick={() => setShowDettaglio(!showDettaglio)}
          >
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 'bold', color: '#1535a8' }}>📋 Dettaglio per Aliquota IVA</h3>
            {showDettaglio ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
          </div>
          {showDettaglio && (
            <div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 24 }}>
                {/* IVA Debito per Aliquota */}
                <div>
                  <h4 style={{ color: '#dc2626', marginBottom: 12, fontSize: 15 }}>📈 IVA a Debito (Corrispettivi)</h4>
                  {Object.keys(result.sales_detail || {}).length > 0 ? (
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                      <thead>
                        <tr style={{ background: '#fef2f2', borderBottom: '2px solid #fecaca' }}>
                          <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: '600' }}>Aliquota</th>
                          <th style={{ padding: '10px 12px', textAlign: 'right', fontWeight: '600' }}>Imponibile</th>
                          <th style={{ padding: '10px 12px', textAlign: 'right', fontWeight: '600' }}>IVA</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(result.sales_detail).map(([aliq, val]) => (
                          <tr key={aliq} style={{ borderBottom: '1px solid #f3f4f6' }}>
                            <td style={{ padding: '10px 12px' }}>{aliq}%</td>
                            <td style={{ padding: '10px 12px', textAlign: 'right' }}>{formatEuro(val.imponibile)}</td>
                            <td style={{ padding: '10px 12px', textAlign: 'right' }}>{formatEuro(val.iva)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <p style={{ color: '#64748b', fontSize: 14 }}>Nessun corrispettivo nel periodo</p>
                  )}
                </div>

                {/* IVA Credito per Aliquota */}
                <div>
                  <h4 style={{ color: '#16a34a', marginBottom: 12 }}>📉 IVA a Credito (Acquisti)</h4>
                  {Object.keys(result.purchase_detail || {}).length > 0 ? (
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                      <thead>
                        <tr style={{ background: '#f0fdf4' }}>
                          <th>Aliquota</th>
                          <th style={{ textAlign: 'right' }}>Imponibile</th>
                          <th style={{ textAlign: 'right' }}>IVA</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(result.purchase_detail).map(([aliq, val]) => (
                          <tr key={aliq}>
                            <td>{aliq}%</td>
                            <td style={{ textAlign: 'right' }}>{formatEuro(val.imponibile)}</td>
                            <td style={{ textAlign: 'right' }}>{formatEuro(val.iva)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <p style={{ color: '#64748b', fontSize: 14 }}>Nessuna fattura nel periodo</p>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Sezione Confronto con Commercialista */}
      <div style={{ ...cardStyle, background: 'linear-gradient(135deg, #f5f3ff 0%, #eef2ff 100%)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: 12, borderBottom: '1px solid rgba(139, 92, 246, 0.2)' }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 'bold', color: '#6d28d9' }}>🔍 Confronto con Commercialista</h3>
        </div>
        <div style={{ marginTop: 16 }}>
          <p style={{ fontSize: 14, color: '#64748b', marginBottom: 16 }}>
            Inserisci i valori calcolati dal tuo commercialista per verificare eventuali discrepanze.
          </p>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
            <div>
              <label style={{ display: 'block', fontSize: 13, marginBottom: 4, fontWeight: 500 }}>
                IVA Debito Commercialista (€)
              </label>
              <input
                type="number"
                step="0.01"
                value={confronto.debito}
                onChange={(e) => setConfronto({ ...confronto, debito: e.target.value })}
                placeholder="0.00"
                style={{ padding: '10px 12px', borderRadius: 8, border: '2px solid #dce8f4', fontSize: 14, width: 180 }}
                data-testid="input-confronto-debito"
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 13, marginBottom: 4, fontWeight: 500 }}>
                IVA Credito Commercialista (€)
              </label>
              <input
                type="number"
                step="0.01"
                value={confronto.credito}
                onChange={(e) => setConfronto({ ...confronto, credito: e.target.value })}
                placeholder="0.00"
                style={{ padding: '10px 12px', borderRadius: 8, border: '2px solid #dce8f4', fontSize: 14, width: 180 }}
                data-testid="input-confronto-credito"
              />
            </div>
            <div style={{ display: 'flex', alignItems: 'flex-end' }}>
              <button 
                onClick={eseguiConfronto}
                disabled={!confronto.debito || !confronto.credito}
                style={{ padding: '10px 20px', background: '#7c3aed', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 'bold', fontSize: 14 }}
                data-testid="btn-confronta"
              >
                Confronta
              </button>
            </div>
          </div>

          {/* Risultato Confronto */}
          {confrontoResult && (
            <div style={{
              marginTop: 16,
              padding: 16,
              borderRadius: 8,
              background: confrontoResult.esito?.coincide ? '#f0fdf4' : '#fefce8',
              border: confrontoResult.esito?.coincide ? '1px solid #86efac' : '1px solid #fde047'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                {confrontoResult.esito?.coincide ? (
                  <CheckCircle size={20} style={{ color: '#16a34a' }} />
                ) : (
                  <AlertCircle size={20} style={{ color: '#ca8a04' }} />
                )}
                <span style={{ fontWeight: 600 }}>
                  {confrontoResult.esito?.note}
                </span>
              </div>
              
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
                <div>
                  <p style={{ fontSize: 13, color: '#64748b' }}>Differenza Debito</p>
                  <p style={{ fontWeight: 700, color: Math.abs(confrontoResult.differenze?.iva_debito) > 1 ? '#dc2626' : '#16a34a' }}>
                    {formatEuro(confrontoResult.differenze?.iva_debito || 0)}
                  </p>
                </div>
                <div>
                  <p style={{ fontSize: 13, color: '#64748b' }}>Differenza Credito</p>
                  <p style={{ fontWeight: 700, color: Math.abs(confrontoResult.differenze?.iva_credito) > 1 ? '#dc2626' : '#16a34a' }}>
                    {formatEuro(confrontoResult.differenze?.iva_credito || 0)}
                  </p>
                </div>
                <div>
                  <p style={{ fontSize: 13, color: '#64748b' }}>Differenza Saldo</p>
                  <p style={{ fontWeight: 700, color: Math.abs(confrontoResult.differenze?.saldo) > 1 ? '#dc2626' : '#16a34a' }}>
                    {formatEuro(confrontoResult.differenze?.saldo || 0)}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Riepilogo Annuale */}
      <div style={{ ...cardStyle }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 'bold', color: '#1535a8' }}>📅 Riepilogo Annuale {anno}</h3>
          <button onClick={caricaRiepilogoAnnuale} style={{ padding: '8px 14px', background: '#dce8f4', color: '#374151', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: '600', fontSize: 13 }} data-testid="btn-riepilogo-annuale">
            <RefreshCw size={14} style={loading ? { animation: 'spin 1s linear infinite' } : {}} />
            Carica
          </button>
        </div>
        {riepilogoAnnuale && (
          <div style={{ padding: 0, overflow: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr>
                  <th>Mese</th>
                  <th style={{ textAlign: 'right' }}>IVA Debito</th>
                  <th style={{ textAlign: 'right' }}>IVA Credito</th>
                  <th style={{ textAlign: 'right' }}>Da Versare</th>
                  <th style={{ textAlign: 'right' }}>Credito</th>
                  <th style={{ textAlign: 'center' }}>Stato</th>
                </tr>
              </thead>
              <tbody>
                {riepilogoAnnuale.mensile?.map((m) => (
                  <tr key={m.mese}>
                    <td style={{ fontWeight: 500 }}>{m.mese_nome}</td>
                    <td style={{ textAlign: 'right', color: '#dc2626' }}>{formatEuro(m.iva_debito || 0)}</td>
                    <td style={{ textAlign: 'right', color: '#16a34a' }}>{formatEuro(m.iva_credito || 0)}</td>
                    <td style={{ textAlign: 'right', color: '#f59e0b', fontWeight: 600 }}>
                      {m.iva_da_versare > 0 ? formatEuro(m.iva_da_versare) : '-'}
                    </td>
                    <td style={{ textAlign: 'right', color: '#1535a8' }}>
                      {m.credito_da_riportare > 0 ? formatEuro(m.credito_da_riportare) : '-'}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <span style={{ 
                        padding: '4px 10px', 
                        borderRadius: 6, 
                        fontSize: 12, 
                        fontWeight: '600',
                        background: m.stato === 'Da versare' ? '#fef3c7' : m.stato === 'A credito' ? '#dbeafe' : '#f3f4f6',
                        color: m.stato === 'Da versare' ? '#b45309' : m.stato === 'A credito' ? '#1535a8' : '#6080a0'
                      }}>
                        {m.stato}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot style={{ background: '#e2e8f0', fontWeight: 700 }}>
                <tr>
                  <td style={{ padding: 12 }}>TOTALE ANNO</td>
                  <td style={{ textAlign: 'right', padding: 12, color: '#b91c1c' }}>
                    {formatEuro(riepilogoAnnuale.totali?.iva_debito_totale || 0)}
                  </td>
                  <td style={{ textAlign: 'right', padding: 12, color: '#15803d' }}>
                    {formatEuro(riepilogoAnnuale.totali?.iva_credito_totale || 0)}
                  </td>
                  <td style={{ textAlign: 'right', padding: 12, color: '#b45309' }}>
                    {formatEuro(riepilogoAnnuale.totali?.iva_versata_totale || 0)}
                  </td>
                  <td style={{ textAlign: 'right', padding: 12, color: '#1535a8' }}>
                    {formatEuro(riepilogoAnnuale.totali?.credito_finale || 0)}
                  </td>
                  <td style={{ textAlign: 'center', padding: 12 }}>
                    <span style={{ 
                      padding: '4px 10px', 
                      borderRadius: 6, 
                      fontSize: 12, 
                      fontWeight: '600',
                      background: riepilogoAnnuale.totali?.saldo_annuale > 0 ? '#fef3c7' : '#dbeafe',
                      color: riepilogoAnnuale.totali?.saldo_annuale > 0 ? '#d97706' : '#1535a8'
                    }}>
                      {riepilogoAnnuale.totali?.saldo_annuale > 0 ? 'Da Versare' : 'A Credito'}
                    </span>
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </div>

      {/* Note informative */}
      <div style={{ marginTop: 20, padding: 16, background: '#f0f9ff', borderRadius: 8, fontSize: 13, color: '#1535a8' }}>
        <strong>ℹ️ Note sul calcolo</strong>
        <ul style={{ margin: '8px 0 0 16px', padding: 0, lineHeight: 1.8 }}>
          <li><strong>IVA a Debito</strong>: calcolata dalla somma dell&apos;IVA sui corrispettivi del periodo</li>
          <li><strong>IVA a Credito</strong>: calcolata dalla somma dell&apos;IVA sulle fatture d&apos;acquisto ricevute nel periodo</li>
          <li><strong>Deroghe temporali</strong>: applicate regola 15 giorni e 12 giorni per fatture mese precedente</li>
          <li><strong>Note di Credito</strong> (TD04, TD08): sottratte dal totale IVA credito</li>
          <li>Regime IVA: <strong>Ordinario per competenza</strong></li>
        </ul>
      </div>
      </div>
    </PageLayout>
  );
}
