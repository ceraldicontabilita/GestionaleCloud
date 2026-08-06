import React, { useState, useEffect, useCallback, useRef } from 'react';
import api from '../api';
import ModalFattura from '../components/ModalFattura';
import { useAnnoGlobale } from '../contexts/AnnoContext';
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
  const { anno } = useAnnoGlobale();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [erroriFonti, setErroriFonti] = useState({});
  const [tabAttiva, setTabAttiva] = useState('panoramica');
  const [alertFilter, setAlertFilter] = useState('tutti');
  const ultimoEstrattoRef = useRef(null);
  const [variazioneRiconciliazione, setVariazioneRiconciliazione] = useState(null);

  const caricaDati = useCallback(async ({ silenzioso = false } = {}) => {
    if (!silenzioso) setLoading(true);
    try {
      const [alertRes, partiteRes, matchRes] = await Promise.allSettled([
        api.get('/api/alerts/lista?risolto=false&limit=200').then(r => r.data),
        api.get('/api/partite-aperte/stats', { params: { anno } }).then(r => r.data),
        api.get('/api/riconciliazione/stats', { params: { anno } }).then(r => r.data),
      ]);

      setErroriFonti({
        alerts: alertRes.status === 'rejected' ? 'Alert di sistema non disponibili' : null,
        partite: partiteRes.status === 'rejected' ? `Partite ${anno} non disponibili` : null,
        riconciliazione:
          matchRes.status === 'rejected' ? `Riconciliazione ${anno} non disponibile` : null,
      });

      const match = matchRes.status === 'fulfilled' ? matchRes.value : {};
      const estratto = match?.sezioni?.estratto_conto;
      if (estratto && ultimoEstrattoRef.current) {
        const prima = ultimoEstrattoRef.current;
        const variazione = {
          riconciliati: estratto.riconciliati - prima.riconciliati,
          daRiconciliare: estratto.da_riconciliare - prima.da_riconciliare,
          totaleInvariato: estratto.totale === prima.totale,
        };
        if (variazione.riconciliati || variazione.daRiconciliare || !variazione.totaleInvariato) {
          setVariazioneRiconciliazione(variazione);
        }
      }
      if (estratto) ultimoEstrattoRef.current = estratto;

      setData({
        alerts: alertRes.status === 'fulfilled' ? alertRes.value : { alerts: [], stats: {} },
        partite: partiteRes.status === 'fulfilled' ? partiteRes.value : {},
        match,
      });
    } catch (e) {
      console.error('Errore caricamento dashboard:', e);
      setErroriFonti({ dashboard: 'Dashboard temporaneamente non disponibile' });
    }
    if (!silenzioso) setLoading(false);
  }, [anno]);

  useEffect(() => {
    caricaDati();
    const timer = window.setInterval(() => caricaDati({ silenzioso: true }), 60 * 1000);
    return () => window.clearInterval(timer);
  }, [caricaDati]);

  const alerts = data?.alerts?.alerts || [];
  const alertStats = data?.alerts?.stats || {};
  const partiteStats = data?.partite || {};
  const matchStats = data?.match?.stati || data?.match || {};
  const matchDetails = data?.match || {};

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
          <Button variant="secondary" onClick={() => caricaDati()} disabled={loading}>
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
        {Object.values(erroriFonti).some(Boolean) && (
          <div
            role="alert"
            style={{
              marginBottom: SPACING.md,
              padding: '12px 14px',
              border: `1px solid ${COLORS.danger}`,
              borderRadius: BORDER_RADIUS.sm,
              background: COLORS.dangerLight,
              color: COLORS.danger,
            }}
          >
            {Object.values(erroriFonti).filter(Boolean).join(' · ')}. I valori mancanti non sono zero.
          </div>
        )}
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
            erroriFonti={erroriFonti}
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
          <TabPartite
            stats={partiteStats}
            anno={anno}
            fonteNonDisponibile={Boolean(erroriFonti.partite)}
            isMobile={isMobile}
          />
        ) : (
          <TabRiconciliazione
            stats={matchStats}
            dettagli={matchDetails}
            variazione={variazioneRiconciliazione}
            fonteNonDisponibile={Boolean(erroriFonti.riconciliazione)}
            isMobile={isMobile}
          />
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
  erroriFonti,
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
          {erroriFonti.partite ? (
            <SourceUnavailable message={erroriFonti.partite} />
          ) : totPartite === 0 ? (
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
          {erroriFonti.riconciliazione ? (
            <SourceUnavailable message={erroriFonti.riconciliazione} />
          ) : Object.keys(matchStats).length === 0 ? (
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
function TabPartite({ stats, anno, fonteNonDisponibile, isMobile }) {
  const [fatturaView, setFatturaView] = useState(null);
  const [partite, setPartite] = useState([]);
  const [tipoFiltro, setTipoFiltro] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorePartite, setErrorePartite] = useState(null);

  const caricaPartite = useCallback(async tipo => {
    setLoading(true);
    setErrorePartite(null);
    try {
      const res = await api.get('/api/partite-aperte/lista', {
        params: {
          ...(tipo ? { tipo } : {}),
          stato: 'aperta',
          anno,
          limit: 50,
        },
      }).then(r => r.data);
      setPartite(res.partite || res || []);
    } catch (e) {
      console.error(e);
      setPartite([]);
      setErrorePartite(`Elenco partite ${anno} non disponibile`);
    }
    setLoading(false);
  }, [anno]);

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
      {fonteNonDisponibile || errorePartite ? (
        <SourceUnavailable message={errorePartite || `Partite ${anno} non disponibili`} />
      ) : loading ? (
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
                <Th>Azioni</Th>
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
                  <Td style={{ whiteSpace: 'nowrap' }}>
                    {(p.tipo === 'fattura_fornitore' || p.tipo === 'fattura') && p.documento_id ? (
                      <span style={{ display: 'inline-flex', gap: 6 }}>
                        <Button size="sm" variant="info" onClick={() => setFatturaView({ id: p.documento_id })}>
                          👁 Vedi
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => { window.location.href = '/prima-nota#sezione=provvisori'; }}
                        >
                          Apri Prima Nota
                        </Button>
                      </span>
                    ) : (
                      '—'
                    )}
                  </Td>
                </tr>
              ))}
              {(!partite || partite.length === 0) && (
                <tr>
                  <Td colSpan={7} style={{ textAlign: 'center', color: COLORS.textMuted }}>
                    Nessuna partita
                  </Td>
                </tr>
              )}
            </tbody>
          </Table>
        </TableWrap>
      )}
      {fatturaView && (
        <ModalFattura fatturaId={fatturaView.id} onClose={() => setFatturaView(null)} />
      )}
    </div>
  );
}

