import { useEffect } from 'react';

/**
 * Il menu pubblico e' la replica del menu Qromo (public/carta/): pagina statica
 * che legge la carta da `/api/menu/carta`. Il QR dei clienti punta a `/menu/`,
 * che qui rimanda a quella pagina.
 */
export default function CartaPubblica() {
  useEffect(() => {
    const base = process.env.PUBLIC_URL || '';
    window.location.replace(`${base}/carta/index.html${window.location.search}`);
  }, []);
  return null;
}
