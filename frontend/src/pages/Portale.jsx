import React, { useState, useEffect, useCallback, useRef } from 'react';
import api from '../api';

/* ─── Utility: estrae session_id dall'URL hash ─── */
function getSessionIdFromHash() {
  const hash = window.location.hash;
  if (!hash) return null;
  const m = hash.match(/session_id=([^&]+)/);
  return m ? m[1] : null;
}

/* ─── Canvas Pad Firma (touch + mouse) ─── */
function SignaturePad({ onReady, onClear }) {
  const canvasRef = useRef(null);
  const drawing = useRef(false);
  const [isEmpty, setIsEmpty] = useState(true);

  const getPos = (canvas, e) => {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    if (e.touches) {
      return {
        x: (e.touches[0].clientX - rect.left) * scaleX,
        y: (e.touches[0].clientY - rect.top) * scaleY,
      };
    }
    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top) * scaleY,
    };
  };

  const startDraw = useCallback((e) => {
    e.preventDefault();
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    drawing.current = true;
    const pos = getPos(canvas, e);
    ctx.beginPath();
    ctx.moveTo(pos.x, pos.y);
  }, []);

  const draw = useCallback((e) => {
    e.preventDefault();
    if (!drawing.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const pos = getPos(canvas, e);
    ctx.lineTo(pos.x, pos.y);
    ctx.strokeStyle = '#1e3a5f';
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.stroke();
    setIsEmpty(false);
  }, []);

  const endDraw = useCallback((e) => {
    e.preventDefault();
    drawing.current = false;
    const canvas = canvasRef.current;
    if (onReady) onReady(canvas.toDataURL('image/png'));
  }, [onReady]);

  const clearPad = () => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    setIsEmpty(true);
    if (onClear) onClear();
  };

  useEffect(() => {
    const canvas = canvasRef.current;
    // Set physical size 2x for retina
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = 160 * dpr;
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
  }, []);

  return (
    <div>
      <div style={{
        border: '2px dashed #cbd5e1',
        borderRadius: 12,
        background: '#f8fafc',
        overflow: 'hidden',
        cursor: 'crosshair',
        touchAction: 'none',
        userSelect: 'none',
      }}>
        <canvas
          ref={canvasRef}
          style={{ width: '100%', height: 160, display: 'block', touchAction: 'none' }}
          onMouseDown={startDraw}
          onMouseMove={draw}
          onMouseUp={endDraw}
          onMouseLeave={endDraw}
          onTouchStart={startDraw}
          onTouchMove={draw}
          onTouchEnd={endDraw}
        />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
        <span style={{ fontSize: 12, color: '#64748b' }}>
          {isEmpty ? 'Disegna la tua firma qui sopra' : 'Firma acquisita'}
        </span>
        <button
          type="button"
          onClick={clearPad}
          style={{
            background: 'none', border: '1px solid #e2e8f0', borderRadius: 6,
            padding: '4px 12px', fontSize: 12, color: '#64748b', cursor: 'pointer'
          }}
        >
          Cancella
        </button>
      </div>
    </div>
  );
}

