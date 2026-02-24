/**
 * CoerenzaPOSCorrispettivi.jsx
 * 
 * Verifica coerenza tra pagamenti elettronici (POS) e corrispettivi XML
 * Normativa 2026: obbligo abbinamento RT-POS
 */
import React, { useState, useEffect } from 'react';
import api from '../api';
import { formatEuro, formatDateIT } from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { 
  CreditCard, AlertTriangle, CheckCircle, XCircle, 
  RefreshCw, TrendingUp, Calendar, FileWarning
} from 'lucide-react';

export default function CoerenzaPOSCorrispettivi() {
  const { anno } = useAnnoGlobale();
  const [loading, setLoading] = useState(true);
  const [dati, setDati] = useState(null);
  const [riepilogoMensile, setRiepilogoMensile] = useState(null);
  const [tab, setTab] = useState('giornaliero');
  const [err, setErr] = useState('');

  useEffect(() => {
    loadDati();
  }, [anno]);

  const loadDati = async () => {
    setLoading(true);
    setErr('');
    try {
      const [coerenzaRes, mensileRes] = await Promise.all([
        api.get(`/api/pos-corrispettivi/verifica-coerenza?anno=${anno}`),
        api.get(`/api/pos-corrispettivi/riepilogo-mensile?anno=${anno}`)
      ]);
      setDati(coerenzaRes.data);
      setRiepilogoMensile(mensileRes.data);
    } catch (e) {
      setErr('Errore caricamento: ' + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  };

  const handleRiconcilia = async (data) => {
    try {
      const res = await api.post(`/api/pos-corrispettivi/riconcilia-pos-giorno?data=${data}`);
      alert(res.data.message);
      loadDati();
    } catch (e) {
      alert('Errore: ' + (e.response?.data?.detail || e.message));
    }
  };

  const getStatoIcon = (stato) => {
    switch (stato) {
      case 'ok': return <CheckCircle size={16} color="#10b981" />;
      case 'mancante': return <XCircle size={16} color="#ef4444" />;
      case 'differenza': return <AlertTriangle size={16} color="#f59e0b" />;
      case 'extra': return <FileWarning size={16} color="#8b5cf6" />;
      default: return null;
    }
  };

  const getStatoBadge = (stato) => {
    const colors = {
      ok: { bg: '#dcfce7', color: '#166534' },
      mancante: { bg: '#fee2e2', color: '#991b1b' },
      differenza: { bg: '#fef3c7', color: '#92400e' },
      extra: { bg: '#f3e8ff', color: '#6b21a8' },
      warning: { bg: '#fef3c7', color: '#92400e' },
      error: { bg: '#fee2e2', color: '#991b1b' }
    };
    const c = colors[stato] || colors.ok;
    return {
      background: c.bg,
      color: c.color,
      padding: '4px 10px',
      borderRadius: 12,
      fontSize: 11,
      fontWeight: 600,
      textTransform: 'uppercase'
    };
  };

  if (loading) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <RefreshCw size={32} style={{ animation: 'spin 1s linear infinite', color: '#1535a8' }} />
        <p style={{ marginTop: 12, color: '#64748b' }}>Analisi coerenza POS/Corrispettivi...</p>
      </div>
    );
  }

  if (err) {
    return (
      <div style={{ padding: 20, background: '#fee2e2', borderRadius: 8, color: '#991b1b' }}>
        {err}
        <button onClick={loadDati} style={{ marginLeft: 12, padding: '4px 12px' }}>Riprova</button>
      </div>
    );
  }

  return (
    <div style={{ padding: 20 }} data-testid="coerenza-pos-page">
      {/* KPI Summary - Compatto */}
      {dati?.riepilogo && (
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: 'repeat(4, 1fr)', 
          gap: 12, 
          marginBottom: 20 
        }}>
          <div style={{ background: '#f0fdf4', padding: 16, borderRadius: 10, border: '1px solid #bbf7d0' }}>
            <div style={{ fontSize: 11, color: '#166534', marginBottom: 4 }}>Coerenza</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: '#166534' }}>
              {dati.riepilogo.percentuale_coerenza}%
            </div>
          </div>
          <div style={{ background: '#eff6ff', padding: 16, borderRadius: 10, border: '1px solid #bfdbfe' }}>
            <div style={{ fontSize: 11, color: '#1535a8', marginBottom: 4 }}>POS da XML</div>
            <div style={{ fontSize: 18, fontWeight: 700, color: '#1535a8' }}>
              {formatEuro(dati.riepilogo.totale_elettronico_xml)}
            </div>
          </div>
          <div style={{ background: '#f5f3ff', padding: 16, borderRadius: 10, border: '1px solid #ddd6fe' }}>
            <div style={{ fontSize: 11, color: '#5b21b6', marginBottom: 4 }}>POS Accreditato</div>
            <div style={{ fontSize: 18, fontWeight: 700, color: '#5b21b6' }}>
              {formatEuro(dati.riepilogo.totale_pos_accreditato)}
            </div>
          </div>
          <div style={{ 
            background: Math.abs(dati.riepilogo.differenza_totale) > 100 ? '#fef2f2' : '#f0fdf4', 
            padding: 16, 
            borderRadius: 10, 
            border: `1px solid ${Math.abs(dati.riepilogo.differenza_totale) > 100 ? '#fecaca' : '#bbf7d0'}` 
          }}>
            <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>Differenza</div>
            <div style={{ 
              fontSize: 18, 
              fontWeight: 700, 
              color: Math.abs(dati.riepilogo.differenza_totale) > 100 ? '#dc2626' : '#16a34a' 
            }}>
              {formatEuro(dati.riepilogo.differenza_totale)}
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button
          onClick={() => setTab('giornaliero')}
          style={{
            padding: '8px 16px',
            background: tab === 'giornaliero' ? '#1e293b' : '#f1f5f9',
            color: tab === 'giornaliero' ? 'white' : '#475569',
            border: 'none',
            borderRadius: 6,
            fontWeight: 600,
            fontSize: 13,
            cursor: 'pointer'
          }}
        >
          <Calendar size={14} style={{ marginRight: 6, verticalAlign: 'middle' }} />
          Giornaliero
        </button>
        <button
          onClick={() => setTab('mensile')}
          style={{
            padding: '8px 16px',
            background: tab === 'mensile' ? '#1e293b' : '#f1f5f9',
            color: tab === 'mensile' ? 'white' : '#475569',
            border: 'none',
            borderRadius: 6,
            fontWeight: 600,
            fontSize: 13,
            cursor: 'pointer'
          }}
        >
          <TrendingUp size={14} style={{ marginRight: 6, verticalAlign: 'middle' }} />
          Mensile
        </button>
        <button
          onClick={() => setTab('anomalie')}
          style={{
            padding: '8px 16px',
            background: tab === 'anomalie' ? '#dc2626' : '#fee2e2',
            color: tab === 'anomalie' ? 'white' : '#991b1b',
            border: 'none',
            borderRadius: 6,
            fontWeight: 600,
            fontSize: 13,
            cursor: 'pointer'
          }}
        >
          <AlertTriangle size={14} style={{ marginRight: 6, verticalAlign: 'middle' }} />
          Anomalie ({dati?.anomalie_count || 0})
        </button>
        <button
          onClick={loadDati}
          style={{
            marginLeft: 'auto',
            padding: '8px 16px',
            background: '#f1f5f9',
            color: '#475569',
            border: 'none',
            borderRadius: 6,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 6
          }}
        >
          <RefreshCw size={14} /> Aggiorna
        </button>
      </div>

      {/* Tab Giornaliero */}
      {tab === 'giornaliero' && dati?.riepilogo_giornaliero && (
        <div style={{ background: 'white', borderRadius: 10, border: '1px solid #e2e8f0', overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#f8fafc' }}>
                <th style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 600, color: '#64748b', fontSize: 11 }}>DATA</th>
                <th style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 600, color: '#64748b', fontSize: 11 }}>ELETTR. XML</th>
                <th style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 600, color: '#64748b', fontSize: 11 }}>POS BANCA</th>
                <th style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 600, color: '#64748b', fontSize: 11 }}>DIFF.</th>
                <th style={{ padding: '10px 14px', textAlign: 'center', fontWeight: 600, color: '#64748b', fontSize: 11 }}>STATO</th>
              </tr>
            </thead>
            <tbody>
              {dati.riepilogo_giornaliero.slice().reverse().map((g, i) => (
                <tr key={g.data} style={{ borderBottom: '1px solid #f1f5f9' }}>
                  <td style={{ padding: '10px 14px' }}>
                    <span style={{ fontWeight: 600 }}>{formatDateIT(g.data)}</span>
                    <span style={{ marginLeft: 8, fontSize: 11, color: '#94a3b8' }}>{g.giorno_settimana}</span>
                  </td>
                  <td style={{ padding: '10px 14px', textAlign: 'right', color: '#1535a8' }}>
                    {formatEuro(g.elettronico_xml)}
                  </td>
                  <td style={{ padding: '10px 14px', textAlign: 'right', color: '#7c3aed' }}>
                    {formatEuro(g.pos_accreditato)}
                  </td>
                  <td style={{ 
                    padding: '10px 14px', 
                    textAlign: 'right', 
                    fontWeight: 600,
                    color: g.differenza > 10 ? '#dc2626' : g.differenza < -10 ? '#1535a8' : '#16a34a'
                  }}>
                    {g.differenza > 0 ? '+' : ''}{formatEuro(g.differenza)}
                  </td>
                  <td style={{ padding: '10px 14px', textAlign: 'center' }}>
                    <span style={getStatoBadge(g.stato)}>
                      {getStatoIcon(g.stato)} {g.stato}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab Mensile */}
      {tab === 'mensile' && riepilogoMensile?.mesi && (
        <div style={{ background: 'white', borderRadius: 10, border: '1px solid #e2e8f0', overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#f8fafc' }}>
                <th style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 600, color: '#64748b', fontSize: 11 }}>MESE</th>
                <th style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 600, color: '#64748b', fontSize: 11 }}>CORRISPETTIVI</th>
                <th style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 600, color: '#64748b', fontSize: 11 }}>CONTANTI</th>
                <th style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 600, color: '#64748b', fontSize: 11 }}>ELETTR. XML</th>
                <th style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 600, color: '#64748b', fontSize: 11 }}>POS BANCA</th>
                <th style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 600, color: '#64748b', fontSize: 11 }}>DIFF.</th>
                <th style={{ padding: '10px 14px', textAlign: 'center', fontWeight: 600, color: '#64748b', fontSize: 11 }}>STATO</th>
              </tr>
            </thead>
            <tbody>
              {riepilogoMensile.mesi.map(m => (
                <tr key={m.mese} style={{ borderBottom: '1px solid #f1f5f9' }}>
                  <td style={{ padding: '10px 14px', fontWeight: 600 }}>{m.nome} {anno}</td>
                  <td style={{ padding: '10px 14px', textAlign: 'right' }}>{formatEuro(m.totale_corrispettivi)}</td>
                  <td style={{ padding: '10px 14px', textAlign: 'right', color: '#16a34a' }}>{formatEuro(m.contanti)}</td>
                  <td style={{ padding: '10px 14px', textAlign: 'right', color: '#1535a8' }}>{formatEuro(m.elettronico_xml)}</td>
                  <td style={{ padding: '10px 14px', textAlign: 'right', color: '#7c3aed' }}>{formatEuro(m.pos_accreditato)}</td>
                  <td style={{ 
                    padding: '10px 14px', 
                    textAlign: 'right', 
                    fontWeight: 600,
                    color: Math.abs(m.differenza) > 50 ? '#dc2626' : '#16a34a'
                  }}>
                    {m.differenza > 0 ? '+' : ''}{formatEuro(m.differenza)}
                  </td>
                  <td style={{ padding: '10px 14px', textAlign: 'center' }}>
                    <span style={getStatoBadge(m.stato)}>{m.stato}</span>
                  </td>
                </tr>
              ))}
              {/* Totale */}
              <tr style={{ background: '#f8fafc', fontWeight: 700 }}>
                <td style={{ padding: '12px 14px' }}>TOTALE {anno}</td>
                <td style={{ padding: '12px 14px', textAlign: 'right' }}>-</td>
                <td style={{ padding: '12px 14px', textAlign: 'right' }}>-</td>
                <td style={{ padding: '12px 14px', textAlign: 'right', color: '#1535a8' }}>
                  {formatEuro(riepilogoMensile.totali.elettronico_xml)}
                </td>
                <td style={{ padding: '12px 14px', textAlign: 'right', color: '#7c3aed' }}>
                  {formatEuro(riepilogoMensile.totali.pos_accreditato)}
                </td>
                <td style={{ 
                  padding: '12px 14px', 
                  textAlign: 'right',
                  color: Math.abs(riepilogoMensile.totali.differenza) > 100 ? '#dc2626' : '#16a34a'
                }}>
                  {riepilogoMensile.totali.differenza > 0 ? '+' : ''}{formatEuro(riepilogoMensile.totali.differenza)}
                </td>
                <td></td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {/* Tab Anomalie */}
      {tab === 'anomalie' && (
        <div>
          {dati?.anomalie?.length === 0 ? (
            <div style={{ padding: 40, textAlign: 'center', background: '#f0fdf4', borderRadius: 10 }}>
              <CheckCircle size={48} color="#16a34a" />
              <p style={{ marginTop: 12, color: '#166534', fontWeight: 600 }}>Nessuna anomalia rilevata</p>
              <p style={{ fontSize: 13, color: '#64748b' }}>I dati POS e corrispettivi XML sono coerenti</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {dati.anomalie.map((a, i) => (
                <div key={a.data} style={{ 
                  background: 'white', 
                  borderRadius: 10, 
                  border: '1px solid #fecaca',
                  padding: 16,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 16
                }}>
                  <div style={{ 
                    width: 48, 
                    height: 48, 
                    borderRadius: 10, 
                    background: '#fee2e2',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center'
                  }}>
                    {getStatoIcon(a.stato)}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>
                      {formatDateIT(a.data)} <span style={{ fontSize: 12, color: '#94a3b8' }}>({a.giorno_settimana})</span>
                    </div>
                    <div style={{ fontSize: 13, color: '#64748b' }}>{a.messaggio}</div>
                    <div style={{ fontSize: 12, marginTop: 4 }}>
                      <span style={{ color: '#1535a8' }}>XML: {formatEuro(a.elettronico_xml)}</span>
                      <span style={{ margin: '0 8px', color: '#94a3b8' }}>|</span>
                      <span style={{ color: '#7c3aed' }}>POS: {formatEuro(a.pos_accreditato)}</span>
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ 
                      fontSize: 18, 
                      fontWeight: 700, 
                      color: '#dc2626',
                      marginBottom: 4
                    }}>
                      {formatEuro(a.differenza)}
                    </div>
                    <button
                      onClick={() => handleRiconcilia(a.data)}
                      style={{
                        padding: '6px 12px',
                        background: '#1535a8',
                        color: 'white',
                        border: 'none',
                        borderRadius: 6,
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: 'pointer'
                      }}
                    >
                      Riconcilia
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Nota normativa */}
      <div style={{ 
        marginTop: 16, 
        padding: 12, 
        background: '#fef3c7', 
        borderRadius: 8, 
        fontSize: 12, 
        color: '#92400e',
        display: 'flex',
        alignItems: 'flex-start',
        gap: 10
      }}>
        <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 2 }} />
        <div>
          <strong>Normativa 2026:</strong> Dal 1° gennaio 2026 è obbligatorio collegare RT e POS. 
          Eventuali discrepanze tra corrispettivi e transazioni POS possono generare avvisi dall'Agenzia delle Entrate.
          Accredito POS: Lun-Gio +1g lavorativo, Ven-Dom → Lunedì.
        </div>
      </div>
    </div>
  );
}
