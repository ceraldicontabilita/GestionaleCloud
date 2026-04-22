import React, { useState, useEffect, useCallback } from 'react';
import {
  COLORS,
  STYLES,
  SPACING,
  SHADOWS,
  BORDER_RADIUS,
  FONT,
  button,
  badge,
  formatEuro,
  formatDateIT,
  formatDateShort,
  useIsMobile,
  RG,
} from '../lib/utils';

const API = import.meta.env.VITE_BACKEND_URL || '';

/* ================================================================
   DASHBOARD RELAZIONALE — Ceraldi ERP
   Vista unificata: alert, partite aperte, riconciliazione, stato moduli.
   Usa SOLO il design system da utils.js (no Tailwind, no Shadcn).
   ================================================================ */

export default function DashboardRelazionale() {
  const isMobile = useIsMobile();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [tabAttiva, setTabAttiva] = useState('panoramica');
  const [alertFilter, setAlertFilter] = useState('tutti');

  const caricaDati = useCallback(async () => {
    setLoading(true);
    try {
      const [alertRes, partiteRes, matchRes] = await Promise.allSettled([
        fetch(`${API}/api/alerts/lista?risolto=false&limit=200`).then(r => r.json()),
        fetch(`${API}/api/partite-aperte/stats`).then(r => r.json()),
        fetch(`${API}/api/riconciliazione/stats`).then(r => r.json()),
      ]);

      setData({
        alerts: alertRes.status === 'fulfilled' ? alertRes.value : { alerts: [], stats: {} },
        partite: partiteRes.status === 'fulfilled' ? partiteRes.value : {},
        match: matchRes.status === 'fulfilled' ? matchRes.value : {},
      });
    } catch (e) {
      console.error('Errore caricamento dashboard:', e);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    caricaDati();
  }, [caricaDati]);

  const alerts = data?.alerts?.alerts || [];
  const alertStats = data?.alerts?.stats || {};
  const partiteStats = data?.partite || {};
  const matchStats = data?.match || {};

  // Raggruppamento alert per modulo
  const alertPerModulo = {};
  alerts.forEach(a => {
    const mod = a.modulo || 'altro';
    if (!alertPerModulo[mod]) alertPerModulo[mod] = [];
    alertPerModulo[mod].push(a);
  });

  // Conteggi severità
  const critici = alerts.filter(a => a.severita === 'critical').length;
  const warning = alerts.filter(a => a.severita === 'warning').length;
  const info = alerts.filter(a => a.severita === 'info').length;

  const tabs = [
    { id: 'panoramica', label: '📊 Panoramica', count: null },
    { id: 'alert', label: '🔔 Alert', count: alertStats.non_risolti || alerts.length },
    { id: 'partite', label: '📋 Partite Aperte', count: null },
    { id: 'riconciliazione', label: '🔗 Riconciliazione', count: null },
  ];

  return (
    <div style={STYLES.page}>
      {/* HEADER */}
      <div style={STYLES.pageHeader}>
        <div>
          <h1 style={STYLES.pageTitle}>📊 Dashboard Relazionale</h1>
          <p style={STYLES.pageSubtitle}>
            Stato completo del gestionale — alert, partite, riconciliazione
          </p>
        </div>
        <button style={button('secondary')} onClick={caricaDati} disabled={loading}>
          {loading ? '⏳ Caricamento...' : '🔄 Aggiorna'}
        </button>
      </div>

      {/* TAB BAR */}
      <div style={STYLES.tabBar}>
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTabAttiva(t.id)}
            style={{
              ...button(tabAttiva === t.id ? 'primary' : 'ghost'),
              fontSize: 13,
              padding: '7px 14px',
              position: 'relative',
            }}
          >
            {t.label}
            {t.count > 0 && (
              <span
                style={{
                  ...badge('danger'),
                  marginLeft: 6,
                  fontSize: 10,
                  padding: '2px 6px',
                  minWidth: 18,
                  textAlign: 'center',
                }}
              >
                {t.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* CONTENUTO */}
      <div style={STYLES.pageInner}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 60, color: COLORS.textMuted }}>
            ⏳ Caricamento dashboard...
          </div>
        ) : tabAttiva === 'panoramica' ? (
          <TabPanoramica
            alerts={alerts}
            critici={critici}
            warning={warning}
            info={info}
            partiteStats={partiteStats}
            matchStats={matchStats}
            alertPerModulo={alertPerModulo}
            isMobile={isMobile}
          />
        ) : tabAttiva === 'alert' ? (
          <TabAlert
            alerts={alerts}
            alertPerModulo={alertPerModulo}
            filter={alertFilter}
            setFilter={setAlertFilter}
            onRefresh={caricaDati}
            isMobile={isMobile}
          />
        ) : tabAttiva === 'partite' ? (
          <TabPartite stats={partiteStats} isMobile={isMobile} />
        ) : (
          <TabRiconciliazione stats={matchStats} isMobile={isMobile} />
        )}
      </div>
    </div>
  );
}

