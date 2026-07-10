import React, { lazy, Suspense, useEffect, useState } from 'react';
import { Braces, Landmark } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { HubTabs } from '../../components/ds';

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
      <HubTabs
        testIdPrefix="tab-integrazioni"
        activeId={activeTab}
        onSelect={tab => navigate(tab.to)}
        tabs={tabs}
      />
      <div style={{ display: activeTab === 'openapi' ? 'block' : 'none' }}>
        <Suspense fallback={<Loading />}>{visitedTabs.has('openapi') && <OpenAPIContent />}</Suspense>
      </div>
      <div style={{ display: activeTab === 'pagopa' ? 'block' : 'none' }}>
        <Suspense fallback={<Loading />}>{visitedTabs.has('pagopa') && <PagoPAContent />}</Suspense>
      </div>
    </div>
  );
}
