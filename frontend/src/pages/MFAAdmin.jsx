import React, { useCallback, useEffect, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import api from '../api';
import { useAuth } from '../contexts/AuthContext';

const card = { background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: 22, maxWidth: 760, margin: '0 auto' };
const button = { border: 0, borderRadius: 8, background: '#0f2a4a', color: '#fff', padding: '11px 16px', fontWeight: 800, cursor: 'pointer' };
const input = { width: '100%', boxSizing: 'border-box', border: '1px solid #cbd5e1', borderRadius: 8, padding: '12px 14px', fontSize: 17, letterSpacing: 1, margin: '12px 0' };

export default function MFAAdmin() {
  const { applyMfaStepUp } = useAuth();
  const [status, setStatus] = useState(null);
  const [setup, setSetup] = useState(null);
  const [code, setCode] = useState('');
  const [recoveryCodes, setRecoveryCodes] = useState([]);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const response = await api.get('/api/auth/mfa/status');
    setStatus(response.data);
  }, []);

  useEffect(() => { load().catch(() => setMessage('Impossibile leggere lo stato MFA.')); }, [load]);

  const start = async () => {
    setBusy(true); setMessage('');
    try { setSetup((await api.post('/api/auth/mfa/setup/start')).data); }
    catch (error) { setMessage(error.response?.data?.detail || 'Avvio configurazione non riuscito.'); }
    finally { setBusy(false); }
  };

  const confirm = async () => {
    setBusy(true); setMessage('');
    try {
      const response = await api.post('/api/auth/mfa/setup/confirm', { code });
      setRecoveryCodes(response.data.recovery_codes || []);
      setSetup(null); setCode('');
      setMessage('MFA attivata. Salva i codici di recupero prima di lasciare la pagina.');
      await load();
    } catch (error) { setMessage(error.response?.data?.detail || 'Codice non valido.'); }
    finally { setBusy(false); }
  };

  const stepUp = async () => {
    setBusy(true); setMessage('');
    try {
      const response = await api.post('/api/auth/mfa/step-up', { code });
      applyMfaStepUp(response.data);
      setCode(''); setMessage('Sessione verificata con MFA.');
      await load();
    } catch (error) { setMessage(error.response?.data?.detail || 'Codice non valido.'); }
    finally { setBusy(false); }
  };

  const disable = async () => {
    if (!window.confirm('Disattivare MFA? Le approvazioni AI saranno bloccate finché non verrà riattivata.')) return;
    setBusy(true); setMessage('');
    try {
      await api.post('/api/auth/mfa/disable', { code });
      setCode(''); setRecoveryCodes([]); setMessage('MFA disattivata.');
      await load();
    } catch (error) { setMessage(error.response?.data?.detail || 'Codice non valido.'); }
    finally { setBusy(false); }
  };

  if (!status) return <div style={card}>Caricamento sicurezza...</div>;

  return (
    <div style={{ padding: 20 }}>
      <div style={card}>
        <h2 style={{ marginTop: 0 }}>Sicurezza e MFA</h2>
        <p style={{ color: '#475569', lineHeight: 1.55 }}>
          La verifica in due passaggi protegge l'accesso amministratore e rende obbligatoria una sessione MFA per approvare o rifiutare decisioni AI.
        </p>
        <div style={{ padding: 12, borderRadius: 8, background: status.enabled ? '#ecfdf5' : '#fff7ed', color: status.enabled ? '#166534' : '#9a3412', fontWeight: 800 }}>
          {status.enabled ? 'MFA attiva' : 'MFA non ancora configurata'}
          {status.enabled && ` · ${status.recovery_codes_remaining} codici di recupero disponibili`}
        </div>
        {message && <div style={{ marginTop: 14, padding: 10, background: '#f1f5f9', borderRadius: 8 }}>{message}</div>}

        {!status.enabled && !setup && <button style={{ ...button, marginTop: 18 }} disabled={busy} onClick={start}>Configura MFA</button>}

        {setup && (
          <div style={{ marginTop: 20 }}>
            <h3>1. Scansiona il codice</h3>
            <div style={{ background: '#fff', padding: 14, width: 'fit-content', border: '1px solid #e2e8f0' }}><QRCodeSVG value={setup.otpauth_uri} size={190} /></div>
            <p style={{ color: '#64748b', fontSize: 13 }}>Se non puoi scansionarlo, inserisci manualmente questa chiave. Non condividerla.</p>
            <code style={{ display: 'block', wordBreak: 'break-all', background: '#f8fafc', padding: 10 }}>{setup.secret}</code>
            <h3>2. Conferma il primo codice</h3>
            <input style={input} value={code} onChange={event => setCode(event.target.value)} inputMode="numeric" autoComplete="one-time-code" placeholder="000000" />
            <button style={button} disabled={busy || code.trim().length !== 6} onClick={confirm}>Attiva MFA</button>
          </div>
        )}

        {recoveryCodes.length > 0 && (
          <div style={{ marginTop: 20, padding: 16, border: '2px solid #f59e0b', borderRadius: 10 }}>
            <h3 style={{ marginTop: 0 }}>Codici di recupero — mostrati una sola volta</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 8 }}>
              {recoveryCodes.map(item => <code key={item} style={{ padding: 8, background: '#fffbeb' }}>{item}</code>)}
            </div>
          </div>
        )}

        {status.enabled && (
          <div style={{ marginTop: 20 }}>
            <h3>{status.verified_in_session ? 'Sessione MFA verificata' : 'Verifica questa sessione'}</h3>
            {!status.verified_in_session && <p style={{ color: '#64748b' }}>Inserisci un codice per abilitare le approvazioni AI senza uscire dal gestionale.</p>}
            <input style={input} value={code} onChange={event => setCode(event.target.value.toUpperCase())} autoComplete="one-time-code" placeholder="Codice MFA o recupero" />
            {!status.verified_in_session && <button style={button} disabled={busy || code.trim().length < 6} onClick={stepUp}>Verifica sessione</button>}
            <button style={{ ...button, background: '#b91c1c', marginLeft: status.verified_in_session ? 0 : 10 }} disabled={busy || code.trim().length < 6} onClick={disable}>Disattiva MFA</button>
          </div>
        )}
      </div>
    </div>
  );
}
