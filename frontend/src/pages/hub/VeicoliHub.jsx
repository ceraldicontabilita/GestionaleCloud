import React, { lazy, Suspense, useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';

const FlottaContent = lazy(() => import('../NoleggioAuto.jsx'));
const VerbaliContent = lazy(() => import('../VerbaliRiconciliazione.jsx'));

const TABS = [
  { id: 'flotta', label: '🚗 Flotta Auto', color: '#3b82f6' },
  { id: 'verbali', label: '📋 Verbali Noleggio', color: '#8b5cf6' },
  { id: 'costi', label: '💰 Riepilogo Costi', color: '#10b981' },
];

const Loading = () => (
  <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
    <div
      style={{
        width: 32,
        height: 32,
        border: '3px solid #e2e8f0',
        borderTop: '3px solid #3b82f6',
        borderRadius: '50%',
        animation: 'spin 1s linear infinite',
        margin: '0 auto 12px',
      }}
    />
    <style>{`@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}`}</style>
    Caricamento...
  </div>
);

const getTabFromPath = pathname => {
  if (pathname.includes('/verbali')) return 'verbali';
  if (pathname.includes('/costi')) return 'costi';
  if (pathname.includes('/noleggio/')) {
    const m = pathname.match(/\/noleggio\/([\w-]+)/);
    if (m && TABS.find(t => t.id === m[1])) return m[1];
  }
  return 'flotta';
};

function RiepilogoCosti({ anno }) {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    setLoading(true);
    import('../../api').then(({ default: api }) => {
      api
        .get(`/api/noleggio/veicoli?anno=${anno}`)
        .then(r => setData(r.data))
        .catch(() => setData(null))
        .finally(() => setLoading(false));
    });
  }, [anno]);

  if (loading) return <Loading />;
  if (!data)
    return (
      <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
        Nessun dato disponibile
      </div>
    );

  const stats = data.statistiche || {};
  const veicoli = data.veicoli || [];
  const fmt = v =>
    `€ ${(v || 0).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const categorie = [
    { key: 'totale_canoni', label: 'Canoni', icon: '📋', color: '#3b82f6' },
    { key: 'totale_pedaggio', label: 'Pedaggio', icon: '🛣️', color: '#8b5cf6' },
    { key: 'totale_verbali', label: 'Verbali', icon: '🚨', color: '#ef4444' },
    { key: 'totale_bollo', label: 'Bollo', icon: '📝', color: '#f59e0b' },
    { key: 'totale_costi_extra', label: 'Costi Extra', icon: '💳', color: '#ff9800' },
    { key: 'totale_riparazioni', label: 'Riparazioni', icon: '🔧', color: '#6b7280' },
  ];

  return (
    <div>
      {/* Header */}
      <div
        style={{
          background: '#15803d',
          borderRadius: 12,
          padding: 20,
          color: 'white',
          marginBottom: 20,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2 style={{ margin: '0 0 8px', fontSize: 20 }}>💰 Riepilogo Costi Noleggio {anno}</h2>
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
            📄 Esporta PDF
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
                color: '#6b7280',
                fontWeight: 600,
                textTransform: 'uppercase',
              }}
            >
              {c.icon} {c.label}
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
        <h3 style={{ margin: '0 0 16px', fontSize: 16, color: '#1e3a5f' }}>
          📊 Dettaglio per Veicolo
        </h3>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e2e8f0' }}>
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
                      color: '#64748b',
                      textTransform: 'uppercase',
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {veicoli.map((v, i) => {
                const tot =
                  (v.totale_canoni || 0) +
                  (v.totale_verbali || 0) +
                  (v.totale_bollo || 0) +
                  (v.totale_pedaggio || 0) +
                  (v.totale_costi_extra || 0) +
                  (v.totale_riparazioni || 0);
                return (
                  <tr key={v.targa || i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '10px 12px', fontWeight: 700, color: '#3b82f6' }}>
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
                        color: '#059669',
                      }}
                    >
                      {fmt(v.totale_canoni)}
                    </td>
                    <td
                      style={{
                        padding: '10px 12px',
                        textAlign: 'right',
                        color: (v.totale_verbali || 0) > 0 ? '#ef4444' : '#6b7280',
                      }}
                    >
                      {fmt(v.totale_verbali)}
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'right' }}>
                      {fmt(v.totale_bollo)}
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'right' }}>
                      {fmt(
                        (v.totale_pedaggio || 0) +
                          (v.totale_costi_extra || 0) +
                          (v.totale_riparazioni || 0)
                      )}
                    </td>
                    <td
                      style={{
                        padding: '10px 12px',
                        textAlign: 'right',
                        fontWeight: 700,
                        fontSize: 14,
                        color: '#1e3a5f',
                      }}
                    >
                      {fmt(tot)}
                    </td>
                  </tr>
                );
              })}
              {/* Totale */}
              <tr style={{ borderTop: '2px solid #1e3a5f', background: '#f0f4ff' }}>
                <td colSpan={3} style={{ padding: '12px', fontWeight: 700, color: '#1e3a5f' }}>
                  TOTALE
                </td>
                <td
                  style={{ padding: '12px', textAlign: 'right', fontWeight: 700, color: '#059669' }}
                >
                  {fmt(stats.totale_canoni)}
                </td>
                <td
                  style={{ padding: '12px', textAlign: 'right', fontWeight: 700, color: '#ef4444' }}
                >
                  {fmt(stats.totale_verbali)}
                </td>
                <td style={{ padding: '12px', textAlign: 'right', fontWeight: 700 }}>
                  {fmt(stats.totale_bollo)}
                </td>
                <td style={{ padding: '12px', textAlign: 'right', fontWeight: 700 }}>
                  {fmt((stats.totale_pedaggio || 0) + (stats.totale_costi_extra || 0))}
                </td>
                <td
                  style={{
                    padding: '12px',
                    textAlign: 'right',
                    fontWeight: 700,
                    fontSize: 16,
                    color: '#1e3a5f',
                  }}
                >
                  {fmt(stats.totale_generale)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
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
      {/* Tab Bar uniforme */}
      <div
        style={{
          display: 'flex',
          gap: 6,
          padding: '8px 16px',
          background: 'white',
          borderBottom: '1px solid #e2e8f0',
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
              border: `1px solid ${activeTab === tab.id ? tab.color : '#e2e8f0'}`,
              fontWeight: activeTab === tab.id ? 700 : 500,
              fontSize: 12,
              cursor: 'pointer',
              transition: 'all 140ms ease',
              background: activeTab === tab.id ? tab.color : '#ffffff',
              color: activeTab === tab.id ? 'white' : '#64748b',
              boxShadow: activeTab === tab.id ? '0 1px 2px rgba(15,39,68,0.08)' : 'none',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div style={{ padding: '16px 0 0 0' }}>
        <Suspense fallback={<Loading />}>
          {/* Flotta: carica solo se visitato, poi mantieni montato */}
          {loadedTabs.has('flotta') && (
            <div style={{ display: activeTab === 'flotta' ? 'block' : 'none' }}>
              <FlottaContent />
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
