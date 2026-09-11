import React, { lazy, Suspense, useState, useEffect } from 'react';
import { Settings, ShieldCheck, Workflow, Users, Bot } from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { HubTabs, PageLoader } from '../../components/ds';

const AdminContent = lazy(() => import('../Admin.jsx'));
const ElaborazioniContent = lazy(() => import('./AdminElaborazioni.jsx'));
const MFAContent = lazy(() => import('../MFAAdmin.jsx'));

export default function AdminHub() {
  const navigate = useNavigate();
  const location = useLocation();
  const path = location.pathname;

  const isElaborazioni = path.includes('/admin/elaborazioni')
    || path.includes('/admin/batch-reprocessing')
    || path.includes('/admin/batch-processor');
  const isMfa = path.includes('/admin/mfa');
  const isAdmin = !isElaborazioni && !isMfa;

  const [visitedAdmin, setVisitedAdmin] = useState(isAdmin);
  const [visitedElaborazioni, setVisitedElaborazioni] = useState(isElaborazioni);
  const [visitedMfa, setVisitedMfa] = useState(isMfa);

  useEffect(() => {
    if (isElaborazioni) setVisitedElaborazioni(true);
    else if (isMfa) setVisitedMfa(true);
    else setVisitedAdmin(true);
  }, [isElaborazioni, isMfa]);

  useEffect(() => {
    if (path.includes('/admin/batch-reprocessing') || path.includes('/admin/batch-processor')) {
      navigate('/admin/elaborazioni', { replace: true });
    }
  }, [path, navigate]);

  const tabs = [
    { id: 'admin', label: 'Sistema', Icon: Settings, to: '/admin' },
    { id: 'mfa', label: 'Sicurezza MFA', Icon: ShieldCheck, to: '/admin/mfa' },
    { id: 'elaborazioni', label: 'Elaborazioni', Icon: Workflow, to: '/admin/elaborazioni' },
  ];
  const activeTab = isElaborazioni ? 'elaborazioni' : isMfa ? 'mfa' : 'admin';

  return (
    <div style={{ width: '100%' }}>
      <HubTabs
        testIdPrefix="tab-admin"
        activeId={activeTab}
        onSelect={tab => navigate(tab.to)}
        tabs={tabs}
      />

      <div
        data-testid="admin-shortcuts"
        style={{
          display: 'flex',
          gap: 8,
          flexWrap: 'wrap',
          padding: '10px 16px',
          background: '#f8fafc',
          borderBottom: '1px solid #e2e8f0',
        }}
      >
        <Link
          to="/utenti"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '7px 10px', borderRadius: 8, background: '#fff', border: '1px solid #e2e8f0', color: '#334155', textDecoration: 'none', fontSize: 13, fontWeight: 600 }}
          data-testid="admin-shortcut-utenti"
        >
          <Users size={15} /> Utenti
        </Link>
        <Link
          to="/impostazioni-ai"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '7px 10px', borderRadius: 8, background: '#fff', border: '1px solid #e2e8f0', color: '#334155', textDecoration: 'none', fontSize: 13, fontWeight: 600 }}
          data-testid="admin-shortcut-ai"
        >
          <Bot size={15} /> Assistente AI
        </Link>
      </div>

      <div style={{ display: isAdmin ? 'block' : 'none' }}>
        <Suspense fallback={<PageLoader />}>{visitedAdmin && <AdminContent />}</Suspense>
      </div>
      <div style={{ display: isElaborazioni ? 'block' : 'none' }}>
        <Suspense fallback={<PageLoader />}>{visitedElaborazioni && <ElaborazioniContent />}</Suspense>
      </div>
      <div style={{ display: isMfa ? 'block' : 'none' }}>
        <Suspense fallback={<PageLoader />}>{visitedMfa && <MFAContent />}</Suspense>
      </div>
    </div>
  );
}
