/**
 * HRHub.jsx — Hub Risorse Umane
 *
 * Dashboard di accesso ai 7 moduli HR con KPI live e grafica stile dipendenti-cloud
 * ma colori Ceraldi (navy + oro).
 *
 * Moduli:
 *  1. Anagrafica (→ /dipendenti)
 *  2. Presenze (→ /presenze)
 *  3. Ferie & Permessi (→ /ferie-permessi)
 *  4. Turni (→ /turni)
 *  5. Buste Paga / Cedolini (→ /cedolini)
 *  6. Missioni (→ /missioni)
 *  7. Documenti HR (→ /hr-documenti)
 *
 * Design: card con icona circolare colorata, KPI live, hover effect.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useAbortableEffect, isCanceledError } from '../../hooks';
import { useNavigate } from 'react-router-dom';
import {
  Users, Clock, CalendarDays, CalendarClock, FileText, MapPin, FolderOpen,
  ArrowRight, TrendingUp, AlertTriangle,
} from 'lucide-react';
import api from '../../api';
import { COLORS, SPACING, useIsMobile } from '../../lib/utils';

// ═════════════════════════════════════════════════════════════════════════

export default function HRHub() {
  const isMobile = useIsMobile();
  const navigate = useNavigate();

  const [stats, setStats] = useState({
    dipendenti: 0,
    richieste_in_attesa: 0,
    missioni_in_attesa: 0,
    documenti_in_scadenza: 0,
  });
  const [loading, setLoading] = useState(true);

  const loadStats = useCallback(async (signal) => {
    setLoading(true);
    try {
      const [dipRes, richRes, misRes, docRes] = await Promise.all([
        api.get('/api/dipendenti', { signal })
          .catch((e) => { if (isCanceledError(e)) throw e; return { data: [] }; }),
        api.get('/api/ferie-richieste?stato=in_attesa', { signal })
          .catch((e) => { if (isCanceledError(e)) throw e; return { data: [] }; }),
        api.get('/api/missioni?stato=in_attesa', { signal })
          .catch((e) => { if (isCanceledError(e)) throw e; return { data: [] }; }),
        api.get('/api/hr-documenti/in-scadenza?days=30', { signal })
          .catch((e) => { if (isCanceledError(e)) throw e; return { data: [] }; }),
      ]);
      if (signal?.aborted) return;
      setStats({
        dipendenti: (Array.isArray(dipRes.data) ? dipRes.data : []).filter((d) => (d.in_carico !== false && d.attivo !== false)).length,
        richieste_in_attesa: Array.isArray(richRes.data) ? richRes.data.length : 0,
        missioni_in_attesa: Array.isArray(misRes.data) ? misRes.data.length : 0,
        documenti_in_scadenza: Array.isArray(docRes.data) ? docRes.data.length : 0,
      });
    } catch (e) {
      if (isCanceledError(e)) return;
      console.error('[HRHub] stats error:', e);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useAbortableEffect((signal) => { loadStats(signal); }, [loadStats]);

  const moduli = useMemo(() => [
    {
      path: '/dipendenti',
      titolo: 'Anagrafica',
      descrizione: 'Dati personali, contratti, fascicolo dipendente',
      icon: Users,
      color: COLORS.primary,
      bg: COLORS.primarySoft,
      badge: stats.dipendenti > 0 ? `${stats.dipendenti} attivi` : null,
      badgeColor: COLORS.primary,
    },
    {
      path: '/presenze',
      titolo: 'Presenze',
      descrizione: 'Calendario mensile presenze e giustificativi',
      icon: Clock,
      color: COLORS.info,
      bg: COLORS.infoLight,
      badge: null,
    },
    {
      path: '/ferie-permessi',
      titolo: 'Ferie & Permessi',
      descrizione: 'Richieste con workflow di approvazione',
      icon: CalendarDays,
      color: COLORS.warning,
      bg: COLORS.warningLight,
      badge: stats.richieste_in_attesa > 0 ? `${stats.richieste_in_attesa} in attesa` : null,
      badgeColor: COLORS.warning,
    },
    {
      path: '/turni',
      titolo: 'Turni',
      descrizione: 'Pianificazione settimanale turni dipendenti',
      icon: CalendarClock,
      color: COLORS.accent,
      bg: COLORS.accentSoft,
      badge: null,
    },
    {
      path: '/cedolini',
      titolo: 'Buste Paga',
      descrizione: 'Cedolini, calcoli salariali, prima nota stipendi',
      icon: FileText,
      color: COLORS.success,
      bg: COLORS.successLight,
      badge: null,
    },
    {
      path: '/missioni',
      titolo: 'Missioni',
      descrizione: 'Trasferte, rimborsi, workflow approvazione',
      icon: MapPin,
      color: '#7c3aed',
      bg: '#f3e8ff',
      badge: stats.missioni_in_attesa > 0 ? `${stats.missioni_in_attesa} in attesa` : null,
      badgeColor: '#7c3aed',
    },
    {
      path: '/hr-documenti',
      titolo: 'Documenti HR',
      descrizione: 'Archivio documenti personali e scadenze',
      icon: FolderOpen,
      color: COLORS.danger,
      bg: COLORS.dangerLight,
      badge: stats.documenti_in_scadenza > 0 ? `${stats.documenti_in_scadenza} in scadenza` : null,
      badgeColor: COLORS.danger,
    },
    {
      path: '/presenze/attendance',
      titolo: 'Registro Presenze',
      descrizione: 'Inserimento batch presenze, PDF consulente, giustificativi',
      icon: Clock,
      color: '#0891b2',
      bg: '#ecfeff',
      badge: null,
    },
    {
      path: '/saldi-ferie-permessi',
      titolo: 'Saldi Ferie & Permessi',
      descrizione: 'Consuntivo saldi finali ferie, permessi e ROL per dipendente',
      icon: CalendarDays,
      color: '#059669',
      bg: '#ecfdf5',
      badge: null,
    },
  ], [stats]);

  // ═══════════════════════════════════════════════════════════════════════
  return (
    <div style={{ padding: isMobile ? SPACING.lg : SPACING.xxl, minHeight: '100vh', backgroundColor: COLORS.bg }}>
      {/* HEADER */}
      <div style={{ marginBottom: SPACING.xxl }}>
        <h1 style={{ fontSize: 32, fontWeight: 700, color: COLORS.text, margin: 0, letterSpacing: '-0.02em' }}>
          Risorse Umane
        </h1>
        <p style={{ fontSize: 15, color: COLORS.textMuted, margin: '6px 0 0' }}>
          Gestione completa dipendenti Ceraldi Group SRL
        </p>
      </div>

      {/* KPI SUMMARY */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: SPACING.lg,
        marginBottom: SPACING.xxl,
      }}>
        <SummaryCard
          label="Dipendenti attivi"
          value={stats.dipendenti}
          icon={Users}
          color={COLORS.primary}
          bg={COLORS.primarySoft}
          loading={loading}
        />
        <SummaryCard
          label="Ferie/permessi da approvare"
          value={stats.richieste_in_attesa}
          icon={CalendarDays}
          color={COLORS.warning}
          bg={COLORS.warningLight}
          loading={loading}
          highlight={stats.richieste_in_attesa > 0}
        />
        <SummaryCard
          label="Missioni da approvare"
          value={stats.missioni_in_attesa}
          icon={MapPin}
          color="#7c3aed"
          bg="#f3e8ff"
          loading={loading}
          highlight={stats.missioni_in_attesa > 0}
        />
        <SummaryCard
          label="Documenti in scadenza"
          value={stats.documenti_in_scadenza}
          icon={AlertTriangle}
          color={COLORS.danger}
          bg={COLORS.dangerLight}
          loading={loading}
          highlight={stats.documenti_in_scadenza > 0}
        />
      </div>

      {/* MODULI */}
      <div style={{ marginBottom: SPACING.md }}>
        <h2 style={{ fontSize: 18, fontWeight: 600, color: COLORS.text, margin: `0 0 ${SPACING.lg}px 0` }}>
          Moduli HR
        </h2>
      </div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: `repeat(auto-fill, minmax(${isMobile ? '260px' : '320px'}, 1fr))`,
        gap: SPACING.lg,
      }}>
        {moduli.map((m) => (
          <ModuloCard key={m.path} modulo={m} onClick={() => navigate(m.path)} />
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
function SummaryCard({ label, value, icon: Icon, color, bg, loading, highlight }) {
  return (
    <div style={{
      backgroundColor: COLORS.card,
      border: `1px solid ${highlight ? color + '60' : COLORS.border}`,
      borderRadius: 12,
      padding: SPACING.lg,
      display: 'flex',
      alignItems: 'center',
      gap: SPACING.md,
      boxShadow: highlight ? `0 2px 8px ${color}15` : 'none',
      transition: 'all 0.15s',
    }}>
      <div style={{
        width: 48, height: 48, borderRadius: 12,
        backgroundColor: bg,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0,
      }}>
        <Icon size={24} color={color} />
      </div>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.text, lineHeight: 1 }}>
          {loading ? '—' : value}
        </div>
        <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>
          {label}
        </div>
      </div>
    </div>
  );
}

function ModuloCard({ modulo, onClick }) {
  const [hover, setHover] = useState(false);
  const Icon = modulo.icon;
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        backgroundColor: COLORS.card,
        border: `1px solid ${hover ? modulo.color + '80' : COLORS.border}`,
        borderRadius: 12,
        padding: SPACING.xl,
        textAlign: 'left',
        cursor: 'pointer',
        transition: 'all 0.2s',
        boxShadow: hover ? `0 8px 24px ${modulo.color}20` : '0 1px 3px rgba(15,39,68,0.04)',
        transform: hover ? 'translateY(-2px)' : 'none',
        width: '100%',
        fontFamily: 'inherit',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'start', justifyContent: 'space-between', marginBottom: SPACING.md }}>
        <div style={{
          width: 52, height: 52, borderRadius: 14,
          backgroundColor: modulo.bg,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon size={26} color={modulo.color} />
        </div>
        {modulo.badge && (
          <span style={{
            padding: '4px 10px',
            borderRadius: 12,
            backgroundColor: modulo.bg,
            color: modulo.badgeColor || modulo.color,
            fontSize: 11,
            fontWeight: 600,
            whiteSpace: 'nowrap',
          }}>
            {modulo.badge}
          </span>
        )}
      </div>
      <div style={{ fontSize: 17, fontWeight: 600, color: COLORS.text, marginBottom: 4 }}>
        {modulo.titolo}
      </div>
      <div style={{ fontSize: 13, color: COLORS.textMuted, marginBottom: SPACING.md, lineHeight: 1.5, minHeight: 38 }}>
        {modulo.descrizione}
      </div>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        fontSize: 13,
        fontWeight: 500,
        color: modulo.color,
        opacity: hover ? 1 : 0.7,
        transition: 'opacity 0.15s',
      }}>
        Apri modulo
        <ArrowRight size={14} style={{ transform: hover ? 'translateX(4px)' : 'none', transition: 'transform 0.15s' }} />
      </div>
    </button>
  );
}

