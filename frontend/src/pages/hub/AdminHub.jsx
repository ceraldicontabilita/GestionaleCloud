import React, { lazy, Suspense, useState, useEffect } from 'react';
import { Activity, Settings, Workflow } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';

const AdminContent = lazy(() => import('../Admin.jsx'));
const BatchContent = lazy(() => import('../BatchReprocessing.jsx'));
const BatchProcContent = lazy(() => import('../BatchProcessor.jsx'));

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

export default function AdminHub() {
  const navigate = useNavigate();
  const location = useLocation();
  const path = location.pathname;

  const isBatch = path.includes('/batch-reprocessing');
  const isBatchProc = path.includes('/batch-processor');
  const isAdmin = !isBatch && !isBatchProc;

  const [visitedAdmin, setVisitedAdmin] = useState(isAdmin);
  const [visitedBatch, setVisitedBatch] = useState(isBatch);
  const [visitedBatchProc, setVisitedBatchProc] = useState(isBatchProc);

  useEffect(() => {
    if (isBatch) setVisitedBatch(true);
    else if (isBatchProc) setVisitedBatchProc(true);
    else setVisitedAdmin(true);
  }, [isBatch, isBatchProc, isAdmin]);

  const tabs = [
    { id: 'admin', label: 'Sistema', Icon: Settings, to: '/admin' },
    { id: 'batch-reprocessing', label: 'Batch Reprocessing', Icon: Activity, to: '/batch-reprocessing' },
    { id: 'batch-processor', label: 'Batch Processor', Icon: Workflow, to: '/batch-processor' },
  ];
  const activeTab = isBatch ? 'batch-reprocessing' : isBatchProc ? 'batch-processor' : 'admin';

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
              data-testid={`tab-admin-${id}`}
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
