import React, { lazy, Suspense, useState, useEffect } from 'react';
import { Activity, Settings, ShieldCheck, Workflow } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { HubTabs, PageLoader } from '../../components/ds';

const AdminContent = lazy(() => import('../Admin.jsx'));
const BatchContent = lazy(() => import('../BatchReprocessing.jsx'));
const BatchProcContent = lazy(() => import('../BatchProcessor.jsx'));
const MFAContent = lazy(() => import('../MFAAdmin.jsx'));


export default function AdminHub() {
  const navigate = useNavigate();
  const location = useLocation();
  const path = location.pathname;

  const isBatch = path.includes('/batch-reprocessing');
  const isBatchProc = path.includes('/batch-processor');
  const isMfa = path.includes('/admin/mfa');
  const isAdmin = !isBatch && !isBatchProc && !isMfa;

  const [visitedAdmin, setVisitedAdmin] = useState(isAdmin);
  const [visitedBatch, setVisitedBatch] = useState(isBatch);
  const [visitedBatchProc, setVisitedBatchProc] = useState(isBatchProc);
  const [visitedMfa, setVisitedMfa] = useState(isMfa);

  useEffect(() => {
    if (isBatch) setVisitedBatch(true);
    else if (isBatchProc) setVisitedBatchProc(true);
    else if (isMfa) setVisitedMfa(true);
    else setVisitedAdmin(true);
  }, [isBatch, isBatchProc, isMfa, isAdmin]);

  const tabs = [
    { id: 'admin', label: 'Sistema', Icon: Settings, to: '/admin' },
    { id: 'mfa', label: 'Sicurezza MFA', Icon: ShieldCheck, to: '/admin/mfa' },
    { id: 'batch-reprocessing', label: 'Batch Reprocessing', Icon: Activity, to: '/batch-reprocessing' },
    { id: 'batch-processor', label: 'Batch Processor', Icon: Workflow, to: '/batch-processor' },
  ];
  const activeTab = isBatch ? 'batch-reprocessing' : isBatchProc ? 'batch-processor' : isMfa ? 'mfa' : 'admin';

  return (
    <div style={{ width: '100%' }}>
      <HubTabs
        testIdPrefix="tab-admin"
        activeId={activeTab}
        onSelect={tab => navigate(tab.to)}
        tabs={tabs}
      />
      <div style={{ display: isAdmin ? 'block' : 'none' }}>
        <Suspense fallback={<PageLoader />}>{visitedAdmin && <AdminContent />}</Suspense>
      </div>
      <div style={{ display: isBatch ? 'block' : 'none' }}>
        <Suspense fallback={<PageLoader />}>{visitedBatch && <BatchContent />}</Suspense>
      </div>
      <div style={{ display: isBatchProc ? 'block' : 'none' }}>
        <Suspense fallback={<PageLoader />}>{visitedBatchProc && <BatchProcContent />}</Suspense>
      </div>
      <div style={{ display: isMfa ? 'block' : 'none' }}>
        <Suspense fallback={<PageLoader />}>{visitedMfa && <MFAContent />}</Suspense>
      </div>
    </div>
  );
}