/* ================================================================
   TAB RICONCILIAZIONE — Stato match
   ================================================================ */
function TabRiconciliazione({ stats, dettagli, variazione, fonteNonDisponibile, isMobile }) {
  const estratto = dettagli?.sezioni?.estratto_conto;
  const quadratura = dettagli?.quadratura;
  if (fonteNonDisponibile) {
    return <SourceUnavailable message="Riconciliazione non disponibile" />;
  }
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

      {variazione && (
        <Card
          style={{
            marginBottom: SPACING.md,
            borderLeft: `4px solid ${variazione.totaleInvariato && variazione.riconciliati === -variazione.daRiconciliare ? COLORS.success : COLORS.danger}`,
          }}
          data-testid="variazione-riconciliazione"
        >
          <strong>Ultimo aggiornamento:</strong>{' '}
          riconciliati {variazione.riconciliati >= 0 ? '+' : ''}{variazione.riconciliati},
          da riconciliare {variazione.daRiconciliare >= 0 ? '+' : ''}{variazione.daRiconciliare}.
          {!variazione.totaleInvariato && ' Attenzione: il totale dei movimenti e cambiato.'}
        </Card>
      )}

      {estratto && (
        <Card title="Quadratura estratto conto" icon="✓" style={{ marginBottom: SPACING.md }}>
          <div style={RG.col2(isMobile)}>
            <div>
              <div>Movimenti totali: <strong>{estratto.totale}</strong></div>
              <div>Riconciliati: <strong style={{ color: COLORS.success }}>{estratto.riconciliati}</strong></div>
              <div>Da riconciliare: <strong style={{ color: COLORS.warning }}>{estratto.da_riconciliare}</strong></div>
            </div>
            <div>
              <Badge variant={quadratura?.ok ? 'success' : 'danger'}>
                {quadratura?.ok ? 'Quadratura corretta' : 'Quadratura incoerente'}
              </Badge>
              <div style={{ marginTop: 8, color: COLORS.textMuted, fontSize: 13 }}>
                {quadratura?.valori}
              </div>
            </div>
          </div>
        </Card>
      )}

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
function SourceUnavailable({ message }) {
  return (
    <div role="status" style={{ color: COLORS.danger, fontSize: 13 }}>
      ⚠️ {message}. Riprova con Aggiorna.
    </div>
  );
}

// Dall'alert al DOCUMENTO (richiesta utente 18/07/2026: "dalla finestra
// alert se clicco mi deve portare direttamente al documento in questione").
function _destinazioneAlert(a) {
  const coll = (a.entita_collection || '').toLowerCase();
  const id = a.entita_id;
  if (!id) return null;
  if (coll === 'invoices') return `/fatture?invoice_id=${id}`;
  if (coll.startsWith('prima_nota')) return '/prima-nota';
  if (coll.includes('f24')) return '/riconciliazione/f24';
  if (coll.includes('fornitori') || coll === 'suppliers') return `/fornitori#search=${id}`;
  if (coll.includes('corrispettivi')) return '/fatture/corrispettivi';
  if (coll.includes('estratto')) return '/riconciliazione';
  if (coll.includes('assegni')) return '/riconciliazione/assegni';
  if (coll.includes('cedolini') || coll.includes('salari')) return '/salari';
  if (coll.includes('attachment') || coll.includes('documenti') || coll.includes('inbox')) return '/documenti';
  return null;
}

function AlertRow({ alert: a, showModulo = true }) {
  const sevIcons = { critical: '🚨', warning: '⚠️', info: 'ℹ️' };
  const icon = sevIcons[a.severita] || sevIcons.info;
  const destinazione = _destinazioneAlert(a);

  return (
    <div
      onClick={destinazione ? () => { window.location.href = destinazione; } : undefined}
      title={destinazione ? 'Apri il documento' : undefined}
      style={{
        display: 'flex',
        gap: 10,
        alignItems: 'flex-start',
        padding: '10px 0',
        borderBottom: `1px solid ${COLORS.gray[100]}`,
        cursor: destinazione ? 'pointer' : 'default',
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
