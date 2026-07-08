import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api';
import { StatCard } from './ds';
import { COLORS, SHADOWS, BORDER_RADIUS } from '../lib/utils';

const TIPI = [
  { key: 'urgente', label: 'Urgenti', accent: 'danger' },
  { key: 'avviso', label: 'Avvisi', accent: 'warning' },
  { key: 'info', label: 'Info', accent: 'info' },
  { key: 'suggerimento', label: 'Suggerimenti', accent: 'success' },
];

function minutiFa(iso) {
  if (!iso) return null;
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (diff < 1) return 'adesso';
  if (diff < 60) return `${diff} min fa`;
  const h = Math.floor(diff / 60);
  return `${h}h fa`;
}

export default function WidgetAgenti() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState({
    urgente: 0,
    avviso: 0,
    info: 0,
    suggerimento: 0,
    totale: 0,
  });
  const [lastUpdate, setLastUpdate] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const res = await api.get('/api/agenti/segnalazioni/summary');
      setSummary(res.data);
      setLastUpdate(new Date().toISOString());
    } catch {
      // silenzioso
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const iv = setInterval(load, 5 * 60 * 1000); // 5 minuti
    return () => clearInterval(iv);
  }, [load]);

  if (loading) return null;
  if (summary.totale === 0 && !loading) return null; // Nasconde se nessuna segnalazione

  return (
    <div
      data-testid="widget-agenti"
      style={{
        background: COLORS.card,
        border: `1px solid ${COLORS.border}`,
        borderRadius: BORDER_RADIUS.md,
        padding: '14px 18px',
        boxShadow: SHADOWS.sm,
        marginBottom: 16,
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div
            style={{
              width: 28,
              height: 28,
              borderRadius: BORDER_RADIUS.sm,
              background: COLORS.primaryLight,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#7dd3fc"
              strokeWidth="2.5"
            >
              <circle cx="12" cy="12" r="3" />
              <path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83" />
            </svg>
          </div>
          <span style={{ fontWeight: 700, fontSize: 13, color: COLORS.text }}>Agenti AI</span>
        </div>
        <span style={{ fontSize: 11, color: COLORS.textSubtle }}>
          {lastUpdate ? `Aggiornato ${minutiFa(lastUpdate)}` : ''}
        </span>
      </div>

      {/* Contatori */}
      <div style={{ display: 'flex', gap: 8 }}>
        {TIPI.map(t => (
          <div
            key={t.key}
            data-testid={`widget-agenti-${t.key}`}
            onClick={() => navigate(`/agenti`)}
            style={{ flex: 1, cursor: 'pointer' }}
          >
            <StatCard
              label={t.label}
              value={summary[t.key]}
              accent={summary[t.key] > 0 ? t.accent : 'none'}
              style={{ padding: '8px 4px', textAlign: 'center' }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
