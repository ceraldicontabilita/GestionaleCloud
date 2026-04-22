import { useEffect, useState } from 'react';
import ReactDOM from 'react-dom';

/**
 * Portal Component - Risolve l'errore "removeChild" renderizzando
 * i modali in un elemento root dedicato invece di document.body
 */
export default function Portal({ children }) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    return () => setMounted(false);
  }, []);

  if (!mounted) return null;

  // Usa portal-root se esiste, altrimenti document.body
  const portalRoot = document.getElementById('portal-root') || document.body;

  return ReactDOM.createPortal(children, portalRoot);
}
