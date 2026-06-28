import React, { useState, useEffect, useCallback } from 'react';
import api from '../api';
import { COLORS, STYLES, useIsMobile, formatEuro } from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';

export default function DatiProvvisori() {
  const { anno } = useAnnoGlobale();
  const isMobile = useIsMobile();
  const [proposte, setProposte] = useState([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [stats, setStats] = useState(null);

  const loadProposte = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/proposte?stato=da_confermare');
      setProposte(res.data?.proposte || []);
    } catch {
      setProposte([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProposte();
  }, [loadProposte]);

  const handleGenera = async () => {
    setGenerating(true);
    try {
      const res = await api.post(`/api/genera-proposte?anno=${anno}`);
      setStats(res.data);
      await loadProposte();
    } catch (e) {
      alert('Errore: ' + (e.response?.data?.detail || e.message));
    } finally {
      setGenerating(false);
    }
  };

  const handleConferma = async id => {
    try {
      await api.post(`/api/conferma/${id}`);
      setProposte(prev => prev.filter(p => p.id !== id));
    } catch (e) {
      alert('Errore: ' + (e.response?.data?.detail || e.message));
    }
  };

  const handleRifiuta = async id => {
    try {
      await api.post(`/api/rifiuta/${id}`);
      setProposte(prev => prev.filter(p => p.id !== id));
    } catch (e) {
      alert('Errore: ' + (e.response?.data?.detail || e.message));
    }
  };

  const handleConfermaTutte = async () => {
    if (!window.confirm(`Confermare tutte le ${proposte.length} proposte?`)) return;
    try {
      const res = await api.post('/api/conferma-tutte');
      alert(`${res.data?.confermati || 0} pagamenti confermati`);
      await loadProposte();
    } catch (e) {
      alert('Errore: ' + (e.response?.data?.detail || e.message));
    }
  };

  const totale = proposte.reduce((s, p) => s + (p.fattura_importo || 0), 0);

  return (
    <div style={{ ...STYLES.page, padding: isMobile ? 12 : 24 }}>
      {/* Header */}
      <div
        style={{
          background: '#1d4ed8',
          borderRadius: 16,
          padding: '24px 28px',
          color: 'white',
          marginBottom: 24,
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
            <h1 style={{ margin: '0 0 6px', fontSize: 22, fontWeight: 800 }}>📋 Dati Provvisori</h1>
            <p style={{ margin: 0, opacity: 0.85, fontSize: 14 }}>
              Conferma i pagamenti prima dell'inserimento definitivo in Prima Nota
            </p>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <button
              onClick={handleGenera}
              disabled={generating}
              style={{
                padding: '10px 20px',
                background: 'rgba(255,255,255,0.2)',
                color: 'white',
                border: '1px solid rgba(255,255,255,0.4)',
                borderRadius: 8,
                cursor: generating ? 'wait' : 'pointer',
                fontWeight: 700,
                fontSize: 13,
              }}
            >
              {generating ? '⏳ Analisi...' : '🔍 Cerca Abbinamenti'}
            </button>
            {proposte.length > 0 && (
              <button
                onClick={handleConfermaTutte}
                style={{
                  padding: '10px 20px',
                  background: '#22c55e',
                  color: 'white',
                  border: 'none',
                  borderRadius: 8,
                  cursor: 'pointer',
                  fontWeight: 700,
                  fontSize: 13,
                }}
              >
                ✓ Conferma Tutte ({proposte.length})
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Stats after generation */}
      {stats && (
        <div
          style={{
            background: '#f0fdf4',
            borderRadius: 10,
            padding: '12px 20px',
            marginBottom: 16,
            display: 'flex',
            gap: 20,
            fontSize: 13,
          }}
        >
          <span>
            📊 Analizzate: <b>{stats.fatture_analizzate}</b>
          </span>
          <span>
            ✅ Proposte: <b>{stats.proposte_create}</b>
          </span>
          <span>
            ⏭️ Già proposte: <b>{stats.gia_proposte}</b>
          </span>
          <span>
            ❌ No match: <b>{stats.no_match}</b>
          </span>
        </div>
      )}

      {/* Summary */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(3, 1fr)',
          gap: 12,
          marginBottom: 24,
        }}
      >
        <div
          style={{
            background: 'white',
            borderRadius: 10,
            padding: '16px 20px',
            boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
          }}
        >
          <div
            style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' }}
          >
            Da Confermare
          </div>
          <div style={{ fontSize: 28, fontWeight: 800, color: '#7c3aed', marginTop: 4 }}>
            {proposte.length}
          </div>
        </div>
        <div
          style={{
            background: 'white',
            borderRadius: 10,
            padding: '16px 20px',
            boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
          }}
        >
          <div
            style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' }}
          >
            Importo Totale
          </div>
          <div style={{ fontSize: 28, fontWeight: 800, color: '#059669', marginTop: 4 }}>
            € {totale.toLocaleString('it-IT', { minimumFractionDigits: 2 })}
          </div>
        </div>
        <div
          style={{
            background: 'white',
            borderRadius: 10,
            padding: '16px 20px',
            boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
          }}
        >
          <div
            style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' }}
          >
            Destinazione
          </div>
          <div style={{ fontSize: 28, fontWeight: 800, color: '#3b82f6', marginTop: 4 }}>
            🏦 Banca
          </div>
        </div>
      </div>

      {/* Proposte list */}
      {loading && (
        <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>Caricamento...</div>
      )}

      {!loading && proposte.length === 0 && (
        <div
          style={{
            padding: 48,
            textAlign: 'center',
            background: 'white',
            borderRadius: 12,
            boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
          }}
        >
          <div style={{ fontSize: 40, marginBottom: 12 }}>✅</div>
          <div style={{ fontSize: 16, fontWeight: 600, color: '#1e3a5f', marginBottom: 8 }}>
            Nessuna proposta in attesa
          </div>
          <div style={{ fontSize: 13, color: '#6b7280' }}>
            Clicca "🔍 Cerca Abbinamenti" per analizzare le fatture non pagate
          </div>
        </div>
      )}

      {!loading && proposte.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: 13,
              background: 'white',
              borderRadius: 12,
              overflow: 'hidden',
              boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
            }}
          >
            <thead>
              <tr style={{ background: '#f8fafc' }}>
                {[
                  'Affidabilità',
                  'Fattura',
                  'Fornitore',
                  'Importo',
                  'Movimento Banca',
                  'Data Banca',
                  'Azioni',
                ].map((h, i) => (
                  <th
                    key={i}
                    style={{
                      padding: '12px 14px',
                      textAlign: 'left',
                      fontWeight: 700,
                      fontSize: 11,
                      color: '#64748b',
                      textTransform: 'uppercase',
                      borderBottom: '2px solid #e2e8f0',
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {proposte.map(p => (
                <tr key={p.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                  <td style={{ padding: '12px 14px' }}>
                    <div
                      style={{
                        width: 40,
                        height: 40,
                        borderRadius: '50%',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontWeight: 800,
                        fontSize: 13,
                        color: 'white',
                        background:
                          p.confidence >= 50
                            ? '#22c55e'
                            : p.confidence >= 30
                              ? '#f59e0b'
                              : '#ef4444',
                      }}
                    >
                      {p.confidence}%
                    </div>
                  </td>
                  <td style={{ padding: '12px 14px' }}>
                    <div style={{ fontWeight: 700, color: '#1e3a5f' }}>#{p.fattura_numero}</div>
                    <div style={{ fontSize: 11, color: '#6b7280' }}>{p.fattura_data}</div>
                  </td>
                  <td style={{ padding: '12px 14px' }}>
                    <div style={{ fontWeight: 600 }}>{p.fattura_fornitore}</div>
                    <div style={{ fontSize: 11, color: '#6b7280' }}>P.IVA {p.fattura_piva}</div>
                  </td>
                  <td
                    style={{
                      padding: '12px 14px',
                      fontWeight: 700,
                      color: '#059669',
                      fontSize: 15,
                    }}
                  >
                    €{' '}
                    {(p.fattura_importo || 0).toLocaleString('it-IT', { minimumFractionDigits: 2 })}
                  </td>
                  <td
                    style={{ padding: '12px 14px', fontSize: 12, color: '#475569', maxWidth: 250 }}
                  >
                    {(p.movimento_descrizione || '').substring(0, 60)}...
                  </td>
                  <td style={{ padding: '12px 14px', fontWeight: 600 }}>{p.movimento_data}</td>
                  <td style={{ padding: '12px 14px' }}>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button
                        onClick={() => handleConferma(p.id)}
                        style={{
                          padding: '6px 14px',
                          background: '#22c55e',
                          color: 'white',
                          border: 'none',
                          borderRadius: 6,
                          cursor: 'pointer',
                          fontWeight: 700,
                          fontSize: 12,
                        }}
                      >
                        ✓ Conferma
                      </button>
                      <button
                        onClick={() => handleRifiuta(p.id)}
                        style={{
                          padding: '6px 14px',
                          background: '#fee2e2',
                          color: '#dc2626',
                          border: 'none',
                          borderRadius: 6,
                          cursor: 'pointer',
                          fontWeight: 600,
                          fontSize: 12,
                        }}
                      >
                        ✗
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
