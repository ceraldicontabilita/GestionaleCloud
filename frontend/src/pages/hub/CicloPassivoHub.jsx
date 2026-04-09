import { Navigate } from 'react-router-dom';

/**
 * CicloPassivoHub — redirect diretto alla pagina import fatture XML.
 * La funzionalità completa è in CicloPassivoAdmin.jsx (/ciclo-passivo/import).
 */
export default function CicloPassivoHub() {
  return <Navigate to="/ciclo-passivo/import" replace />;
}
