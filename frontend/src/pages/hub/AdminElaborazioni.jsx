import React, { lazy, Suspense, useMemo, useState } from 'react';
import { Activity, Workflow } from 'lucide-react';
import { HubTabs, PageLoader } from '../../components/ds';

const ElaborazioneAutomatica = lazy(() => import('../BatchProcessor.jsx'));
const RielaborazioneDocumenti = lazy(() => import('../BatchReprocessing.jsx'));

export default function AdminElaborazioni() {
  const [activeTab, setActiveTab] = useState('automatica');
  const [visited, setVisited] = useState(() => new Set(['automatica']));

  const tabs = useMemo(() => [
    { id: 'automatica', label: 'Elaborazione automatica', Icon: Workflow },
    { id: 'rielaborazione', label: 'Rielaborazione documenti', Icon: Activity },
  ], []);

  const handleSelect = tab => {
    setActiveTab(tab.id);
    setVisited(prev => new Set([...prev, tab.id]));
  };

  return (
    <div style={{ width: '100%' }}>
      <HubTabs
        testIdPrefix="tab-admin-elaborazioni"
        activeId={activeTab}
        onSelect={handleSelect}
        tabs={tabs}
      />
      <div style={{ display: activeTab === 'automatica' ? 'block' : 'none' }}>
        <Suspense fallback={<PageLoader />}>
          {visited.has('automatica') && <ElaborazioneAutomatica />}
        </Suspense>
      </div>
      <div style={{ display: activeTab === 'rielaborazione' ? 'block' : 'none' }}>
        <Suspense fallback={<PageLoader />}>
          {visited.has('rielaborazione') && <RielaborazioneDocumenti />}
        </Suspense>
      </div>
    </div>
  );
}
