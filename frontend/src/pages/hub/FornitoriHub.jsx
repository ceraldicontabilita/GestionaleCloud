import React, { lazy, Suspense } from 'react';
import { PageLoader } from '../../components/ds';

const FornitoriContent = lazy(() => import('../Fornitori.jsx'));


export default function FornitoriHub() {
  return (
    <Suspense fallback={<PageLoader />}>
      <FornitoriContent />
    </Suspense>
  );
}
