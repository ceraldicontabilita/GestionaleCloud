import React, { useCallback, useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { LogIn, RotateCw } from 'lucide-react';
import { entraDalGestionale, loginGestionale } from '../lib/sessioneGruppo';

// Nessun tastierino: l'amministrazione del Menu si apre con la sessione del
// Gestionale. Senza sessione si passa dal login del Gestionale, che poi
// riporta qui (`/login?next=/menu/admin`).
export default function AdminLoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [stato, setStato] = useState('verifica');

  const prova = useCallback(async () => {
    setStato('verifica');
    const esito = await entraDalGestionale();
    if (esito === 'ok') {
      navigate(location.state?.da || '/admin', { replace: true });
      return;
    }
    setStato(esito);
  }, [navigate, location.state]);

  useEffect(() => { prova(); }, [prova]);

  const destinazione = `/menu${location.state?.da || '/admin'}`;
  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ background: '#faf7f0' }}>
      <div className="w-full max-w-sm rounded-xl p-6 text-center"
        style={{ background: '#fffefb', border: '1px solid #e6e0d4', color: '#2a3329' }}>
        <h1 className="text-xl font-bold mb-2">Gestione menu</h1>
        {stato === 'verifica' && <p role="status">Verifica dell'accesso in corso…</p>}
        {stato === 'nessuna_sessione' && (
          <>
            <p className="mb-4">Per gestire il menu entra prima nel Gestionale.</p>
            <a href={loginGestionale(destinazione)}
              className="inline-flex items-center justify-center gap-2 rounded-lg px-4 font-semibold text-white"
              style={{ background: '#5b7a6b', minHeight: 44 }}>
              <LogIn className="w-4 h-4" /> Entra dal Gestionale
            </a>
          </>
        )}
        {stato === 'non_disponibile' && (
          <>
            <p className="mb-4">Servizio temporaneamente non disponibile.</p>
            <button type="button" onClick={prova}
              className="inline-flex items-center justify-center gap-2 rounded-lg px-4 font-semibold text-white"
              style={{ background: '#5b7a6b', minHeight: 44 }}>
              <RotateCw className="w-4 h-4" /> Riprova
            </button>
          </>
        )}
      </div>
    </div>
  );
}
