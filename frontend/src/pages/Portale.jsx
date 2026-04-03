import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api';

// Estrae session_id dal fragment URL (es: #session_id=xxx)
function getSessionIdFromHash() {
  const hash = window.location.hash;
  if (!hash) return null;
  const m = hash.match(/session_id=([^&]+)/);
  return m ? m[1] : null;
}

export default function Portale() {
  const [step, setStep] = useState('loading'); // loading | login | portal | no_account
  const [user, setUser] = useState(null);
  const [dipendente, setDipendente] = useState(null);
  const [cedolini, setCedolini] = useState([]);
  const [contratti, setContratti] = useState([]);
  const [loadingDati, setLoadingDati] = useState(false);
  const [firmaId, setFirmaId] = useState(null);
  const [msg, setMsg] = useState('');
  const navigate = useNavigate();

  // Processa il session_id se presente nell'URL
  const processSession = useCallback(async (sessionId) => {
    try {
      const res = await api.post('/api/auth/google/session', { session_id: sessionId });
      const { user: u, token } = res.data;
      if (token) {
        localStorage.setItem('portal_token', token);
        localStorage.setItem('portal_user', JSON.stringify(u));
      }
      // Pulisci hash
      window.history.replaceState(null, '', window.location.pathname);
      return u;
    } catch {
      return null;
    }
  }, []);

  const loadPortalData = useCallback(async (email) => {
    setLoadingDati(true);
    try {
      const headers = {};
      const token = localStorage.getItem('portal_token');
      if (token) headers.Authorization = `Bearer ${token}`;

      const [cedRes, contRes] = await Promise.all([
        api.get('/api/portal/portale/cedolini', { headers }).catch(() => ({ data: [] })),
        api.get('/api/portal/portale/contratti', { headers }).catch(() => ({ data: [] })),
      ]);

      // Cerca dipendente per email (senza auth specifica)
      const dipRes = await api.get(`/api/dipendenti/by-google-email?email=${encodeURIComponent(email)}`).catch(() => ({ data: null }));
      setDipendente(dipRes.data);
      setCedolini(cedRes.data || []);
      setContratti(contRes.data || []);
    } catch {
      // silenzioso
    } finally {
      setLoadingDati(false);
    }
  }, []);

  // All'avvio: controlla se c'è sessione attiva o session_id nel hash
  useEffect(() => {
    const init = async () => {
      // 1. Check session_id nell'URL (ritorno da Google login)
      const sessionId = getSessionIdFromHash();
      if (sessionId) {
        const u = await processSession(sessionId);
        if (u) {
          setUser(u);
          setStep('portal');
          await loadPortalData(u.email);
          return;
        }
      }

      // 2. Check token salvato in localStorage
      const saved = localStorage.getItem('portal_user');
      const token = localStorage.getItem('portal_token');
      if (saved && token) {
        const u = JSON.parse(saved);
        setUser(u);
        setStep('portal');
        await loadPortalData(u.email);
        return;
      }

      setStep('login');
    };
    init();
  }, [processSession, loadPortalData]);

  const doGoogleLogin = () => {
    const redirectUrl = `${window.location.origin}/portale`;
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  const logout = () => {
    localStorage.removeItem('portal_token');
    localStorage.removeItem('portal_user');
    setUser(null);
    setStep('login');
  };

  const scaricaCedolino = async (cedolino) => {
    try {
      const token = localStorage.getItem('portal_token');
      const res = await api.get(`/api/portal/portale/cedolini/${cedolino.id}/pdf`, {
        headers: { Authorization: `Bearer ${token}` },
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `cedolino_${cedolino.mese_anno || cedolino.id}.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch {
      setMsg('Download cedolino non disponibile');
    }
  };

  const firmaContratto = async (docId) => {
    try {
      const token = localStorage.getItem('portal_token');
      const res = await api.post(`/api/portal/portale/firma/${docId}`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setFirmaId(res.data.firma_id);
      setContratti(prev => prev.map(c => c.id === docId ? { ...c, firmato: true } : c));
      setMsg('Documento firmato con successo!');
    } catch (e) {
      setMsg(e.response?.data?.detail || 'Errore durante la firma');
    }
  };

  const MESI = ['', 'Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic'];

  // ---- RENDER ----

  if (step === 'loading') {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f8fafc' }}>
        <div style={{ textAlign: 'center', color: '#94a3b8' }}>
          <Spinner />
          <p style={{ marginTop: 12 }}>Caricamento portale...</p>
        </div>
      </div>
    );
  }

  if (step === 'login') {
    return (
      <div style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #1e3a5f 0%, #0f2339 100%)',
        padding: 24,
      }}>
        <div style={{
          background: '#fff',
          borderRadius: 20,
          padding: '48px 40px',
          maxWidth: 440,
          width: '100%',
          textAlign: 'center',
          boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
        }}>
          <div style={{ marginBottom: 24 }}>
            <div style={{
              width: 60, height: 60,
              borderRadius: 16,
              background: '#1e3a5f',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              margin: '0 auto 16px',
            }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#7dd3fc" strokeWidth="2">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
            </div>
            <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, color: '#0f172a' }}>
              Portale Dipendenti
            </h1>
            <p style={{ margin: '8px 0 0', color: '#64748b', fontSize: 14 }}>
              Ceraldi Group S.r.l.
            </p>
          </div>

          <p style={{ color: '#475569', fontSize: 14, marginBottom: 28, lineHeight: 1.6 }}>
            Accedi con il tuo account Google aziendale per visualizzare
            cedolini, contratti e firmare documenti.
          </p>

          <button
            data-testid="btn-google-login-portale"
            onClick={doGoogleLogin}
            style={{
              width: '100%',
              padding: '14px 24px',
              background: '#fff',
              border: '1.5px solid #e2e8f0',
              borderRadius: 12,
              cursor: 'pointer',
              fontSize: 15,
              fontWeight: 600,
              color: '#1e293b',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 12,
              boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
              transition: 'all 0.15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.12)'; e.currentTarget.style.transform = 'translateY(-1px)'; }}
            onMouseLeave={e => { e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.06)'; e.currentTarget.style.transform = 'translateY(0)'; }}
          >
            <GoogleIcon />
            Accedi con Google
          </button>

          <p style={{ fontSize: 12, color: '#94a3b8', marginTop: 20 }}>
            Se non riesci ad accedere, contatta il responsabile HR per ricevere il codice di invito.
          </p>
        </div>
      </div>
    );
  }

  // PORTAL VIEW
  return (
    <div style={{ minHeight: '100vh', background: '#f8fafc' }}>
      {/* Header */}
      <div style={{ background: '#1e3a5f', color: '#fff', padding: '16px 32px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 36, height: 36, borderRadius: 10, background: 'rgba(255,255,255,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#7dd3fc" strokeWidth="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15 }}>Portale Dipendenti</div>
            <div style={{ fontSize: 12, opacity: 0.7 }}>Ceraldi Group S.r.l.</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {user?.picture && <img src={user.picture} alt="" style={{ width: 32, height: 32, borderRadius: '50%', border: '2px solid rgba(255,255,255,0.3)' }} />}
          <span style={{ fontSize: 13 }}>{user?.name || user?.email}</span>
          <button
            onClick={logout}
            style={{ background: 'rgba(255,255,255,0.15)', border: 'none', color: '#fff', padding: '6px 12px', borderRadius: 8, cursor: 'pointer', fontSize: 12 }}
          >
            Esci
          </button>
        </div>
      </div>

      {/* Content */}
      <div style={{ maxWidth: 900, margin: '0 auto', padding: '32px 24px' }}>
        {/* Benvenuto */}
        <div style={{
          background: 'linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%)',
          borderRadius: 16,
          padding: '24px 28px',
          color: '#fff',
          marginBottom: 28,
        }}>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 800 }}>
            Benvenuto{dipendente?.nome_completo ? `, ${dipendente.nome_completo}` : user?.name ? `, ${user.name}` : ''}!
          </h2>
          <p style={{ margin: '8px 0 0', opacity: 0.8, fontSize: 14 }}>
            {dipendente?.mansione ? `${dipendente.mansione} — ` : ''}
            Qui puoi consultare i tuoi documenti e firmare i contratti.
          </p>
          {dipendente?.data_inizio_contratto && (
            <p style={{ margin: '4px 0 0', opacity: 0.6, fontSize: 12 }}>
              In forza dal {dipendente.data_inizio_contratto}
            </p>
          )}
        </div>

        {msg && (
          <div style={{
            padding: '10px 16px', borderRadius: 8, marginBottom: 16, fontSize: 13,
            background: msg.includes('successo') ? '#f0fdf4' : '#fef2f2',
            border: `1px solid ${msg.includes('successo') ? '#bbf7d0' : '#fecaca'}`,
            color: msg.includes('successo') ? '#16a34a' : '#dc2626',
          }}>
            {msg}
          </div>
        )}

        {loadingDati ? (
          <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}><Spinner /> Caricamento documenti...</div>
        ) : (
          <>
            {/* ===== CEDOLINI ===== */}
            <Section title="Cedolini Paga" icon="payslip">
              {cedolini.length === 0 ? (
                <EmptyState label="Nessun cedolino disponibile" />
              ) : (
                <div style={{ display: 'grid', gap: 10 }}>
                  {cedolini.map(c => (
                    <div key={c.id || `${c.anno}-${c.mese}`} style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: '12px 16px', background: '#fff', borderRadius: 10,
                      border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
                    }}>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 14, color: '#0f172a' }}>
                          {MESI[c.mese] || c.mese} {c.anno}
                        </div>
                        <div style={{ fontSize: 12, color: '#64748b' }}>
                          {c.netto_pagato ? `Netto: €${Number(c.netto_pagato).toLocaleString('it-IT', { minimumFractionDigits: 2 })}` : 'Cedolino disponibile'}
                        </div>
                      </div>
                      <button
                        data-testid={`btn-scarica-cedolino-${c.id}`}
                        onClick={() => scaricaCedolino(c)}
                        style={{
                          background: '#1e3a5f', color: '#fff', border: 'none',
                          borderRadius: 8, padding: '7px 16px', fontSize: 12,
                          fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
                        }}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                        </svg>
                        Scarica PDF
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </Section>

            {/* ===== CONTRATTI ===== */}
            <Section title="Contratti e Documenti" icon="contract">
              {contratti.length === 0 ? (
                <EmptyState label="Nessun contratto disponibile" />
              ) : (
                <div style={{ display: 'grid', gap: 10 }}>
                  {contratti.map(c => (
                    <div key={c.id} style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: '12px 16px', borderRadius: 10,
                      border: `1px solid ${c.firmato ? '#bbf7d0' : '#e2e8f0'}`,
                      background: c.firmato ? '#f0fdf4' : '#fff',
                    }}>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 14, color: '#0f172a' }}>
                          {c.tipo || c.nome || 'Documento'}
                        </div>
                        <div style={{ fontSize: 12, color: '#64748b' }}>
                          {c.data_documento || c.data || ''}{c.firmato ? ' — Firmato' : ' — Da firmare'}
                        </div>
                      </div>
                      {c.firmato ? (
                        <span style={{ fontSize: 12, fontWeight: 700, color: '#16a34a', padding: '6px 12px', background: '#dcfce7', borderRadius: 8 }}>
                          Firmato
                        </span>
                      ) : (
                        <button
                          data-testid={`btn-firma-${c.id}`}
                          onClick={() => firmaContratto(c.id)}
                          style={{
                            background: '#059669', color: '#fff', border: 'none',
                            borderRadius: 8, padding: '7px 16px', fontSize: 12,
                            fontWeight: 600, cursor: 'pointer',
                          }}
                        >
                          Firma documento
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </Section>
          </>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 28 }}>
      <h3 style={{ margin: '0 0 14px', fontSize: 16, fontWeight: 700, color: '#0f172a' }}>{title}</h3>
      {children}
    </div>
  );
}

function EmptyState({ label }) {
  return (
    <div style={{ textAlign: 'center', padding: '32px 0', color: '#94a3b8', background: '#fff', borderRadius: 10, border: '1px solid #e2e8f0' }}>
      <p style={{ margin: 0, fontSize: 14 }}>{label}</p>
    </div>
  );
}

function Spinner() {
  return (
    <div style={{ width: 24, height: 24, border: '3px solid #e2e8f0', borderTop: '3px solid #1e3a5f', borderRadius: '50%', animation: 'spin 1s linear infinite', display: 'inline-block' }} />
  );
}

function GoogleIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
    </svg>
  );
}
