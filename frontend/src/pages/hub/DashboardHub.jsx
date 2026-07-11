import React, { lazy, Suspense, useEffect, useState } from 'react';
import { LayoutDashboard, Network } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { HubTabs, PageLoader } from '../../components/ds';

const DashboardContent = lazy(() => import('../Dashboard.jsx'));
const DashboardRelazionaleContent = lazy(() => import('../DashboardRelazionale.jsx'));


export default function DashboardHub() {
  const navigate = useNavigate();
  const location = useLocation();
  const isRelazionale = location.pathname.includes('/dashboard-relazionale');
  const activeTab = isRelazionale ? 'relazionale' : 'dashboard';
  const [visitedTabs, setVisitedTabs] = useState(() => new Set([activeTab]));

  useEffect(() => {
    setVisitedTabs(prev => {
      const next = new Set(prev);
      next.add(activeTab);
      return next;
    });
  }, [activeTab]);

  const tabs = [
    { id: 'dashboard', label: 'Dashboard', Icon: LayoutDashboard, to: '/' },
    { id: 'relazionale', label: 'Dashboard relazionale', Icon: Network, to: '/dashboard-relazionale' },
  ];

  return (
    <div style={{ width: '100%' }}>
      <HubTabs
        testIdPrefix="tab-dashboard"
        activeId={activeTab}
        onSelect={tab => navigate(tab.to)}
        tabs={tabs}
      />
      <div style={{ display: activeTab === 'dashboard' ? 'block' : 'none' }}>
        <Suspense fallback={<PageLoader />}>
          {visitedTabs.has('dashboard') && <DashboardContent />}
        </Suspense>
      </div>
      <div style={{ display: activeTab === 'relazionale' ? 'block' : 'none' }}>
        <Suspense fallback={<PageLoader />}>
          {visitedTabs.has('relazionale') && <DashboardRelazionaleContent />}
        </Suspense>
      </div>
    </div>
  );
}
