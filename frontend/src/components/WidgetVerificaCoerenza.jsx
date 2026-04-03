import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';
import { formatEuro } from '../lib/utils';
import { AlertTriangle, CheckCircle, XCircle, ChevronDown, ChevronUp, RefreshCw } from 'lucide-react';

/**
 * Widget di Verifica Coerenza Dati
 * Mostra alert automatici quando ci sono discrepanze nei dati.
 * Da includere in tutte le pagine principali.
 */
export default function WidgetVerificaCoerenza({ anno, mostraDettaglio = false }) {
  const [verifica, setVerifica] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadVerifica();
  }, [anno]);

  const loadVerifica = async () => {
    try {
      setLoading(true);
      setError(null);
      const annoCorrente = anno || new Date().getFullYear();
      const res = await api.get(`/api/verifica-coerenza/widget?anno=${annoCorrente}`);
      setVerifica(res.data);
    } catch (err) {
      console.error('Errore caricamento verifica:', err);
      setError('Errore nel caricamento delle verifiche');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div style={{
        padding: 10,
        background: '#f1f5f9',
        borderRadius: 8,
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        fontSize: 13,
        color: '#64748b'
      }}>
        <RefreshCw size={16} className="animate-spin" />
        Verifica coerenza dati...
      </div>
    );
  }

  if (error || !verifica) {
    return null; // Non mostrare nulla se c'è errore
  }

  // Se non ci sono discrepanze, mostra solo un badge verde (opzionale)
  if (!verifica.has_discrepanze && !mostraDettaglio) {
    return (
      <div style={{
        padding: '8px 12px',
        background: '#dcfce7',
        borderRadius: 8,
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        fontSize: 13,
        color: '#166534',
        border: '1px solid #bbf7d0'
      }}>
        <CheckCircle size={16} />
        Dati coerenti
      </div>
    );
  }

  // Se ci sono discrepanze, mostra alert
  if (verifica.has_discrepanze) {
    const severityColor = verifica.critical_count > 0 ? '#dc2626' : '#f59e0b';
    const severityBg = verifica.critical_count > 0 ? '#fef2f2' : '#fffbeb';
    const severityBorder = verifica.critical_count > 0 ? '#fecaca' : '#fde68a';

    return (
      <div style={{
        background: severityBg,
        borderRadius: 8,
        border: `1px solid ${severityBorder}`,
        marginBottom: 16
      }}>
        {/* Header */}
        <div
          onClick={() => setExpanded(!expanded)}
          style={{
            padding: '12px 16px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            cursor: 'pointer'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {verifica.critical_count > 0 ? (
              <XCircle size={20} color="#dc2626" />
            ) : (
              <AlertTriangle size={20} color="#f59e0b" />
            )}
            <div>
              <div style={{ fontWeight: 'bold', color: severityColor, fontSize: 14 }}>
                ⚠️ {verifica.totale_discrepanze} Discrepanze Rilevate - {verifica.mese_nome} {verifica.anno}
              </div>
              <div style={{ fontSize: 12, color: '#64748b' }}>
                {verifica.critical_count > 0 && `${verifica.critical_count} critiche • `}
                Clicca per dettagli
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button
              onClick={(e) => { e.stopPropagation(); loadVerifica(); }}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: 4
              }}
              title="Ricarica"
            >
              <RefreshCw size={16} color="#64748b" />
            </button>
            {expanded ? <ChevronUp size={20} color="#64748b" /> : <ChevronDown size={20} color="#64748b" />}
          </div>
        </div>

        {/* Dettaglio discrepanze */}
        {expanded && (
          <div style={{
            padding: '0 16px 16px',
            borderTop: '1px solid ' + severityBorder
          }}>
            {verifica.discrepanze?.map((d, idx) => (
              <div
                key={idx}
                style={{
                  padding: 12,
                  marginTop: 12,
                  background: 'white',
                  borderRadius: 6,
                  border: `1px solid ${d.severita === 'critical' ? '#fecaca' : '#fde68a'}`
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <div style={{
                      fontWeight: 'bold',
                      color: d.severita === 'critical' ? '#dc2626' : '#d97706',
                      fontSize: 13
                    }}>
                      {d.categoria} - {d.sottocategoria}
                    </div>
                    <div style={{ fontSize: 13, color: '#475569', marginTop: 4 }}>
                      {d.descrizione}
                    </div>
                    {d.periodo && (
                      <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2 }}>
                        Periodo: {d.periodo}
                      </div>
                    )}
                  </div>
                  <div style={{ textAlign: 'right', minWidth: 120 }}>
                    <div style={{ fontSize: 12, color: '#64748b' }}>Atteso</div>
                    <div style={{ fontWeight: 'bold', color: '#059669' }}>{formatEuro(d.valore_atteso)}</div>
                    <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>Trovato</div>
                    <div style={{ fontWeight: 'bold', color: '#dc2626' }}>{formatEuro(d.valore_trovato)}</div>
                    <div style={{
                      fontSize: 13,
                      fontWeight: 'bold',
                      color: d.differenza > 0 ? '#dc2626' : '#2563eb',
                      marginTop: 4,
                      padding: '2px 8px',
                      background: d.differenza > 0 ? '#fef2f2' : '#eff6ff',
                      borderRadius: 4
                    }}>
                      Diff: {d.differenza > 0 ? '+' : ''}{formatEuro(d.differenza)}
                    </div>
                  </div>
                </div>
                {d.suggerimento && (
                  <div style={{
                    marginTop: 8,
                    padding: 8,
                    background: '#f8fafc',
                    borderRadius: 4,
                    fontSize: 12,
                    color: '#64748b'
                  }}>
                    💡 {d.suggerimento}
                  </div>
                )}
              </div>
            ))}

            {verifica.totale_discrepanze > 5 && (
              <div style={{
                textAlign: 'center',
                marginTop: 12,
                padding: 8,
                background: '#f1f5f9',
                borderRadius: 4,
                fontSize: 13,
                color: '#64748b'
              }}>
                E altre {verifica.totale_discrepanze - 5} discrepanze...
                <Link
                  to="/verifica-coerenza"
                  style={{ marginLeft: 8, color: '#2563eb', textDecoration: 'none' }}
                >
                  Vedi tutte →
                </Link>
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  return null;
}

/**
 * Badge compatto per header/navbar
 */
export function BadgeVerificaCoerenza({ anno }) {
  const [count, setCount] = useState(0);
  const [critical, setCritical] = useState(0);

  useEffect(() => {
    const loadCount = async () => {
      try {
        const annoCorrente = anno || new Date().getFullYear();
        const res = await api.get(`/api/verifica-coerenza/widget?anno=${annoCorrente}`);
        setCount(res.data?.totale_discrepanze || 0);
        setCritical(res.data?.critical_count || 0);
      } catch (err) {
        console.error('Errore badge verifica:', err);
      }
    };
    loadCount();
  }, [anno]);

  if (count === 0) return null;

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '2px 8px',
        borderRadius: 12,
        fontSize: 11,
        fontWeight: 'bold',
        background: critical > 0 ? '#dc2626' : '#f59e0b',
        color: 'white'
      }}
      title={`${count} discrepanze nei dati${critical > 0 ? ` (${critical} critiche)` : ''}`}
    >
      <AlertTriangle size={12} />
      {count}
    </span>
  );
}
