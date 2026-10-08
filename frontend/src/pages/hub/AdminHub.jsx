import React, { lazy, Suspense, useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { PageLoader } from '../../components/ds';
import PaginaNonTrovata from '../PaginaNonTrovata';

const AdminContent = lazy(() => import('../Admin.jsx'));
const ElaborazioniContent = lazy(() => import('./AdminElaborazioni.jsx'));
const MFAContent = lazy(() => import('../MFAAdmin.jsx'));

export default function AdminHub() {
  const location = useLocation();
  const path = location.pathname;

  const isElaborazioni = path === '/admin/elaborazioni';
  const isMfa = path === '/admin/mfa';
  const isAdmin = path === '/admin' || path === '/admin/';
  const isUnknown = !isElaborazioni && !isMfa && !isAdmin;

  const [visitedAdmin, setVisitedAdmin] = useState(isAdmin);
  const [visitedElaborazioni, setVisitedElaborazioni] = useState(isElaborazioni);
  const [visitedMfa, setVisitedMfa] = useState(isMfa);

  useEffect(() => {
    if (isElaborazioni) setVisitedElaborazioni(true);
    else if (isMfa) setVisitedMfa(true);
    else setVisitedAdmin(true);
  }, [isElaborazioni, isMfa]);

  // Le schede (Sistema, Utenti, MFA, Elaborazioni, ...) le disegna SchedeHub dalla mappa unica.

  return (
    <div style={{ width: '100%' }}>
      <div style={{ display: isAdmin ? 'block' : 'none' }}>
        <Suspense fallback={<PageLoader />}>{visitedAdmin && <AdminContent />}</Suspense>
      </div>
      <div style={{ display: isElaborazioni ? 'block' : 'none' }}>
        <Suspense fallback={<PageLoader />}>{visitedElaborazioni && <ElaborazioniContent />}</Suspense>
      </div>
      <div style={{ display: isMfa ? 'block' : 'none' }}>
        <Suspense fallback={<PageLoader />}>{visitedMfa && <MFAContent />}</Suspense>
      </div>
      {isUnknown && <PaginaNonTrovata />}
    </div>
  );
}
