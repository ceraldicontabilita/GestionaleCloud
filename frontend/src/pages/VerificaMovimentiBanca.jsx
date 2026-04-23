import React, { useState, useEffect, useCallback } from 'react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { RefreshCw, Download, AlertTriangle, CheckCircle, Loader2, Info } from 'lucide-react';

/**
 * Pagina: movimenti bancari (da estratto conto) che NON sono in Prima Nota Banca.
 *
 * Sostituisce i vecchi box "Prima Nota vs Estratto Conto" e "Bonifici vs Banca"
 * che mostravano solo numeri aggregati incomprensibili. Qui l'utente vede
 * la LISTA esatta dei movimenti mancanti e può decidere cosa importare.
 *
 * Endpoint usati (PR: fix/strumenti-pulizia-e-importa-ec):
 *   GET  /api/prima-nota/movimenti-ec-non-in-prima-nota?anno=N&tipo=entrata|uscita
 *   POST /api/prima-nota/importa-da-ec  { ec_id, categoria?, descrizione? }
 */
export default function VerificaMovimentiBanca() {
  const { anno } = useAnnoGlobale();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [filtroTipo, setFiltroTipo] = useState('all'); // all | entrata | uscita
  const [importing, setImporting] = useState({}); // {ec_id: true/false}
  const [imported, setImported] = useState({}); // {ec_id: 'ok' | 'err'}
  const [error, setError] = useState(null);

  const caricaDati = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ anno: String(anno) });
      if (filtroTipo !== 'all') params.set('tipo', filtroTipo);
      const r = await api.get(`/api/prima-nota/movimenti-ec-non-in-prima-nota?${params.toString()}`);
      setData(r.data);
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || 'Errore caricamento');
    } finally {
      setLoading(false);
    }
  }, [anno, filtroTipo]);

  useEffect(() => { caricaDati(); }, [caricaDati]);

  const importaSingolo = async (ec_id) => {
    setImporting(s => ({ ...s, [ec_id]: true }));
    try {
      const r = await api.post('/api/prima-nota/importa-da-ec', { ec_id });
      if (r.data?.success) {
        setImported(s => ({ ...s, [ec_id]: 'ok' }));
        // Tolgo dalla lista dopo 1.5s per dare feedback visivo
        setTimeout(() => {
          setData(d => d ? {
            ...d,
            movimenti: (d.movimenti || []).filter(m => m.id !== ec_id),
            totale_mancanti: Math.max(0, (d.totale_mancanti || 1) - 1),
          } : d);
        }, 1500);
      } else {
        setImported(s => ({ ...s, [ec_id]: 'err' }));
      }
    } catch (e) {
      setImported(s => ({ ...s, [ec_id]: 'err' }));
      alert('Errore import: ' + (e?.response?.data?.detail || e?.message));
    } finally {
      setImporting(s => ({ ...s, [ec_id]: false }));
    }
  };

  const fmtEuro = (n) => new Intl.NumberFormat('it-IT', {
    style: 'currency', currency: 'EUR',
  }).format(Number(n) || 0);
  const fmtData = (d) => {
    if (!d) return '—';
    try { return new Date(d).toLocaleDateString('it-IT'); } catch { return d; }
  };

  const movimenti = data?.movimenti || [];

  return (
    <div style={{ padding: 0 }}>
      {/* Intro */}
      <div style={{
        background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 10,
        padding: 14, marginBottom: 16, display: 'flex', gap: 12, alignItems: 'flex-start',
      }}>
        <Info size={18} color="#0284c7" style={{ flexShrink: 0, marginTop: 2 }} />
        <div style={{ fontSize: 13, color: '#0c4a6e', lineHeight: 1.5 }}>
          Qui vedi i movimenti presenti nell'<strong>Estratto Conto bancario</strong> che
          NON risultano ancora registrati in <strong>Prima Nota Banca</strong>.
          <br />
          Se un movimento è legittimo, clicca <strong>Importa in Prima Nota</strong> per aggiungerlo.
          Se invece è già in Prima Nota ma non è stato riconciliato, lo vedi segnalato con un'icona gialla.
        </div>
      </div>

      {/* Toolbar */}
      <div style={{
        display: 'flex', gap: 10, marginBottom: 14, flexWrap: 'wrap',
        alignItems: 'center',
      }}>
        <div style={{ display: 'inline-flex', gap: 6, background: '#f1f5f9', padding: 4, borderRadius: 8 }}>
          {[
            { k: 'all', label: 'Tutti' },
            { k: 'entrata', label: 'Entrate' },
            { k: 'uscita', label: 'Uscite' },
          ].map(o => (
            <button
              key={o.k}
              onClick={() => setFiltroTipo(o.k)}
              style={{
                padding: '6px 12px', fontSize: 12, fontWeight: 600,
                background: filtroTipo === o.k ? '#0f2744' : 'transparent',
                color: filtroTipo === o.k ? '#fff' : '#475569',
                border: 'none', borderRadius: 6, cursor: 'pointer',
              }}
            >
              {o.label}
            </button>
          ))}
        </div>

        <button
          onClick={caricaDati}
          disabled={loading}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '7px 12px', fontSize: 13, fontWeight: 500,
            background: '#fff', color: '#475569',
            border: '1px solid #cbd5e1', borderRadius: 6,
            cursor: loading ? 'not-allowed' : 'pointer',
          }}
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          Ricarica
        </button>

        {data && (
          <div style={{ marginLeft: 'auto', fontSize: 12, color: '#64748b' }}>
            Trovati <strong>{data.totale_mancanti}</strong> movimenti mancanti ·
            Entrate: <strong>{fmtEuro(data.importo_totale_entrate)}</strong> ·
            Uscite: <strong>{fmtEuro(data.importo_totale_uscite)}</strong>
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div style={{
          background: '#fef2f2', border: '1px solid #fecaca', color: '#991b1b',
          padding: 12, borderRadius: 8, fontSize: 13, marginBottom: 12,
        }}>
          {String(error)}
        </div>
      )}

      {/* Loading */}
      {loading && !data && (
        <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>
          <Loader2 size={24} className="animate-spin" style={{ margin: '0 auto 8px' }} />
          Caricamento movimenti…
        </div>
      )}

      {/* Empty state */}
      {!loading && data && movimenti.length === 0 && (
        <div style={{
          padding: 40, textAlign: 'center',
          background: '#f0fdf4', border: '1px solid #86efac', borderRadius: 10,
        }}>
          <CheckCircle size={32} color="#16a34a" style={{ margin: '0 auto 10px' }} />
          <div style={{ fontSize: 15, fontWeight: 600, color: '#166534' }}>
            Tutto riconciliato
          </div>
          <div style={{ fontSize: 13, color: '#15803d', marginTop: 4 }}>
            Nessun movimento dell'estratto conto manca in Prima Nota Banca per l'anno {anno}.
          </div>
        </div>
      )}

      {/* List */}
      {movimenti.length > 0 && (
        <div style={{
          background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10,
          overflow: 'hidden',
        }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
              <tr>
                <th style={thStyle}>Data</th>
                <th style={thStyle}>Tipo</th>
                <th style={thStyle}>Descrizione</th>
                <th style={{ ...thStyle, textAlign: 'right' }}>Importo</th>
                <th style={{ ...thStyle, textAlign: 'center' }}>Azione</th>
              </tr>
            </thead>
            <tbody>
              {movimenti.map(m => {
                const status = imported[m.id];
                const isBusy = importing[m.id];
                return (
                  <tr key={m.id} style={{
                    borderBottom: '1px solid #f1f5f9',
                    background: status === 'ok' ? '#f0fdf4' : 'transparent',
                    transition: 'background 200ms',
                  }}>
                    <td style={tdStyle}>{fmtData(m.data)}</td>
                    <td style={tdStyle}>
                      <span style={{
                        padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600,
                        background: m.tipo === 'entrata' ? '#dcfce7' : '#fee2e2',
                        color: m.tipo === 'entrata' ? '#166534' : '#991b1b',
                      }}>
                        {m.tipo === 'entrata' ? 'Entrata' : 'Uscita'}
                      </span>
                      {m.possibile_match_esistente && (
                        <span
                          title="C'è un movimento simile in Prima Nota ma non è collegato — forse va solo riconciliato"
                          style={{ marginLeft: 6, cursor: 'help' }}
                        >
                          <AlertTriangle size={13} color="#d97706" style={{ verticalAlign: 'text-bottom' }} />
                        </span>
                      )}
                    </td>
                    <td style={{ ...tdStyle, maxWidth: 400, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {m.descrizione || '—'}
                      {m.categoria && (
                        <span style={{ marginLeft: 8, fontSize: 11, color: '#64748b' }}>
                          ({m.categoria})
                        </span>
                      )}
                    </td>
                    <td style={{
                      ...tdStyle, textAlign: 'right', fontWeight: 600,
                      color: m.tipo === 'entrata' ? '#16a34a' : '#dc2626',
                    }}>
                      {fmtEuro(m.importo)}
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                      {status === 'ok' ? (
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', gap: 4,
                          color: '#16a34a', fontSize: 12, fontWeight: 600,
                        }}>
                          <CheckCircle size={14} /> Importato
                        </span>
                      ) : (
                        <button
                          onClick={() => importaSingolo(m.id)}
                          disabled={isBusy}
                          style={{
                            display: 'inline-flex', alignItems: 'center', gap: 5,
                            padding: '5px 10px', fontSize: 12, fontWeight: 500,
                            background: '#b8860b', color: '#fff',
                            border: 'none', borderRadius: 5,
                            cursor: isBusy ? 'not-allowed' : 'pointer',
                            opacity: isBusy ? 0.6 : 1,
                          }}
                        >
                          {isBusy ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
                          {isBusy ? 'Importo…' : 'Importa in Prima Nota'}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const thStyle = {
  padding: '10px 12px', textAlign: 'left', fontSize: 11,
  fontWeight: 600, color: '#475569', textTransform: 'uppercase',
  letterSpacing: 0.3,
};
const tdStyle = {
  padding: '8px 12px', verticalAlign: 'middle',
};