/* ================================================================
   TAB PANORAMICA — KPI + alert critici + stato moduli
   ================================================================ */
function TabPanoramica({
  alerts,
  critici,
  warning,
  info,
  partiteStats,
  matchStats,
  alertPerModulo,
  isMobile,
}) {
  const kpis = [
    { label: 'Alert Critici', value: critici, color: COLORS.danger, icon: '🚨' },
    { label: 'Alert Warning', value: warning, color: COLORS.warning, icon: '⚠️' },
    { label: 'Alert Info', value: info, color: COLORS.info, icon: 'ℹ️' },
    { label: 'Alert Totali', value: alerts.length, color: COLORS.primary, icon: '🔔' },
  ];

  // Partite aperte totali
  const totPartite = Object.values(partiteStats).reduce((acc, v) => acc + (v?.count || 0), 0);
  const totResiduo = Object.values(partiteStats).reduce(
    (acc, v) => acc + (v?.totale_residuo || 0),
    0
  );

  return (
    <div>
      {/* KPI ROW */}
      <div style={STYLES.kpiGrid}>
        {kpis.map((k, i) => (
          <div
            key={i}
            style={{
              ...STYLES.statBox,
              borderLeftColor: k.color,
            }}
          >
            <div
              style={{
                fontSize: 11,
                color: COLORS.textMuted,
                textTransform: 'uppercase',
                fontWeight: 700,
                letterSpacing: '0.4px',
                marginBottom: 4,
              }}
            >
              {k.icon} {k.label}
            </div>
            <div
              style={{
                fontSize: 28,
                fontWeight: 800,
                color: k.value > 0 ? k.color : COLORS.textSubtle,
              }}
            >
              {k.value}
            </div>
          </div>
        ))}
      </div>

      {/* RIGA 2: Partite + Riconciliazione */}
      <div style={RG.col2(isMobile)}>
        {/* Partite Aperte */}
        <div style={STYLES.card}>
          <div style={STYLES.sectionTitle}>📋 Partite Aperte</div>
          {totPartite === 0 ? (
            <div style={{ color: COLORS.textMuted, fontSize: 13 }}>Nessuna partita aperta</div>
          ) : (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
                <span style={{ fontSize: 13, color: COLORS.textMuted }}>{totPartite} partite</span>
                <span style={{ fontSize: 15, fontWeight: 700, color: COLORS.danger }}>
                  {formatEuro(totResiduo)}
                </span>
              </div>
              {Object.entries(partiteStats).map(([tipo, v]) => (
                <div
                  key={tipo}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '8px 0',
                    borderBottom: `1px solid ${COLORS.gray[100]}`,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={badge(_badgeTipoPartita(tipo))}>{_labelTipoPartita(tipo)}</span>
                    <span style={{ fontSize: 12, color: COLORS.textMuted }}>×{v.count}</span>
                  </div>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>
                    {formatEuro(v.totale_residuo)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Riconciliazione */}
        <div style={STYLES.card}>
          <div style={STYLES.sectionTitle}>🔗 Riconciliazione</div>
          {Object.keys(matchStats).length === 0 ? (
            <div style={{ color: COLORS.textMuted, fontSize: 13 }}>Nessun dato riconciliazione</div>
          ) : (
            <div>
              {Object.entries(matchStats).map(([stato, v]) => (
                <div
                  key={stato}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '8px 0',
                    borderBottom: `1px solid ${COLORS.gray[100]}`,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={badge(_badgeStatoMatch(stato))}>{stato}</span>
                    <span style={{ fontSize: 12, color: COLORS.textMuted }}>×{v.count}</span>
                  </div>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{formatEuro(v.totale)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ALERT CRITICI RECENTI */}
      {critici > 0 && (
        <div
          style={{
            ...STYLES.card,
            marginTop: SPACING.lg,
            borderLeft: `4px solid ${COLORS.danger}`,
          }}
        >
          <div style={STYLES.sectionTitle}>🚨 Alert Critici</div>
          {alerts
            .filter(a => a.severita === 'critical')
            .slice(0, 5)
            .map(a => (
              <AlertRow key={a.id} alert={a} />
            ))}
        </div>
      )}

      {/* STATO MODULI */}
      <div style={{ ...STYLES.card, marginTop: SPACING.lg }}>
        <div style={STYLES.sectionTitle}>📦 Alert per Modulo</div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(auto-fit, minmax(140px, 1fr))',
            gap: SPACING.sm,
          }}
        >
          {Object.entries(alertPerModulo)
            .sort((a, b) => b[1].length - a[1].length)
            .map(([modulo, list]) => {
              const hasCritici = list.some(a => a.severita === 'critical');
              const hasWarning = list.some(a => a.severita === 'warning');
              return (
                <div
                  key={modulo}
                  style={{
                    padding: '10px 12px',
                    borderRadius: BORDER_RADIUS.sm,
                    background: hasCritici
                      ? COLORS.dangerLight
                      : hasWarning
                        ? COLORS.warningLight
                        : COLORS.gray[50],
                    border: `1px solid ${hasCritici ? COLORS.danger : hasWarning ? COLORS.warning : COLORS.border}`,
                    textAlign: 'center',
                  }}
                >
                  <div
                    style={{
                      fontSize: 11,
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      color: COLORS.textMuted,
                      marginBottom: 4,
                    }}
                  >
                    {_iconModulo(modulo)} {modulo}
                  </div>
                  <div
                    style={{
                      fontSize: 20,
                      fontWeight: 800,
                      color: hasCritici
                        ? COLORS.danger
                        : hasWarning
                          ? COLORS.warning
                          : COLORS.primary,
                    }}
                  >
                    {list.length}
                  </div>
                </div>
              );
            })}
        </div>
      </div>
    </div>
  );
}

/* ================================================================
   TAB ALERT — Lista completa filtrata per modulo/severità
   ================================================================ */
function TabAlert({ alerts, alertPerModulo, filter, setFilter, onRefresh, isMobile }) {
  const moduli = ['tutti', ...Object.keys(alertPerModulo).sort()];
  const filtrati = filter === 'tutti' ? alerts : alertPerModulo[filter] || [];

  return (
    <div>
      {/* Filtri */}
      <div style={{ ...STYLES.flexRow, marginBottom: SPACING.lg, flexWrap: 'wrap', gap: 6 }}>
        {moduli.map(m => (
          <button
            key={m}
            onClick={() => setFilter(m)}
            style={{
              ...button(filter === m ? 'primary' : 'secondary'),
              fontSize: 12,
              padding: '5px 12px',
            }}
          >
            {m === 'tutti' ? '📋 Tutti' : `${_iconModulo(m)} ${m}`}
            {m !== 'tutti' && ` (${alertPerModulo[m]?.length || 0})`}
          </button>
        ))}
      </div>

      {/* Lista alert */}
      {filtrati.length === 0 ? (
        <div style={{ ...STYLES.card, textAlign: 'center', padding: 40, color: COLORS.textMuted }}>
          ✅ Nessun alert aperto {filter !== 'tutti' ? `per ${filter}` : ''}
        </div>
      ) : (
        <div style={STYLES.card}>
          {filtrati.map(a => (
            <AlertRow key={a.id} alert={a} showModulo={filter === 'tutti'} />
          ))}
        </div>
      )}
    </div>
  );
}

/* ================================================================
   TAB PARTITE APERTE — Dettaglio per tipo
   ================================================================ */
function TabPartite({ stats, isMobile }) {
  const [partite, setPartite] = useState([]);
  const [tipoFiltro, setTipoFiltro] = useState('');
  const [loading, setLoading] = useState(false);

  const caricaPartite = useCallback(async tipo => {
    setLoading(true);
    try {
      const url = tipo
        ? `${API}/api/partite-aperte/lista?tipo=${tipo}&stato=aperta&limit=50`
        : `${API}/api/partite-aperte/lista?stato=aperta&limit=50`;
      const res = await fetch(url).then(r => r.json());
      setPartite(res.partite || res || []);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    caricaPartite(tipoFiltro);
  }, [tipoFiltro, caricaPartite]);

  const tipi = ['', 'fattura_fornitore', 'f24', 'stipendio', 'pos_atteso', 'trasferimento'];

  return (
    <div>
      {/* KPI */}
      <div style={STYLES.kpiGrid}>
        {Object.entries(stats).map(([tipo, v]) => (
          <div
            key={tipo}
            style={{
              ...STYLES.statBox,
              borderLeftColor: _colorTipoPartita(tipo),
              cursor: 'pointer',
            }}
            onClick={() => setTipoFiltro(tipo)}
          >
            <div
              style={{
                fontSize: 11,
                color: COLORS.textMuted,
                textTransform: 'uppercase',
                fontWeight: 700,
                marginBottom: 4,
              }}
            >
              {_labelTipoPartita(tipo)}
            </div>
            <div style={{ fontSize: 22, fontWeight: 800, color: COLORS.primary }}>{v.count}</div>
            <div style={{ fontSize: 13, color: COLORS.danger, fontWeight: 600 }}>
              {formatEuro(v.totale_residuo)}
            </div>
          </div>
        ))}
      </div>

      {/* Filtri */}
      <div style={{ ...STYLES.flexRow, marginBottom: SPACING.md, gap: 6 }}>
        {tipi.map(t => (
          <button
            key={t || 'all'}
            onClick={() => setTipoFiltro(t)}
            style={{
              ...button(tipoFiltro === t ? 'primary' : 'secondary'),
              fontSize: 12,
              padding: '5px 12px',
            }}
          >
            {t ? _labelTipoPartita(t) : '📋 Tutte'}
          </button>
        ))}
      </div>

      {/* Tabella */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: COLORS.textMuted }}>
          ⏳ Caricamento...
        </div>
      ) : (
        <div style={STYLES.tableWrap}>
          <table style={STYLES.table}>
            <thead>
              <tr>
                <th style={STYLES.th}>Tipo</th>
                <th style={STYLES.th}>Controparte</th>
                <th style={STYLES.th}>Importo</th>
                <th style={STYLES.th}>Residuo</th>
                <th style={STYLES.th}>Scadenza</th>
                <th style={STYLES.th}>Stato</th>
              </tr>
            </thead>
            <tbody>
              {(Array.isArray(partite) ? partite : []).map(p => (
                <tr key={p.id}>
                  <td style={STYLES.td}>
                    <span style={badge(_badgeTipoPartita(p.tipo))}>
                      {_labelTipoPartita(p.tipo)}
                    </span>
                  </td>
                  <td style={STYLES.td}>{p.controparte_nome || '-'}</td>
                  <td style={STYLES.td}>{formatEuro(p.importo_originale)}</td>
                  <td
                    style={{
                      ...STYLES.td,
                      fontWeight: 700,
                      color: p.residuo > 0 ? COLORS.danger : COLORS.success,
                    }}
                  >
                    {formatEuro(p.residuo)}
                  </td>
                  <td style={STYLES.td}>{p.data_scadenza ? formatDateIT(p.data_scadenza) : '-'}</td>
                  <td style={STYLES.td}>
                    <span
                      style={badge(
                        p.stato === 'chiusa'
                          ? 'success'
                          : p.stato === 'parziale'
                            ? 'warning'
                            : 'neutral'
                      )}
                    >
                      {p.stato}
                    </span>
                  </td>
                </tr>
              ))}
              {(!partite || partite.length === 0) && (
                <tr>
                  <td
                    colSpan={6}
                    style={{ ...STYLES.td, textAlign: 'center', color: COLORS.textMuted }}
                  >
                    Nessuna partita
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ================================================================
   TAB RICONCILIAZIONE — Stato match
   ================================================================ */
function TabRiconciliazione({ stats, isMobile }) {
  return (
    <div>
      <div style={STYLES.kpiGrid}>
        {Object.entries(stats).map(([stato, v]) => (
          <div key={stato} style={{ ...STYLES.statBox, borderLeftColor: _colorStatoMatch(stato) }}>
            <div
              style={{
                fontSize: 11,
                color: COLORS.textMuted,
                textTransform: 'uppercase',
                fontWeight: 700,
                marginBottom: 4,
              }}
            >
              {stato}
            </div>
            <div style={{ fontSize: 22, fontWeight: 800, color: COLORS.primary }}>{v.count}</div>
            <div style={{ fontSize: 13, color: COLORS.textMuted, fontWeight: 600 }}>
              {formatEuro(v.totale)}
            </div>
          </div>
        ))}
      </div>

      {Object.keys(stats).length === 0 && (
        <div style={{ ...STYLES.card, textAlign: 'center', padding: 40, color: COLORS.textMuted }}>
          Nessun dato di riconciliazione disponibile.
          <br />I match appariranno qui dopo l'import dell'estratto conto.
        </div>
      )}
    </div>
  );
}

/* ================================================================
   COMPONENTI HELPER
   ================================================================ */
function AlertRow({ alert: a, showModulo = true }) {
  const sevColors = {
    critical: { bg: COLORS.dangerLight, border: COLORS.danger, icon: '🚨' },
    warning: { bg: COLORS.warningLight, border: COLORS.warning, icon: '⚠️' },
    info: { bg: COLORS.infoLight, border: COLORS.info, icon: 'ℹ️' },
  };
  const sev = sevColors[a.severita] || sevColors.info;

  return (
    <div
      style={{
        display: 'flex',
        gap: 10,
        alignItems: 'flex-start',
        padding: '10px 0',
        borderBottom: `1px solid ${COLORS.gray[100]}`,
      }}
    >
      <span style={{ fontSize: 16 }}>{sev.icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          {showModulo && <span style={badge('primary')}>{a.modulo}</span>}
          <span style={{ fontSize: 13, fontWeight: 600, color: COLORS.text }}>{a.titolo}</span>
        </div>
        <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 2 }}>{a.dettaglio}</div>
        <div style={{ fontSize: 11, color: COLORS.textSubtle, marginTop: 2 }}>
          {a.codice} · {a.created_at ? formatDateShort(a.created_at) : ''}
        </div>
      </div>
      <span
        style={badge(
          a.severita === 'critical' ? 'danger' : a.severita === 'warning' ? 'warning' : 'info'
        )}
      >
        {a.severita}
      </span>
    </div>
  );
}

/* ================================================================
   UTILITY MAPPATURE
   ================================================================ */
function _labelTipoPartita(tipo) {
  const map = {
    fattura_fornitore: 'Fatture',
    nota_credito: 'Note Credito',
    f24: 'F24',
    stipendio: 'Stipendi',
    pos_atteso: 'POS',
    trasferimento: 'Trasferimenti',
    altro: 'Altro',
  };
  return map[tipo] || tipo;
}

function _badgeTipoPartita(tipo) {
  const map = {
    fattura_fornitore: 'warning',
    nota_credito: 'danger',
    f24: 'info',
    stipendio: 'primary',
    pos_atteso: 'accent',
    trasferimento: 'neutral',
    altro: 'neutral',
  };
  return map[tipo] || 'neutral';
}

function _colorTipoPartita(tipo) {
  const map = {
    fattura_fornitore: COLORS.warning,
    f24: COLORS.info,
    stipendio: COLORS.primary,
    pos_atteso: COLORS.accent,
    trasferimento: COLORS.textMuted,
  };
  return map[tipo] || COLORS.primary;
}

function _badgeStatoMatch(stato) {
  const map = { confermato: 'success', candidato: 'warning', respinto: 'danger' };
  return map[stato] || 'neutral';
}

function _colorStatoMatch(stato) {
  const map = { confermato: COLORS.success, candidato: COLORS.warning, respinto: COLORS.danger };
  return map[stato] || COLORS.primary;
}

function _iconModulo(modulo) {
  const map = {
    fornitori: '🏢',
    fatture: '📄',
    f24: '🏛️',
    cedolini: '💰',
    dipendenti: '👤',
    banca: '🏦',
    cassa: '💵',
    magazzino: '📦',
    documenti: '📁',
    riconciliazione: '🔗',
  };
  return map[modulo] || '📌';
}
