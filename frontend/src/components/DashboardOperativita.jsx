import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, CalendarClock, FileUp, Landmark, Wrench } from 'lucide-react';
import api from '../api';
import { COLORS } from '../lib/utils';

const AZIONI = [
  { to: '/documenti/import', label: 'Importa documenti', Icon: FileUp },
  { to: '/riconciliazione', label: 'Riconcilia banca', Icon: Landmark },
  { to: '/scadenze', label: 'Apri scadenze', Icon: CalendarClock },
  { to: '/strumenti/commercialista', label: 'Commercialista', Icon: Wrench },
];

export default function DashboardOperativita({ scadenze, erroriApi = [] }) {
  const [alerts, setAlerts] = useState(null);
  const [alertsErrore, setAlertsErrore] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    api
      .get('/api/alerts/summary', { signal: controller.signal })
      .then(r => {
        setAlerts(r.data || null);
        setAlertsErrore(false);
      })
      .catch(e => {
        if (e?.name !== 'CanceledError' && e?.name !== 'AbortError') {
          setAlertsErrore(true);
        }
      });
    return () => controller.abort();
  }, []);

  const elencoScadenze = Array.isArray(scadenze?.scadenze) ? scadenze.scadenze : [];
  const scadenzeUrgenti = elencoScadenze.filter(s => Boolean(s?.urgente)).length;
  const alertAperti = alerts?.totale_aperti ?? null;
  const alertCritici = alerts?.per_severita?.critical ?? null;

  return (
    <section data-testid="dashboard-operativita" style={S.wrap}>
      <div style={S.header}>
        <div>
          <div style={S.eyebrow}>Operatività</div>
          <h2 style={S.title}>Cosa richiede attenzione</h2>
        </div>
        <div style={S.contatori}>
          <Link to="/dashboard/alerts" style={S.contatore} data-testid="dashboard-alert-counter">
            <AlertTriangle size={16} />
            <span>
              <strong>{alertsErrore ? '—' : alertAperti ?? '…'}</strong> alert aperti
              {alertCritici != null && alertCritici > 0 ? ` · ${alertCritici} critici` : ''}
            </span>
          </Link>
          <Link to="/scadenze" style={S.contatore} data-testid="dashboard-deadline-counter">
            <CalendarClock size={16} />
            <span>
              <strong>{elencoScadenze.length}</strong> scadenze nel periodo
              {scadenzeUrgenti > 0 ? ` · ${scadenzeUrgenti} urgenti` : ''}
            </span>
          </Link>
        </div>
      </div>

      {erroriApi.length > 0 && (
        <div style={S.warning} data-testid="dashboard-operativita-warning">
          Alcuni contatori possono essere incompleti perché {erroriApi.length} sezioni dati non sono disponibili.
        </div>
      )}

      <div style={S.actions} data-testid="dashboard-quick-actions">
        {AZIONI.map(({ to, label, Icon }) => (
          <Link key={to} to={to} style={S.action}>
            <Icon size={17} />
            <span>{label}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}

const S = {
  wrap: {
    margin: '12px 0 16px',
    padding: 14,
    background: '#ffffff',
    border: `1px solid ${COLORS.border}`,
    borderRadius: 12,
  },
  header: {
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
    flexWrap: 'wrap',
  },
  eyebrow: {
    color: COLORS.textMuted,
    fontSize: 11,
    fontWeight: 800,
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  title: {
    margin: '2px 0 0',
    fontSize: 18,
    color: COLORS.text,
  },
  contatori: {
    display: 'flex',
    gap: 8,
    flexWrap: 'wrap',
  },
  contatore: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 7,
    padding: '7px 10px',
    borderRadius: 8,
    background: '#f8fafc',
    border: `1px solid ${COLORS.border}`,
    color: COLORS.text,
    textDecoration: 'none',
    fontSize: 12,
  },
  warning: {
    marginTop: 10,
    padding: '8px 10px',
    borderRadius: 8,
    background: '#fffbeb',
    border: '1px solid #fde68a',
    color: '#92400e',
    fontSize: 12,
  },
  actions: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
    gap: 8,
    marginTop: 12,
  },
  action: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '10px 12px',
    borderRadius: 9,
    background: COLORS.primarySoft || '#eef4ff',
    color: COLORS.primary,
    textDecoration: 'none',
    fontSize: 13,
    fontWeight: 700,
    border: `1px solid ${COLORS.border}`,
  },
};
