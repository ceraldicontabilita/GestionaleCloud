import React, { lazy, Suspense, useEffect, useState } from 'react';
import { Braces, Landmark } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';

const OpenAPIContent = lazy(() => import('../IntegrazioniOpenAPI.jsx'));
const PagoPAContent = lazy(() => import('../GestionePagoPA.jsx'));

const Loading = () => (
  <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
    <div
      style={{
        width: 32,
        height: 32,
        border: '3px solid #e2e8f0',
        borderTop: '3px solid #2563eb',
        borderRadius: '50%',
        animation: 'spin 1s linear infinite',
        margin: '0 auto 12px',
      }}
    />
    Caricamento...
  </div>
);

export default function IntegrazioniHub() {
  const navigate = useNavigate();
  const location = useLocation();
  const path = location.pathname;
  const isPagoPA = path.includes('/pagopa');
  const activeTab = isPagoPA ? 'pagopa' : 'openapi';
  const [visitedTabs, setVisitedTabs] = useState(() => new Set([activeTab]));

  useEffect(() => {
    setVisitedTabs(prev => {
      const next = new Set(prev);
      next.add(activeTab);
      return next;
    });
  }, [activeTab]);

  const tabs = [
    { id: 'openapi', label: 'OpenAPI', Icon: Braces, to: '/integrazioni' },
    { id: 'pagopa', label: 'PagoPA', Icon: Landmark, to: '/integrazioni/pagopa' },
  ];

  return (
    <div style={{ width: '100%' }}>
      <div
        style={{
          display: 'flex',
          gap: 8,
          padding: '8px 12px',
          background: 'white',
          borderBottom: '1px solid #e2e8f0',
          borderRadius: '8px 8px 0 0',
          flexWrap: 'wrap',
          marginBottom: 16,
        }}
      >
        {tabs.map(({ id, label, Icon, to }) => {
          const isActive = activeTab === id;
          return (
            <button
              key={id}
              onClick={() => navigate(to)}
              data-testid={`tab-integrazioni-${id}`}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: '9px 13px',
                minHeight: 40,
                borderRadius: 6,
                border: `1px solid ${isActive ? '#0f2744' : '#e2e8f0'}`,
                background: isActive ? '#0f2744' : '#fff',
                color: isActive ? '#fff' : '#64748b',
                fontWeight: isActive ? 700 : 500,
                fontSize: 12,
                cursor: 'pointer',
              }}
            >
              <Icon size={14} />
              <span>{label}</span>
            </button>
          );
        })}
      </div>
      <div style={{ display: activeTab === 'openapi' ? 'block' : 'none' }}>
        <Suspense fallback={<Loading />}>{visitedTabs.has('openapi') && <OpenAPIContent />}</Suspense>
      </div>
      <div style={{ display: activeTab === 'pagopa' ? 'block' : 'none' }}>
        <Suspense fallback={<Loading />}>{visitedTabs.has('pagopa') && <PagoPAContent />}</Suspense>
      </div>
    </div>
  );
}
