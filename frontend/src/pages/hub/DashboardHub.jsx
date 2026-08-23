import React, { lazy, Suspense } from 'react';
import { useLocation } from 'react-router-dom';
import { PageLoader } from '../../components/ds';
import Alerts from '../Alerts.jsx';

const DashboardContent = lazy(() => import('../Dashboard.jsx'));
export default function DashboardHub() {
  const location = useLocation();
  const isAlerts = location.pathname.includes('/dashboard/alerts');
  return (
    <div style={{ width: '100%' }}>
      <Suspense fallback={<PageLoader />}>
        {isAlerts ? <Alerts /> : <DashboardContent />}
      </Suspense>
    </div>
  );
}
