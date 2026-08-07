import React, { lazy, Suspense } from 'react';
import { PageLoader } from '../../components/ds';

const DashboardContent = lazy(() => import('../Dashboard.jsx'));
export default function DashboardHub() {
  return (
    <div style={{ width: '100%' }}>
      <Suspense fallback={<PageLoader />}>
        <DashboardContent />
      </Suspense>
    </div>
  );
}
