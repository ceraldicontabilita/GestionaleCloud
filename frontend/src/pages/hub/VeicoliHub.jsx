import React, { lazy, Suspense, useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../../api';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { PageLoader } from '../../components/ds';
import { PageHeader } from '../../components/ds/PageHeader';
import { COLORS, useIsMobile } from '../../lib/utils';
import { euroOppure } from '../../lib/vista';
import { sezioneNoleggio } from './sezioneNoleggio';
import { ChartColumn, ClipboardList, CreditCard, FileText, Receipt, Route, Siren, Wallet, Wrench } from 'lucide-react';

const ICO = { verticalAlign: '-2px', flexShrink: 0 };

const FlottaContent = lazy(() => import('../NoleggioAuto.jsx'));
const VerbaliContent = lazy(() => import('../VerbaliRiconciliazione.jsx'));
const PosizioneContent = lazy(() => import('../PosizioneNoleggio.jsx'));

const TABS = [
  { id: 'flotta', label: 'Flotta Auto', color: COLORS.primary },
  { id: 'posizione', label: 'Posizione auto e driver', color: COLORS.text },
  { id: 'verbali', label: 'Verbali Noleggio', color: COLORS.info },
  { id: 'costi', label: 'Riepilogo Costi', color: COLORS.success },
];


const getTabFromPath = sezioneNoleggio;

export const totaleAltriCosti = valori =>
  ['totale_pedaggio', 'totale_costi_extra', 'totale_riparazioni'].reduce(
    (totale, chiave) => totale + Number(valori?.[chiave] || 0),
    0
  );

function RiepilogoCosti({ anno }) {
  const isMobile = useIsMobile();
  const [limite, setLimite] = React.useState(200);
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    setLoading(true);
    api
      .get(`/api/noleggio/veicoli?anno=${anno}`)
      .then(r => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [anno]);

  if (loading) return <PageLoader />;
  if (!data)
    return (
      <div style={{ padding: 40, textAlign: 'center', color: '#a19d92' }}>
        Nessun dato disponibile
      </div>
    );

  const stats = data.statistiche || {};
  const veicoli = data.veicoli || [];
  const fmt = v => euroOppure(v);

  const categorie = [
    { key: 'totale_canoni', label: 'Canoni', icon: ClipboardList, color: COLORS.primary },
    { key: 'totale_pedaggio', label: 'Pedaggio', icon: Route, color: COLORS.info },
    { key: 'totale_verbali', label: 'Verbali', icon: Siren, color: COLORS.danger },
    { key: 'totale_bollo', label: 'Bollo', icon: Receipt, color: COLORS.warning },
    { key: 'totale_costi_extra', label: 'Costi Extra', icon: CreditCard, color: COLORS.warning },
    { key: 'totale_riparazioni', label: 'Riparazioni', icon: Wrench, color: '#7a776e' },
  ];

  return (
    <div>
      {/* Header */}
      <div
        style={{
          background: COLORS.success,
          borderRadius: 12,
          padding: 20,
          color: 'white',
          marginBottom: 20,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2 style={{ margin: '0 0 8px', fontSize: 20 }}><Wallet size={14} aria-hidden="true" style={ICO} /> Riepilogo Costi Noleggio {anno}</h2>
            <div style={{ fontSize: 32, fontWeight: 700 }}>{fmt(stats.totale_generale)}</div>
            <div style={{ fontSize: 13, opacity: 0.8, marginTop: 4 }}>
              {veicoli.length} veicoli • {veicoli.filter(v => (v.totale_canoni || 0) > 0).length}{' '}
              con fatture
            </div>
          </div>
          <a
            href={`/api/noleggio/export-pdf-costi?anno=${anno}`}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              padding: '12px 20px',
              background: 'rgba(255,255,255,0.2)',
              color: 'white',
              borderRadius: 8,
              textDecoration: 'none',
              fontWeight: 700,
              fontSize: 14,
              border: '1px solid rgba(255,255,255,0.3)',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <FileText size={14} aria-hidden="true" style={ICO} /> Esporta PDF
          </a>
        </div>
      </div>

      {/* Categorie cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
          gap: 12,
          marginBottom: 24,
        }}
      >
        {categorie.map(c => (
          <div
            key={c.key}
            style={{
              background: 'white',
              borderRadius: 10,
              padding: '14px 16px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
              borderLeft: `4px solid ${c.color}`,
            }}
          >
            <div
              style={{
                fontSize: 11,
                color: '#7a776e',
                fontWeight: 600,
                textTransform: 'uppercase',
              }}
            >
              <c.icon size={13} aria-hidden="true" style={ICO} /> {c.label}
            </div>
            <div style={{ fontSize: 20, fontWeight: 700, color: c.color, marginTop: 6 }}>
              {fmt(stats[c.key])}
            </div>
          </div>
        ))}
      </div>

      {/* Dettaglio per veicolo */}
      <div
        style={{
          background: 'white',
          borderRadius: 12,
          padding: 20,
          boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
        }}
      >
        <h3 style={{ margin: '0 0 16px', fontSize: 16, color: '#4c4a44' }}>
          <ChartColumn size={14} aria-hidden="true" style={ICO} /> Dettaglio per Veicolo
        </h3>
        {isMobile ? (
          <div style={{ display: 'grid', gap: 10 }}>
            {veicoli.slice(0, limite).map((v, i) => (
              <div key={v.targa || i} style={{ border: '1px solid #e6e3d9', borderRadius: 8, padding: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'baseline' }}>
                  <span style={{ fontWeight: 700, color: COLORS.primary }}>{v.targa}</span>
                  <span style={{ fontWeight: 700, color: '#4c4a44' }}>
                    {fmt(
                      (v.totale_canoni || 0) + (v.totale_verbali || 0) + (v.totale_bollo || 0)
                      + (v.totale_pedaggio || 0) + (v.totale_costi_extra || 0) + (v.totale_riparazioni || 0)
                    )}
                  </span>
                </div>
                <div style={{ fontSize: 13, color: '#7a776e', marginTop: 2 }}>
                  {v.marca} {(v.modello || '').substring(0, 25)} · {v.driver || '-'}
                </div>
                <div style={{ fontSize: 13, marginTop: 6, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
                  <span>Canoni: {fmt(v.totale_canoni)}</span>
                  <span>Verbali: {fmt(v.totale_verbali)}</span>
                  <span>Bollo: {fmt(v.totale_bollo)}</span>
                  <span>Altro: {fmt(totaleAltriCosti(v))}</span>
                </div>
              </div>
            ))}
            <div style={{ fontWeight: 700, color: '#4c4a44', padding: '8px 4px' }}>
              TOTALE {fmt(stats.totale_generale)}
            </div>
          </div>
        ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#f6f4ee', borderBottom: '2px solid #e6e3d9' }}>
                {[
                  'Targa',
                  'Veicolo',
                  'Driver',
                  'Canoni',
                  'Verbali',
                  'Bollo',
                  'Altro',
                  'TOTALE',
                ].map((h, i) => (
                  <th
                    key={i}
                    style={{
                      padding: '10px 12px',
                      textAlign: i >= 3 ? 'right' : 'left',
                      fontWeight: 700,
                      fontSize: 11,
                      color: '#7a776e',
                      textTransform: 'uppercase',
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {veicoli.slice(0, limite).map((v, i) => {
                const tot =
                  (v.totale_canoni || 0) +
                  (v.totale_verbali || 0) +
                  (v.totale_bollo || 0) +
                  (v.totale_pedaggio || 0) +
                  (v.totale_costi_extra || 0) +
                  (v.totale_riparazioni || 0);
                return (
                  <tr key={v.targa || i} style={{ borderBottom: '1px solid #f2f0e9' }}>
                    <td style={{ padding: '10px 12px', fontWeight: 700, color: '#5b7a6b' }}>
                      {v.targa}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      {v.marca} {(v.modello || '').substring(0, 25)}
                    </td>
                    <td style={{ padding: '10px 12px' }}>{v.driver || '-'}</td>
                    <td
                      style={{
                        padding: '10px 12px',
                        textAlign: 'right',
                        fontWeight: 600,
                        color: COLORS.success,
                      }}
                    >
                      {fmt(v.totale_canoni)}
                    </td>
                    <td
                      style={{
                        padding: '10px 12px',
                        textAlign: 'right',
                        color: (v.totale_verbali || 0) > 0 ? COLORS.danger : '#7a776e',
                      }}
                    >
                      {fmt(v.totale_verbali)}
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'right' }}>
                      {fmt(v.totale_bollo)}
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'right' }}>
                      {fmt(totaleAltriCosti(v))}
                    </td>
                    <td
                      style={{
                        padding: '10px 12px',
                        textAlign: 'right',
                        fontWeight: 700,
                        fontSize: 14,
                        color: '#4c4a44',
                      }}
                    >
                      {fmt(tot)}
                    </td>
                  </tr>
                );
              })}
              {/* Totale */}
              <tr style={{ borderTop: '2px solid #a94f30', background: '#eef3ef' }}>
                <td colSpan={3} style={{ padding: '12px', fontWeight: 700, color: '#4c4a44' }}>
                  TOTALE
                </td>
                <td
                  style={{ padding: '12px', textAlign: 'right', fontWeight: 700, color: COLORS.success }}
                >
                  {fmt(stats.totale_canoni)}
                </td>
                <td
                  style={{ padding: '12px', textAlign: 'right', fontWeight: 700, color: COLORS.danger }}
                >
                  {fmt(stats.totale_verbali)}
                </td>
                <td style={{ padding: '12px', textAlign: 'right', fontWeight: 700 }}>
                  {fmt(stats.totale_bollo)}
                </td>
                <td style={{ padding: '12px', textAlign: 'right', fontWeight: 700 }}>
                  {fmt(totaleAltriCosti(stats))}
                </td>
                <td
                  style={{
                    padding: '12px',
                    textAlign: 'right',
                    fontWeight: 700,
                    fontSize: 16,
                    color: '#4c4a44',
                  }}
                >
                  {fmt(stats.totale_generale)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        )}
        {veicoli.length > limite && (
          <button
            type="button"
            onClick={() => setLimite(x => x + 200)}
            style={{ minHeight: 44, padding: '8px 16px', marginTop: 12, borderRadius: 6, border: '1px solid #e6e3d9', background: '#fff', fontWeight: 600, cursor: 'pointer' }}
          >
            Mostra altre ({veicoli.length - limite})
          </button>
        )}
      </div>
    </div>
  );
}

export default function VeicoliHub() {
  const { anno } = useAnnoGlobale();
  const navigate = useNavigate();
  const location = useLocation();
  const [activeTab, setActiveTab] = useState(() => getTabFromPath(location.pathname));
  // Traccia i tab già visitati — non smontiamo mai un componente già caricato
  const [loadedTabs, setLoadedTabs] = useState(() => new Set([getTabFromPath(location.pathname)]));

  useEffect(() => {
    const t = getTabFromPath(location.pathname);
    if (t !== activeTab) {
      setActiveTab(t);
      setLoadedTabs(prev => new Set([...prev, t]));
    }
  }, [location.pathname]);

  const handleTabChange = tabId => {
    setActiveTab(tabId);
    setLoadedTabs(prev => new Set([...prev, tabId]));
    navigate(tabId === 'flotta' ? '/noleggio' : `/noleggio/${tabId}`);
  };

  return (
    <div style={{ width: '100%' }}>
      <PageHeader
        title="Noleggi"
        subtitle="Le auto a noleggio: contratti, costi, verbali e chi le guidava."
        style={{ marginBottom: 14 }}
      />
      {/* Tab Bar uniforme */}
      <div
        style={{
          display: 'flex',
          gap: 6,
          padding: '8px 16px',
          background: 'white',
          borderBottom: '1px solid #e6e3d9',
          borderRadius: '8px 8px 0 0',
          flexWrap: 'wrap',
        }}
      >
        {TABS.map(tab => (
          <button
            key={tab.id}
            data-testid={`tab-noleggio-${tab.id}`}
            onClick={() => handleTabChange(tab.id)}
            style={{
              padding: '7px 13px',
              borderRadius: 6,
              border: `1px solid ${activeTab === tab.id ? tab.color : '#e6e3d9'}`,
              fontWeight: activeTab === tab.id ? 700 : 500,
              fontSize: 12,
              cursor: 'pointer',
              transition: 'all 140ms ease',
              background: activeTab === tab.id ? tab.color : '#ffffff',
              color: activeTab === tab.id ? 'white' : '#7a776e',
              boxShadow: activeTab === tab.id ? '0 1px 2px rgba(20, 20, 19,0.08)' : 'none',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div style={{ padding: '16px 0 0 0' }}>
        <Suspense fallback={<PageLoader />}>
          {/* Flotta: carica solo se visitato, poi mantieni montato */}
          {loadedTabs.has('flotta') && (
            <div style={{ display: activeTab === 'flotta' ? 'block' : 'none' }}>
              <FlottaContent />
            </div>
          )}
          {/* Posizione auto/driver: partita doppia costi ↔ prove di pagamento */}
          {loadedTabs.has('posizione') && (
            <div style={{ display: activeTab === 'posizione' ? 'block' : 'none' }}>
              <PosizioneContent />
            </div>
          )}
          {/* Verbali: carica solo se visitato, poi mantieni montato */}
          {loadedTabs.has('verbali') && (
            <div style={{ display: activeTab === 'verbali' ? 'block' : 'none' }}>
              <VerbaliContent />
            </div>
          )}
          {/* Costi: stesso pattern display:none */}
          {loadedTabs.has('costi') && (
            <div style={{ display: activeTab === 'costi' ? 'block' : 'none' }}>
              <RiepilogoCosti anno={anno} />
            </div>
          )}
        </Suspense>
      </div>
    </div>
  );
}
