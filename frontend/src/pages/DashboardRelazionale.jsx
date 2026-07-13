import React, { useState, useEffect, useCallback } from 'react';
import api from '../api';
import {
  COLORS,
  STYLES,
  SPACING,
  BORDER_RADIUS,
  formatEuro,
  formatDateIT,
  formatDateShort,
  useIsMobile,
  RG,
} from '../lib/utils';
import {
  Button,
  Badge,
  Card,
  StatCard,
  PageHeader,
  Tabs,
  TableWrap,
  Table,
  Th,
  Td,
} from '../components/ds';

// Il client `api` usa già baseURL='' (dominio corrente) + JWT interceptor.
// Non usiamo VITE_BACKEND_URL qui perché al build time può puntare a un
// dominio diverso e causare errori CORS in produzione.

/* ================================================================
   DASHBOARD RELAZIONALE — Ceraldi ERP
   Vista unificata: alert, partite aperte, riconciliazione, stato moduli.
   Usa SOLO il design system condiviso (COLORS/STYLES + componenti ds).
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
        api.get('/api/alerts/lista?risolto=false&limit=200').then(r => r.data),
        api.get('/api/partite-aperte/stats').then(r => r.data),
        api.get('/api/riconciliazione/stats').then(r => r.data),
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

  const alertCount = alertStats.non_risolti || alerts.length;

  const tabs = [
    { key: 'panoramica', icon: '📊', label: 'Panoramica' },
    {
      key: 'alert',
      icon: '🔔',
      label: (
        <>
          Alert
          {alertCount > 0 && (
            <Badge
              variant="danger"
              style={{
                marginLeft: 6,
                fontSize: 10,
                padding: '2px 6px',
                minWidth: 18,
                textAlign: 'center',
              }}
            >
              {alertCount}
            </Badge>
          )}
        </>
      ),
    },
    { key: 'partite', icon: '📋', label: 'Partite Aperte' },
    { key: 'riconciliazione', icon: '🔗', label: 'Riconciliazione' },
  ];

  return (
    <div style={STYLES.page}>
      {/* HEADER */}
      <PageHeader
        title="Dashboard Relazionale"
        icon="📊"
        subtitle="Stato completo del gestionale — alert, partite, riconciliazione"
        style={{ marginBottom: SPACING.lg }}
        actions={
          <Button variant="secondary" onClick={caricaDati} disabled={loading}>
            {loading ? '⏳ Caricamento...' : '🔄 Aggiorna'}
          </Button>
        }
      />

      {/* TAB BAR */}
      <div style={STYLES.tabBar}>
        <Tabs items={tabs} value={tabAttiva} onChange={setTabAttiva} />
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
    { label: 'Alert Critici', value: critici, accent: 'danger', icon: '🚨' },
    { label: 'Alert Warning', value: warning, accent: 'warning', icon: '⚠️' },
    { label: 'Alert Info', value: info, accent: 'info', icon: 'ℹ️' },
    { label: 'Alert Totali', value: alerts.length, accent: 'primary', icon: '🔔' },
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
          <StatCard key={i} icon={k.icon} label={k.label} value={k.value} accent={k.accent} />
        ))}
      </div>

      {/* RIGA 2: Partite + Riconciliazione */}
      <div style={RG.col2(isMobile)}>
        {/* Partite Aperte */}
        <Card title="Partite Aperte" icon="📋">
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
                    <Badge variant={_badgeTipoPartita(tipo)}>{_labelTipoPartita(tipo)}</Badge>
                    <span style={{ fontSize: 12, color: COLORS.textMuted }}>×{v.count}</span>
                  </div>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>
                    {formatEuro(v.totale_residuo)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Riconciliazione */}
        <Card title="Riconciliazione" icon="🔗">
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
                    <Badge variant={_badgeStatoMatch(stato)}>{stato}</Badge>
                    <span style={{ fontSize: 12, color: COLORS.textMuted }}>×{v.count}</span>
                  </div>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{formatEuro(v.totale)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* ALERT CRITICI RECENTI */}
      {critici > 0 && (
        <Card
          title="Alert Critici"
          icon="🚨"
          style={{ marginTop: SPACING.lg, borderLeft: `4px solid ${COLORS.danger}` }}
        >
          {alerts
            .filter(a => a.severita === 'critical')
            .slice(0, 5)
            .map(a => (
              <AlertRow key={a.id} alert={a} />
            ))}
        </Card>
      )}

      {/* STATO MODULI */}
      <Card title="Alert per Modulo" icon="📦" style={{ marginTop: SPACING.lg }}>
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
      </Card>
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
          <Button
            key={m}
            variant={filter === m ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setFilter(m)}
          >
            {m === 'tutti' ? '📋 Tutti' : `${_iconModulo(m)} ${m}`}
            {m !== 'tutti' && ` (${alertPerModulo[m]?.length || 0})`}
          </Button>
        ))}
      </div>

      {/* Lista alert */}
      {filtrati.length === 0 ? (
        <Card bodyStyle={{ textAlign: 'center', padding: 40, color: COLORS.textMuted }}>
          ✅ Nessun alert aperto {filter !== 'tutti' ? `per ${filter}` : ''}
        </Card>
      ) : (
        <Card>
          {filtrati.map(a => (
            <AlertRow key={a.id} alert={a} showModulo={filter === 'tutti'} />
          ))}
        </Card>
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
        ? `/api/partite-aperte/lista?tipo=${tipo}&stato=aperta&limit=50`
        : `/api/partite-aperte/lista?stato=aperta&limit=50`;
      const res = await api.get(url).then(r => r.data);
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
          <StatCard
            key={tipo}
            label={_labelTipoPartita(tipo)}
            value={v.count}
            subtext={formatEuro(v.totale_residuo)}
            style={{ borderLeftColor: _colorTipoPartita(tipo), cursor: 'pointer' }}
            onClick={() => setTipoFiltro(tipo)}
          />
        ))}
      </div>

      {/* Filtri */}
      <div style={{ ...STYLES.flexRow, marginBottom: SPACING.md, gap: 6 }}>
        {tipi.map(t => (
          <Button
            key={t || 'all'}
            variant={tipoFiltro === t ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setTipoFiltro(t)}
          >
            {t ? _labelTipoPartita(t) : '📋 Tutte'}
          </Button>
        ))}
      </div>

      {/* Tabella */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: COLORS.textMuted }}>
          ⏳ Caricamento...
        </div>
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Tipo</Th>
                <Th>Controparte</Th>
                <Th>Importo</Th>
                <Th>Residuo</Th>
                <Th>Scadenza</Th>
                <Th>Stato</Th>
              </tr>
            </thead>
            <tbody>
              {(Array.isArray(partite) ? partite : []).map(p => (
                <tr key={p.id}>
                  <Td>
                    <Badge variant={_badgeTipoPartita(p.tipo)}>{_labelTipoPartita(p.tipo)}</Badge>
                  </Td>
                  <Td>{p.controparte_nome || '-'}</Td>
                  <Td>{formatEuro(p.importo_originale)}</Td>
                  <Td
                    style={{
                      fontWeight: 700,
                      color: p.residuo > 0 ? COLORS.danger : COLORS.success,
                    }}
                  >
                    {formatEuro(p.residuo)}
                  </Td>
                  <Td>{p.data_scadenza ? formatDateIT(p.data_scadenza) : '-'}</Td>
                  <Td>
                    <Badge
                      variant={
                        p.stato === 'chiusa'
                          ? 'success'
                          : p.stato === 'parziale'
                            ? 'warning'
                            : 'neutral'
                      }
                    >
                      {p.stato}
                    </Badge>
                  </Td>
                </tr>
              ))}
              {(!partite || partite.length === 0) && (
                <tr>
                  <Td colSpan={6} style={{ textAlign: 'center', color: COLORS.textMuted }}>
                    Nessuna partita
                  </Td>
                </tr>
              )}
            </tbody>
          </Table>
        </TableWrap>
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
          <StatCard
            key={stato}
            label={stato}
            value={v.count}
            subtext={formatEuro(v.totale)}
            style={{ borderLeftColor: _colorStatoMatch(stato) }}
          />
        ))}
      </div>

      {Object.keys(stats).length === 0 && (
        <Card bodyStyle={{ textAlign: 'center', padding: 40, color: COLORS.textMuted }}>
          Nessun dato di riconciliazione disponibile.
          <br />I match appariranno qui dopo l'import dell'estratto conto.
        </Card>
      )}
    </div>
  );
}

/* ================================================================
   COMPONENTI HELPER
   ================================================================ */
function AlertRow({ alert: a, showModulo = true }) {
  const sevIcons = { critical: '🚨', warning: '⚠️', info: 'ℹ️' };
  const icon = sevIcons[a.severita] || sevIcons.info;

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
      <span style={{ fontSize: 16 }}>{icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          {showModulo && <Badge variant="primary">{a.modulo}</Badge>}
          <span style={{ fontSize: 13, fontWeight: 600, color: COLORS.text }}>{a.titolo}</span>
        </div>
        <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 2 }}>{a.dettaglio}</div>
        <div style={{ fontSize: 11, color: COLORS.textSubtle, marginTop: 2 }}>
          {a.codice} · {a.created_at ? formatDateShort(a.created_at) : ''}
        </div>
      </div>
      <Badge
        variant={a.severita === 'critical' ? 'danger' : a.severita === 'warning' ? 'warning' : 'info'}
      >
        {a.severita}
      </Badge>
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
