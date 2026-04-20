import React, { lazy, Suspense, useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';

const AdminContent = lazy(() => import('../Admin.jsx'));
const BatchContent = lazy(() => import('../BatchReprocessing.jsx'));
const BatchProcContent = lazy(() => import('../BatchProcessor.jsx'));

const Loading = () => (
  <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
    <div style={{
      width: 32, height: 32,
      border: '3px solid #e2e8f0',
      borderTop: '3px solid #2563eb',
      borderRadius: '50%',
      animation: 'spin 1s linear infinite',
      margin: '0 auto 12px'
    }} />
    Caricamento...
  </div>
);

export default function AdminHub() {
  const location = useLocation();
  const path = location.pathname;

  const isBatch    = path.includes('/batch-reprocessing');
  const isBatchProc = path.includes('/batch-processor');
  const isAdmin    = !isBatch && !isBatchProc;

  const [visitedAdmin,     setVisitedAdmin]     = useState(isAdmin);
  const [visitedBatch,     setVisitedBatch]     = useState(isBatch);
  const [visitedBatchProc, setVisitedBatchProc] = useState(isBatchProc);

  useEffect(() => {
    if (isBatch)     setVisitedBatch(true);
    else if (isBatchProc) setVisitedBatchProc(true);
    else             setVisitedAdmin(true);
  }, [isBatch, isBatchProc, isAdmin]);

  return (
    <div style={{ width: '100%' }}>
      <div style={{ display: isAdmin ? 'block' : 'none' }}>
        <Suspense fallback={<Loading />}>{visitedAdmin && <AdminContent />}</Suspense>
      </div>
      <div style={{ display: isBatch ? 'block' : 'none' }}>
        <Suspense fallback={<Loading />}>{visitedBatch && <BatchContent />}</Suspense>
      </div>
      <div style={{ display: isBatchProc ? 'block' : 'none' }}>
        <Suspense fallback={<Loading />}>{visitedBatchProc && <BatchProcContent />}</Suspense>
      </div>
    </div>
  );
}
