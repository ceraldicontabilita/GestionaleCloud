import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';
import { formatEuro, COLORS, BORDER_RADIUS } from '../lib/utils';
import { Badge, Button } from './ds';
import {
  AlertTriangle,
  CheckCircle,
  XCircle,
  ChevronDown,
  ChevronUp,
  RefreshCw,
} from 'lucide-react';

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
      <div
        style={{
          padding: 10,
          background: COLORS.bg,
          borderRadius: BORDER_RADIUS.md,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          fontSize: 13,
          color: COLORS.textMuted,
        }}
      >
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
      <Badge
        variant="success"
        style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 12px' }}
      >
        <CheckCircle size={16} />
        Dati coerenti
      </Badge>
    );
  }

  // Se ci sono discrepanze, mostra alert
  if (verifica.has_discrepanze) {
    const critico = verifica.critical_count > 0;
    const severityColor = critico ? COLORS.danger : COLORS.warning;
    const severityBg = critico ? COLORS.dangerLight : COLORS.warningLight;
    const severityBorder = severityBg;

    return (
      <div
        style={{
          background: severityBg,
          borderRadius: BORDER_RADIUS.md,
          border: `1px solid ${severityBorder}`,
          marginBottom: 16,
        }}
      >
        {/* Header */}
        <div
          onClick={() => setExpanded(!expanded)}
          style={{
            padding: '12px 16px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            cursor: 'pointer',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {critico ? (
              <XCircle size={20} color={COLORS.danger} />
            ) : (
              <AlertTriangle size={20} color={COLORS.warning} />
            )}
            <div>
              <div style={{ fontWeight: 'bold', color: severityColor, fontSize: 14 }}>
                ⚠️ {verifica.totale_discrepanze} Discrepanze Rilevate - {verifica.mese_nome}{' '}
                {verifica.anno}
              </div>
              <div style={{ fontSize: 12, color: COLORS.textMuted }}>
                {verifica.critical_count > 0 && `${verifica.critical_count} critiche • `}
                Clicca per dettagli
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Button
              variant="ghost"
              size="sm"
              onClick={e => {
                e.stopPropagation();
                loadVerifica();
              }}
              title="Ricarica"
              style={{ padding: 4 }}
            >
              <RefreshCw size={16} color={COLORS.textMuted} />
            </Button>
            {expanded ? (
              <ChevronUp size={20} color={COLORS.textMuted} />
            ) : (
              <ChevronDown size={20} color={COLORS.textMuted} />
            )}
          </div>
        </div>

        {/* Dettaglio discrepanze */}
        {expanded && (
          <div
            style={{
              padding: '0 16px 16px',
              borderTop: '1px solid ' + severityBorder,
            }}
          >
            {verifica.discrepanze?.map((d, idx) => (
              <div
                key={idx}
                style={{
                  padding: 12,
                  marginTop: 12,
                  background: COLORS.card,
                  borderRadius: BORDER_RADIUS.sm,
                  border: `1px solid ${d.severita === 'critical' ? COLORS.dangerLight : COLORS.warningLight}`,
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
                    <div
                      style={{
                        fontWeight: 'bold',
                        color: d.severita === 'critical' ? COLORS.danger : COLORS.warning,
                        fontSize: 13,
                      }}
                    >
                      {d.categoria} - {d.sottocategoria}
                    </div>
                    <div style={{ fontSize: 13, color: COLORS.gray[600], marginTop: 4 }}>
                      {d.descrizione}
                    </div>
                    {d.periodo && (
                      <div style={{ fontSize: 12, color: COLORS.textSubtle, marginTop: 2 }}>
                        Periodo: {d.periodo}
                      </div>
                    )}
                  </div>
                  <div style={{ textAlign: 'right', minWidth: 120 }}>
                    <div style={{ fontSize: 12, color: COLORS.textMuted }}>Atteso</div>
                    <div style={{ fontWeight: 'bold', color: COLORS.success }}>
                      {formatEuro(d.valore_atteso)}
                    </div>
                    <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>
                      Trovato
                    </div>
                    <div style={{ fontWeight: 'bold', color: COLORS.danger }}>
                      {formatEuro(d.valore_trovato)}
                    </div>
                    <Badge
                      variant={d.differenza > 0 ? 'danger' : 'info'}
                      style={{ marginTop: 4, fontSize: 13 }}
                    >
                      Diff: {d.differenza > 0 ? '+' : ''}
                      {formatEuro(d.differenza)}
                    </Badge>
                  </div>
                </div>
                {d.suggerimento && (
                  <div
                    style={{
                      marginTop: 8,
                      padding: 8,
                      background: COLORS.bgAlt,
                      borderRadius: BORDER_RADIUS.sm,
                      fontSize: 12,
                      color: COLORS.textMuted,
                    }}
                  >
                    💡 {d.suggerimento}
                  </div>
                )}
              </div>
            ))}

            {verifica.totale_discrepanze > 5 && (
              <div
                style={{
                  textAlign: 'center',
                  marginTop: 12,
                  padding: 8,
                  background: COLORS.bg,
                  borderRadius: BORDER_RADIUS.sm,
                  fontSize: 13,
                  color: COLORS.textMuted,
                }}
              >
                E altre {verifica.totale_discrepanze - 5} discrepanze...
                <Link
                  to="/verifica-coerenza"
                  style={{ marginLeft: 8, color: COLORS.info, textDecoration: 'none' }}
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
    <Badge
      variant={critical > 0 ? 'danger' : 'warning'}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
      title={`${count} discrepanze nei dati${critical > 0 ? ` (${critical} critiche)` : ''}`}
    >
      <AlertTriangle size={12} />
      {count}
    </Badge>
  );
}
