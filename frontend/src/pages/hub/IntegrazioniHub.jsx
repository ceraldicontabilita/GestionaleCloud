import React, { lazy, Suspense, useEffect, useState } from 'react';
import { Braces, Mail } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { HubTabs, PageLoader } from '../../components/ds';

const OpenAPIContent = lazy(() => import('../IntegrazioniOpenAPI.jsx'));
const MittentiEmailContent = lazy(() => import('../MittentiEmail.jsx'));

export default function IntegrazioniHub() {
  const navigate = useNavigate();
  const location = useLocation();
  const path = location.pathname;
  const isMittenti = path.includes('/mittenti-email');
  const activeTab = isMittenti ? 'mittenti-email' : 'openapi';
  const [visitedTabs, setVisitedTabs] = useState(() => new Set([activeTab]));

  useEffect(() => {
    if (path.includes('/pagopa')) {
      navigate('/riconciliazione/pagopa', { replace: true });
      return;
    }
    setVisitedTabs(prev => {
      const next = new Set(prev);
      next.add(activeTab);
      return next;
    });
  }, [activeTab, navigate, path]);

  const tabs = [
    { id: 'openapi', label: 'OpenAPI', Icon: Braces, to: '/integrazioni' },
    { id: 'mittenti-email', label: 'Mittenti Email', Icon: Mail, to: '/integrazioni/mittenti-email' },
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
        <Suspense fallback={<PageLoader />}>{visitedTabs.has('openapi') && <OpenAPIContent />}</Suspense>
      </div>
      <div style={{ display: activeTab === 'mittenti-email' ? 'block' : 'none' }}>
        <Suspense fallback={<PageLoader />}>{visitedTabs.has('mittenti-email') && <MittentiEmailContent />}</Suspense>
      </div>
    </div>
  );
}
