import React, { lazy, Suspense, useMemo, useState } from 'react';
import { Activity, Workflow } from 'lucide-react';
import { HubTabs, PageLoader } from '../../components/ds';

const BatchProcessor = lazy(() => import('../BatchProcessor.jsx'));
const BatchReprocessing = lazy(() => import('../BatchReprocessing.jsx'));

export default function AdminElaborazioni() {
  const [activeTab, setActiveTab] = useState('processor');
  const [visited, setVisited] = useState(() => new Set(['processor']));

  const tabs = useMemo(() => [
    { id: 'processor', label: 'Elaborazione automatica', Icon: Workflow },
    { id: 'reprocessing', label: 'Riprocessamento tecnico', Icon: Activity },
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
      <div style={{ display: activeTab === 'processor' ? 'block' : 'none' }}>
        <Suspense fallback={<PageLoader />}>
          {visited.has('processor') && <BatchProcessor />}
        </Suspense>
      </div>
      <div style={{ display: activeTab === 'reprocessing' ? 'block' : 'none' }}>
        <Suspense fallback={<PageLoader />}>
          {visited.has('reprocessing') && <BatchReprocessing />}
        </Suspense>
      </div>
    </div>
  );
}