/* ─── Modal Firma Documento ─── */
function FirmaModal({ contratto, onClose, onFirmato, token }) {
  const [step, setStep] = useState('lettura'); // lettura | firma
  const [scrollOk, setScrollOk] = useState(false);
  const [timer, setTimer] = useState(0);
  const [nomeDigitato, setNomeDigitato] = useState('');
  const [checkLetto, setCheckLetto] = useState(false);
  const [checkAccetta, setCheckAccetta] = useState(false);
  const [firmaB64, setFirmaB64] = useState('');
  const [loading, setLoading] = useState(false);
  const [errore, setErrore] = useState('');
  const [firmataOk, setFirmataOk] = useState(null);
  const scrollRef = useRef(null);
  const timerRef = useRef(null);
  const startTime = useRef(Date.now());

  // Timer lettura
  useEffect(() => {
    timerRef.current = setInterval(() => {
      setTimer(Math.floor((Date.now() - startTime.current) / 1000));
    }, 1000);
    return () => clearInterval(timerRef.current);
  }, []);

  // Scroll tracking
  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 20) {
      setScrollOk(true);
    }
  };

  const canFirmare = scrollOk && checkLetto && checkAccetta && nomeDigitato.trim().length > 3 && firmaB64.length > 100;

  const invia = async () => {
    setLoading(true);
    setErrore('');
    try {
      const res = await api.post(`/api/portal/portale/firma/${contratto.id}`, {
        nome_digitato: nomeDigitato.trim(),
        checkbox_lettura: checkLetto,
        checkbox_accettazione: checkAccetta,
        scroll_completato: scrollOk,
        tempo_lettura_secondi: timer,
        firma_canvas_base64: firmaB64,
      }, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setFirmataOk(res.data);
    } catch (e) {
      setErrore(e.response?.data?.detail || 'Errore durante la firma. Riprova.');
    } finally {
      setLoading(false);
    }
  };

  // Mostra conferma firma
  if (firmataOk) {
    return (
      <Overlay onClose={() => { onFirmato(contratto.id); onClose(); }}>
        <div style={{ textAlign: 'center', padding: '16px 0' }}>
          <div style={{
            width: 64, height: 64, borderRadius: '50%', background: '#dcfce7',
            display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px'
          }}>
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#16a34a" strokeWidth="2.5">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </div>
          <h3 style={{ margin: '0 0 8px', fontSize: 20, fontWeight: 800, color: '#0f172a' }}>
            Documento firmato!
          </h3>
          <p style={{ color: '#64748b', fontSize: 14, margin: '0 0 8px' }}>
            La tua firma è stata registrata con successo.
          </p>
          <div style={{
            background: '#f8fafc', borderRadius: 10, padding: '12px 16px',
            fontSize: 12, color: '#64748b', textAlign: 'left', marginBottom: 20
          }}>
            <div><strong>Hash firma:</strong> {firmataOk.hash_firma?.substring(0, 24)}...</div>
            <div><strong>Data:</strong> {firmataOk.certificato?.data_firma} alle {firmataOk.certificato?.ora_firma}</div>
          </div>
          <button
            data-testid="btn-chiudi-conferma-firma"
            onClick={() => { onFirmato(contratto.id); onClose(); }}
            style={{
              background: '#1e3a5f', color: '#fff', border: 'none',
              borderRadius: 10, padding: '12px 32px', fontSize: 15, fontWeight: 700, cursor: 'pointer'
            }}
          >
            Chiudi
          </button>
        </div>
      </Overlay>
    );
  }

  return (
    <Overlay onClose={onClose}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 18, fontWeight: 800, color: '#0f172a' }}>
            Firma Documento
          </h3>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: '#64748b' }}>
            {contratto.tipo || contratto.nome || 'Contratto'} — {contratto.data_documento || ''}
          </p>
        </div>
        <div style={{
          background: timer >= 30 ? '#dcfce7' : '#fef3c7',
          color: timer >= 30 ? '#16a34a' : '#d97706',
          padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 700
        }}>
          {Math.floor(timer / 60).toString().padStart(2,'0')}:{(timer % 60).toString().padStart(2,'0')}
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
        {['lettura','firma'].map(s => (
          <button
            key={s}
            onClick={() => s === 'firma' && scrollOk ? setStep('firma') : null}
            style={{
              flex: 1, padding: '8px 0', borderRadius: 8, border: 'none', cursor: s === 'firma' && !scrollOk ? 'not-allowed' : 'pointer',
              fontWeight: 700, fontSize: 13,
              background: step === s ? '#1e3a5f' : '#f1f5f9',
              color: step === s ? '#fff' : '#64748b',
              opacity: s === 'firma' && !scrollOk ? 0.5 : 1,
            }}
          >
            {s === 'lettura' ? '1. Leggi' : '2. Firma'}
          </button>
        ))}
      </div>

      {step === 'lettura' && (
        <>
          <p style={{ fontSize: 12, color: '#64748b', margin: '0 0 8px' }}>
            Leggi l'intero documento fino in fondo per procedere.
          </p>
          {/* Documento scrollabile */}
          <div
            ref={scrollRef}
            onScroll={handleScroll}
            style={{
              height: 260, overflowY: 'auto', border: '1px solid #e2e8f0',
              borderRadius: 10, padding: '16px 20px', background: '#fff',
              fontSize: 13, lineHeight: 1.7, color: '#374151', marginBottom: 12
            }}
          >
            <h4 style={{ margin: '0 0 12px', fontSize: 15, fontWeight: 700 }}>
              {contratto.tipo || 'Contratto di Lavoro'}
            </h4>
            <p style={{ margin: '0 0 10px' }}>
              Tra <strong>Ceraldi Group S.r.l.</strong> (di seguito "Datore di lavoro") e il/la dipendente
              identificato/a tramite account Google associato a questo portale (di seguito "Dipendente").
            </p>
            {contratto.contenuto ? (
              <div style={{ whiteSpace: 'pre-wrap' }}>{contratto.contenuto}</div>
            ) : (
              <>
                <p style={{ margin: '0 0 10px' }}>
                  Il presente documento disciplina il rapporto di lavoro subordinato tra le parti, in conformità
                  alla normativa vigente (D.Lgs. 81/2008, CCNL di categoria applicabile).
                </p>
                <p style={{ margin: '0 0 10px' }}>
                  <strong>Art. 1 – Decorrenza e durata.</strong> Il rapporto di lavoro decorre dalla data indicata nel
                  documento e si intende, salvo diversa indicazione, a tempo indeterminato.
                </p>
                <p style={{ margin: '0 0 10px' }}>
                  <strong>Art. 2 – Mansioni.</strong> Il dipendente è assunto con le mansioni indicate nell'allegato,
                  con obbligo di osservare le disposizioni impartite dal datore di lavoro.
                </p>
                <p style={{ margin: '0 0 10px' }}>
                  <strong>Art. 3 – Retribuzione.</strong> La retribuzione mensile lorda è quella indicata nel sistema
                  gestionale e nei cedolini paga allegati.
                </p>
                <p style={{ margin: '0 0 10px' }}>
                  <strong>Art. 4 – Orario di lavoro.</strong> L'orario di lavoro è quello previsto dal CCNL applicato,
                  salvo diverse disposizioni concordate per iscritto.
                </p>
                <p style={{ margin: '0 0 10px' }}>
                  <strong>Art. 5 – Obblighi del dipendente.</strong> Il dipendente si impegna a svolgere le proprie
                  mansioni con diligenza, a rispettare il segreto professionale e a non divulgare informazioni
                  riservate dell'azienda a terzi.
                </p>
                <p style={{ margin: '0 0 10px' }}>
                  <strong>Art. 6 – Privacy.</strong> Il trattamento dei dati personali avviene in conformità al
                  Regolamento EU 2016/679 (GDPR). Il dipendente ha il diritto di accedere, rettificare e
                  cancellare i propri dati nei termini di legge.
                </p>
                <p style={{ margin: 0 }}>
                  <strong>Art. 7 – Firma Elettronica.</strong> La firma digitale apposta in questa sede
                  costituisce firma elettronica semplice (FES) ai sensi dell'art. 3 del Regolamento eIDAS
                  (UE 910/2014), con valore legale equivalente a firma autografa per i documenti
                  contemplati dall'art. 21 del D.Lgs. 82/2005 (CAD).
                </p>
              </>
            )}
          </div>

          {scrollOk ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', background: '#f0fdf4', borderRadius: 8, marginBottom: 12 }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#16a34a" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
              <span style={{ fontSize: 13, color: '#16a34a', fontWeight: 600 }}>Documento letto completamente</span>
            </div>
          ) : (
            <p style={{ fontSize: 12, color: '#f59e0b', margin: '0 0 12px', fontWeight: 600 }}>
              Scorri fino in fondo per continuare
            </p>
          )}

          <button
            data-testid="btn-vai-a-firma"
            disabled={!scrollOk}
            onClick={() => setStep('firma')}
            style={{
              width: '100%', padding: '12px', borderRadius: 10, border: 'none',
              background: scrollOk ? '#1e3a5f' : '#e2e8f0',
              color: scrollOk ? '#fff' : '#94a3b8',
              fontWeight: 700, fontSize: 15, cursor: scrollOk ? 'pointer' : 'not-allowed',
            }}
          >
            Procedi alla Firma
          </button>
        </>
      )}

      {step === 'firma' && (
        <>
          {/* Nome digitato */}
          <div style={{ marginBottom: 16 }}>
            <label style={{ fontSize: 13, fontWeight: 700, color: '#374151', display: 'block', marginBottom: 6 }}>
              Nome e Cognome completo *
            </label>
            <input
              data-testid="input-nome-firma"
              type="text"
              placeholder="Es: Mario Rossi"
              value={nomeDigitato}
              onChange={e => setNomeDigitato(e.target.value)}
              style={{
                width: '100%', padding: '10px 12px', border: '2px solid #e2e8f0',
                borderRadius: 8, fontSize: 14, boxSizing: 'border-box',
                borderColor: nomeDigitato.length > 3 ? '#16a34a' : '#e2e8f0',
              }}
            />
            <p style={{ fontSize: 11, color: '#94a3b8', margin: '4px 0 0' }}>
              Digita esattamente il tuo nome come registrato nel sistema
            </p>
          </div>

          {/* Canvas firma */}
          <div style={{ marginBottom: 16 }}>
            <label style={{ fontSize: 13, fontWeight: 700, color: '#374151', display: 'block', marginBottom: 6 }}>
              Firma autografa (disegna qui) *
            </label>
            <SignaturePad
              onReady={b64 => setFirmaB64(b64)}
              onClear={() => setFirmaB64('')}
            />
          </div>

          {/* Checkboxes */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 16 }}>
            <label data-testid="check-letto" style={{ display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={checkLetto}
                onChange={e => setCheckLetto(e.target.checked)}
                style={{ marginTop: 2, width: 16, height: 16, cursor: 'pointer', accentColor: '#1e3a5f' }}
              />
              <span style={{ fontSize: 13, color: '#374151', lineHeight: 1.5 }}>
                Dichiaro di aver letto e compreso integralmente il documento
              </span>
            </label>
            <label data-testid="check-accetta" style={{ display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={checkAccetta}
                onChange={e => setCheckAccetta(e.target.checked)}
                style={{ marginTop: 2, width: 16, height: 16, cursor: 'pointer', accentColor: '#1e3a5f' }}
              />
              <span style={{ fontSize: 13, color: '#374151', lineHeight: 1.5 }}>
                Accetto le condizioni e le clausole del documento sopra riportato
              </span>
            </label>
          </div>

          {/* Info legale */}
          <div style={{
            background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 8,
            padding: '8px 12px', fontSize: 11, color: '#0369a1', marginBottom: 16, lineHeight: 1.5
          }}>
            La firma elettronica semplice (FES) ha valore legale ai sensi dell'art. 3 eIDAS (UE 910/2014).
            Vengono registrati: IP, timestamp, user-agent, tempo di lettura e hash del documento.
          </div>

          {errore && (
            <div style={{
              background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8,
              padding: '8px 12px', fontSize: 13, color: '#dc2626', marginBottom: 12
            }}>
              {errore}
            </div>
          )}

          {/* Info requisiti mancanti */}
          {!canFirmare && (
            <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 12 }}>
              Mancano:{' '}
              {!nomeDigitato.trim() || nomeDigitato.length <= 3 ? 'nome, ' : ''}
              {firmaB64.length <= 100 ? 'firma disegnata, ' : ''}
              {!checkLetto ? 'checkbox lettura, ' : ''}
              {!checkAccetta ? 'checkbox accettazione' : ''}
            </div>
          )}

          <button
            data-testid="btn-invia-firma"
            disabled={!canFirmare || loading}
            onClick={invia}
            style={{
              width: '100%', padding: '13px', borderRadius: 10, border: 'none',
              background: canFirmare && !loading ? '#059669' : '#e2e8f0',
              color: canFirmare && !loading ? '#fff' : '#94a3b8',
              fontWeight: 700, fontSize: 15, cursor: canFirmare && !loading ? 'pointer' : 'not-allowed',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8
            }}
          >
            {loading ? <Spinner small /> : (
              <>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M17 8l4 4-4 4"/><path d="M3 12h18"/>
                </svg>
                Firma e Invia
              </>
            )}
          </button>
        </>
      )}
    </Overlay>
  );
}

/* ─── Overlay wrapper ─── */
function Overlay({ onClose, children }) {
  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(15,23,42,0.6)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 16, backdropFilter: 'blur(4px)',
      }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{
        background: '#fff', borderRadius: 20,
        padding: '28px 28px 24px',
        width: '100%', maxWidth: 520,
        maxHeight: '90vh', overflowY: 'auto',
        boxShadow: '0 24px 64px rgba(0,0,0,0.25)',
      }}>
        {children}
      </div>
    </div>
  );
}

/* ─── Componente principale ─── */
export default function Portale() {
  const [step, setStep] = useState('loading'); // loading | login | portal
  const [user, setUser] = useState(null);
  const [dipendente, setDipendente] = useState(null);
  const [cedolini, setCedolini] = useState([]);
  const [contratti, setContratti] = useState([]);
  const [loadingDati, setLoadingDati] = useState(false);
  const [msg, setMsg] = useState({ text: '', tipo: 'ok' });
  const [firmaContratto, setFirmaContratto] = useState(null); // contratto da firmare

  const showMsg = (text, tipo = 'ok') => {
    setMsg({ text, tipo });
    setTimeout(() => setMsg({ text: '', tipo: 'ok' }), 5000);
  };

  const processSession = useCallback(async (sessionId) => {
    try {
      const res = await api.post('/api/auth/google/session', { session_id: sessionId });
      const { user: u, token } = res.data;
      if (token) {
        localStorage.setItem('portal_token', token);
        localStorage.setItem('portal_user', JSON.stringify(u));
      }
      window.history.replaceState(null, '', window.location.pathname);
      return u;
    } catch {
      return null;
    }
  }, []);

  const loadPortalData = useCallback(async (email) => {
    setLoadingDati(true);
    try {
      const token = localStorage.getItem('portal_token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};

      const [cedRes, contRes] = await Promise.all([
        api.get('/api/portal/portale/cedolini', { headers }).catch(() => ({ data: [] })),
        api.get('/api/portal/portale/contratti', { headers }).catch(() => ({ data: [] })),
      ]);
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

  useEffect(() => {
    const init = async () => {
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
    setCedolini([]);
    setContratti([]);
    setDipendente(null);
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
      a.download = `cedolino_${cedolino.mese}_${cedolino.anno}.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch {
      showMsg('Download cedolino non disponibile', 'err');
    }
  };

  const MESI_S = ['','Gen','Feb','Mar','Apr','Mag','Giu','Lug','Ago','Set','Ott','Nov','Dic'];

  /* ─── RENDER LOADING ─── */
  if (step === 'loading') {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f8fafc' }}>
        <div style={{ textAlign: 'center', color: '#94a3b8' }}>
          <Spinner />
          <p style={{ marginTop: 12, fontSize: 14 }}>Caricamento portale...</p>
        </div>
      </div>
    );
  }

  /* ─── RENDER LOGIN ─── */
  if (step === 'login') {
    return (
      <div style={{
        minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'linear-gradient(135deg, #1e3a5f 0%, #0f2339 100%)', padding: 24,
      }}>
        <div style={{
          background: '#fff', borderRadius: 24, padding: '48px 40px',
          maxWidth: 440, width: '100%', textAlign: 'center',
          boxShadow: '0 24px 64px rgba(0,0,0,0.35)',
        }}>
          <div style={{
            width: 64, height: 64, borderRadius: 18, background: '#1e3a5f',
            display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px'
          }}>
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#7dd3fc" strokeWidth="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
          </div>
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 900, color: '#0f172a' }}>
            Portale Dipendenti
          </h1>
          <p style={{ margin: '6px 0 0', color: '#64748b', fontSize: 14, fontWeight: 500 }}>
            Ceraldi Group S.r.l.
          </p>

          <p style={{ color: '#475569', fontSize: 14, margin: '28px 0', lineHeight: 1.6 }}>
            Accedi con il tuo account Google aziendale per consultare cedolini, contratti e firmare documenti.
          </p>

          <button
            data-testid="btn-google-login-portale"
            onClick={doGoogleLogin}
            style={{
              width: '100%', padding: '14px 24px', background: '#fff',
              border: '1.5px solid #e2e8f0', borderRadius: 12, cursor: 'pointer',
              fontSize: 15, fontWeight: 700, color: '#1e293b',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12,
              boxShadow: '0 2px 8px rgba(0,0,0,0.06)', transition: 'all 0.15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 6px 20px rgba(0,0,0,0.15)'; e.currentTarget.style.transform = 'translateY(-1px)'; }}
            onMouseLeave={e => { e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.06)'; e.currentTarget.style.transform = 'translateY(0)'; }}
          >
            <GoogleIcon />
            Accedi con Google
          </button>

          <p style={{ fontSize: 12, color: '#94a3b8', marginTop: 20 }}>
            Se non riesci ad accedere, contatta HR per il codice di invito.
          </p>
        </div>
      </div>
    );
  }

  /* ─── RENDER PORTAL ─── */
  const contrattiDaFirmare = contratti.filter(c => !c.firmato);
  const contrattiFirmati = contratti.filter(c => c.firmato);

  return (
    <div style={{ minHeight: '100vh', background: '#f8fafc' }}>
      {/* Modal firma */}
      {firmaContratto && (
        <FirmaModal
          contratto={firmaContratto}
          token={localStorage.getItem('portal_token')}
          onClose={() => setFirmaContratto(null)}
          onFirmato={(docId) => {
            setContratti(prev => prev.map(c => c.id === docId ? { ...c, firmato: true } : c));
            showMsg('Documento firmato con successo!', 'ok');
          }}
        />
      )}

      {/* Header */}
      <div style={{
        background: '#1e3a5f', color: '#fff',
        padding: '14px 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 36, height: 36, borderRadius: 10, background: 'rgba(255,255,255,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#7dd3fc" strokeWidth="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
          </div>
          <div>
            <div style={{ fontWeight: 800, fontSize: 15 }}>Portale Dipendenti</div>
            <div style={{ fontSize: 11, opacity: 0.65 }}>Ceraldi Group S.r.l.</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {user?.picture && <img src={user.picture} alt="" style={{ width: 30, height: 30, borderRadius: '50%', border: '2px solid rgba(255,255,255,0.3)' }} />}
          <span style={{ fontSize: 13, opacity: 0.9 }}>{user?.name || user?.email}</span>
          <button
            data-testid="btn-logout-portale"
            onClick={logout}
            style={{ background: 'rgba(255,255,255,0.15)', border: 'none', color: '#fff', padding: '6px 14px', borderRadius: 8, cursor: 'pointer', fontSize: 12 }}
          >
            Esci
          </button>
        </div>
      </div>

      {/* Content */}
      <div style={{ maxWidth: 900, margin: '0 auto', padding: '28px 20px' }}>

        {/* Banner benvenuto */}
        <div style={{
          background: 'linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%)',
          borderRadius: 16, padding: '22px 28px', color: '#fff', marginBottom: 24
        }}>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 900 }}>
            Benvenuto{dipendente?.nome_completo ? `, ${dipendente.nome_completo}` : user?.name ? `, ${user.name}` : ''}!
          </h2>
          <p style={{ margin: '6px 0 0', opacity: 0.8, fontSize: 14 }}>
            {dipendente?.mansione ? `${dipendente.mansione} — ` : ''}
            Consulta i tuoi documenti e firma i contratti.
          </p>
        </div>

        {/* Avviso contratti da firmare */}
        {contrattiDaFirmare.length > 0 && (
          <div style={{
            background: '#fef3c7', border: '1px solid #fcd34d', borderRadius: 12,
            padding: '14px 20px', marginBottom: 20,
            display: 'flex', alignItems: 'center', gap: 12
          }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#d97706" strokeWidth="2">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            <span style={{ fontSize: 14, fontWeight: 600, color: '#92400e' }}>
              Hai {contrattiDaFirmare.length} documento{contrattiDaFirmare.length > 1 ? 'i' : ''} da firmare
            </span>
          </div>
        )}

        {/* Messaggio feedback */}
        {msg.text && (
          <div style={{
            padding: '10px 16px', borderRadius: 10, marginBottom: 16, fontSize: 14, fontWeight: 600,
            background: msg.tipo === 'ok' ? '#f0fdf4' : '#fef2f2',
            border: `1px solid ${msg.tipo === 'ok' ? '#bbf7d0' : '#fecaca'}`,
            color: msg.tipo === 'ok' ? '#16a34a' : '#dc2626',
          }}>
            {msg.text}
          </div>
        )}

        {loadingDati ? (
          <div style={{ textAlign: 'center', padding: 48, color: '#94a3b8' }}>
            <Spinner />
            <p style={{ marginTop: 12, fontSize: 14 }}>Caricamento documenti...</p>
          </div>
        ) : (
          <>
            {/* ═══ CONTRATTI DA FIRMARE ═══ */}
            {contrattiDaFirmare.length > 0 && (
              <Section title="Documenti da Firmare">
                {contrattiDaFirmare.map(c => (
                  <div key={c.id} style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '14px 18px', background: '#fff', borderRadius: 12,
                    border: '1.5px solid #fcd34d', boxShadow: '0 2px 6px rgba(0,0,0,0.05)',
                  }}>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 14, color: '#0f172a' }}>
                        {c.tipo || c.nome || 'Documento'}
                      </div>
                      <div style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>
                        {c.data_documento || c.data || ''} — In attesa di firma
                      </div>
                    </div>
                    <button
                      data-testid={`btn-firma-${c.id}`}
                      onClick={() => setFirmaContratto(c)}
                      style={{
                        background: '#059669', color: '#fff', border: 'none',
                        borderRadius: 10, padding: '8px 20px', fontSize: 13, fontWeight: 700,
                        cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
                      </svg>
                      Firma ora
                    </button>
                  </div>
                ))}
              </Section>
            )}

            {/* ═══ CEDOLINI ═══ */}
            <Section title="Cedolini Paga">
              {cedolini.length === 0 ? (
                <EmptyState label="Nessun cedolino disponibile" />
              ) : (
                cedolini.map(c => (
                  <div key={c.id || `${c.anno}-${c.mese}`} style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '12px 16px', background: '#fff', borderRadius: 10,
                    border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
                  }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 14, color: '#0f172a' }}>
                        {MESI_S[c.mese] || c.mese} {c.anno}
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
                        borderRadius: 8, padding: '7px 16px', fontSize: 12, fontWeight: 600,
                        cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
                      }}
                    >
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                        <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                      </svg>
                      Scarica PDF
                    </button>
                  </div>
                ))
              )}
            </Section>

            {/* ═══ CONTRATTI FIRMATI ═══ */}
            {contrattiFirmati.length > 0 && (
              <Section title="Documenti Firmati">
                {contrattiFirmati.map(c => (
                  <div key={c.id} style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '12px 16px', background: '#f0fdf4', borderRadius: 10,
                    border: '1px solid #bbf7d0',
                  }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 14, color: '#0f172a' }}>
                        {c.tipo || c.nome || 'Documento'}
                      </div>
                      <div style={{ fontSize: 12, color: '#64748b' }}>
                        {c.firmato_at ? `Firmato il ${c.firmato_at.substring(0,10)}` : 'Firmato'}
                      </div>
                    </div>
                    <span style={{
                      fontSize: 12, fontWeight: 700, color: '#16a34a',
                      padding: '5px 12px', background: '#dcfce7', borderRadius: 8
                    }}>
                      Firmato
                    </span>
                  </div>
                ))}
              </Section>
            )}

            {/* Empty state totale */}
            {cedolini.length === 0 && contratti.length === 0 && (
              <EmptyState label="Nessun documento disponibile. Contatta HR." />
            )}
          </>
        )}
      </div>

      {/* CSS animation */}
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

/* ─── Sub-componenti ─── */
function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <h3 style={{ margin: '0 0 12px', fontSize: 15, fontWeight: 800, color: '#0f172a' }}>{title}</h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {children}
      </div>
    </div>
  );
}

function EmptyState({ label }) {
  return (
    <div style={{ textAlign: 'center', padding: '28px 0', color: '#94a3b8', background: '#fff', borderRadius: 10, border: '1px solid #e2e8f0' }}>
      <p style={{ margin: 0, fontSize: 14 }}>{label}</p>
    </div>
  );
}

function Spinner({ small }) {
  const size = small ? 18 : 24;
  return (
    <div style={{ width: size, height: size, border: `3px solid #e2e8f0`, borderTop: '3px solid #1e3a5f', borderRadius: '50%', animation: 'spin 1s linear infinite', display: 'inline-block' }} />
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
