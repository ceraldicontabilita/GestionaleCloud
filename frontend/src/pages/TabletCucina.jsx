/**
 * TabletCucina.jsx — Vista tablet per rosticceria e pasticceria
 * Flusso: 1) Scelta reparto → 2) Login PIN operatore → 3) Griglia prodotti → 4) Registra produzione
 */
import React, { useState, useEffect, useRef } from 'react';
import { ChefHat, LogOut, CheckCircle, X, ArrowLeft, Package } from 'lucide-react';
import api from '../api';
import { COLORS, useIsMobile } from '../lib/utils';
import CardProdotto, { getColoreProdotto } from '../components/cucina/CardProdotto.jsx';

const REPARTI = [
  { id: 'rosticceria', label: 'Rosticceria', emoji: '🥙', colore: '#1e3a5f', light: '#e8f4fd' },
  { id: 'pasticceria', label: 'Pasticceria', emoji: '🍰', colore: '#b45309', light: '#fef3c7' },
];

// ─── Schermata scelta reparto ─────────────────────────────────────────────────
function SceltaReparto({ onReparto }) {
  return (
    <div style={{
      minHeight: '100vh', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%)',
      padding: 32, gap: 32,
    }}>
      <div style={{ textAlign: 'center', color: 'white' }}>
        <ChefHat size={56} style={{ marginBottom: 12 }} />
        <div style={{ fontSize: 28, fontWeight: 800 }}>Tablet Cucina</div>
        <div style={{ fontSize: 15, opacity: 0.8, marginTop: 6 }}>Seleziona il reparto</div>
      </div>
      <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', justifyContent: 'center' }}>
        {REPARTI.map(r => (
          <button
            key={r.id}
            onClick={() => onReparto(r)}
            style={{
              width: 180, height: 180, borderRadius: 24,
              background: 'white', border: 'none', cursor: 'pointer',
              display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center', gap: 12,
              boxShadow: '0 8px 32px rgba(0,0,0,0.2)',
              transition: 'transform 0.15s',
            }}
            onMouseDown={e => { e.currentTarget.style.transform = 'scale(0.95)'; }}
            onMouseUp={e => { e.currentTarget.style.transform = 'scale(1)'; }}
            onTouchStart={e => { e.currentTarget.style.transform = 'scale(0.95)'; }}
            onTouchEnd={e => { e.currentTarget.style.transform = 'scale(1)'; }}
          >
            <div style={{ fontSize: 56 }}>{r.emoji}</div>
            <div style={{ fontSize: 18, fontWeight: 700, color: r.colore }}>{r.label}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── Schermata login PIN ──────────────────────────────────────────────────────
function LoginPIN({ reparto, onLogin, onBack }) {
  const [dipendenti, setDipendenti] = useState([]);
  const [selezionato, setSelezionato] = useState(null);
  const [pin, setPin]               = useState('');
  const [errore, setErrore]         = useState('');
  const [loading, setLoading]       = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    api.get('/api/dipendenti/pin/lista')
      .then(r => setDipendenti((r.data.dipendenti || []).filter(d => d.ha_pin)))
      .catch(() => setErrore('Impossibile caricare gli operatori'));
  }, []);

  useEffect(() => {
    if (selezionato) inputRef.current?.focus();
  }, [selezionato]);

  const handleLogin = async () => {
    if (!selezionato || pin.length !== 4) return;
    setLoading(true);
    setErrore('');
    try {
      const res = await api.post(`/api/dipendenti/pin/verifica/${selezionato.id}`, { pin });
      if (res.data.valido) {
        onLogin({ ...selezionato, nome: res.data.nome });
      } else {
        setErrore('PIN non corretto');
        setPin('');
      }
    } catch {
      setErrore('Errore verifica PIN');
      setPin('');
    }
    setLoading(false);
  };

  // Tastiera numerica a schermo
  const tasti = ['1','2','3','4','5','6','7','8','9','','0','⌫'];

  const premiTasto = (t) => {
    if (t === '⌫') { setPin(p => p.slice(0, -1)); return; }
    if (t === '') return;
    if (pin.length < 4) setPin(p => p + t);
  };

  return (
    <div style={{
      minHeight: '100vh', background: reparto.light,
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', padding: 24, gap: 24,
    }}>
      <button onClick={onBack} style={{
        position: 'absolute', top: 20, left: 20,
        background: 'none', border: 'none', cursor: 'pointer',
        display: 'flex', alignItems: 'center', gap: 6,
        color: reparto.colore, fontWeight: 600, fontSize: 14,
      }}>
        <ArrowLeft size={18} /> Cambia reparto
      </button>

      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 48 }}>{reparto.emoji}</div>
        <div style={{ fontSize: 22, fontWeight: 700, color: reparto.colore }}>{reparto.label}</div>
        <div style={{ fontSize: 14, color: '#6b7280', marginTop: 4 }}>Chi sei?</div>
      </div>

      {/* Lista operatori */}
      {!selezionato ? (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, justifyContent: 'center', maxWidth: 500 }}>
          {dipendenti.length === 0 && !errore && (
            <div style={{ color: '#6b7280', fontSize: 14 }}>Caricamento operatori...</div>
          )}
          {dipendenti.map(d => (
            <button
              key={d.id}
              onClick={() => { setSelezionato(d); setPin(''); setErrore(''); }}
              style={{
                padding: '14px 22px', borderRadius: 12, border: `2px solid ${reparto.colore}`,
                background: 'white', cursor: 'pointer', fontWeight: 600,
                fontSize: 15, color: reparto.colore,
                boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
                transition: 'transform 0.1s',
              }}
              onMouseDown={e => { e.currentTarget.style.transform = 'scale(0.95)'; }}
              onMouseUp={e => { e.currentTarget.style.transform = 'scale(1)'; }}
              onTouchStart={e => { e.currentTarget.style.transform = 'scale(0.95)'; }}
              onTouchEnd={e => { e.currentTarget.style.transform = 'scale(1)'; }}
            >
              {d.nome_completo}
            </button>
          ))}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
          <div style={{ fontWeight: 700, fontSize: 18, color: reparto.colore }}>
            {selezionato.nome_completo}
          </div>

          {/* Indicatore PIN */}
          <div style={{ display: 'flex', gap: 12, marginBottom: 4 }}>
            {[0,1,2,3].map(i => (
              <div key={i} style={{
                width: 20, height: 20, borderRadius: '50%',
                background: i < pin.length ? reparto.colore : '#e5e7eb',
                transition: 'background 0.15s',
              }} />
            ))}
          </div>

          {errore && (
            <div style={{ color: '#dc2626', fontSize: 13, fontWeight: 600 }}>{errore}</div>
          )}

          {/* Tastiera */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
            {tasti.map((t, i) => (
              <button
                key={i}
                onClick={() => premiTasto(t)}
                disabled={t === ''}
                style={{
                  width: 72, height: 72, borderRadius: 16,
                  background: t === '' ? 'transparent' : 'white',
                  border: t === '' ? 'none' : `2px solid #e5e7eb`,
                  fontSize: 24, fontWeight: 600, cursor: t === '' ? 'default' : 'pointer',
                  color: '#1e293b', boxShadow: t === '' ? 'none' : '0 2px 6px rgba(0,0,0,0.08)',
                  transition: 'transform 0.1s',
                }}
                onMouseDown={e => { if (t !== '') e.currentTarget.style.transform = 'scale(0.9)'; }}
                onMouseUp={e => { e.currentTarget.style.transform = 'scale(1)'; }}
                onTouchStart={e => { if (t !== '') e.currentTarget.style.transform = 'scale(0.9)'; }}
                onTouchEnd={e => { e.currentTarget.style.transform = 'scale(1)'; }}
              >
                {t}
              </button>
            ))}
          </div>

          <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
            <button
              onClick={() => { setSelezionato(null); setPin(''); setErrore(''); }}
              style={{
                padding: '12px 24px', borderRadius: 12, border: `2px solid #e5e7eb`,
                background: 'white', cursor: 'pointer', fontWeight: 600, fontSize: 15, color: '#6b7280',
              }}
            >
              ← Indietro
            </button>
            <button
              onClick={handleLogin}
              disabled={pin.length !== 4 || loading}
              style={{
                padding: '12px 24px', borderRadius: 12, border: 'none',
                background: pin.length === 4 ? reparto.colore : '#e5e7eb',
                cursor: pin.length === 4 ? 'pointer' : 'default',
                fontWeight: 700, fontSize: 15, color: pin.length === 4 ? 'white' : '#9ca3af',
                transition: 'background 0.2s',
              }}
            >
              {loading ? 'Verifica...' : 'Entra →'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Modale registrazione produzione ─────────────────────────────────────────
function ModaleRegistra({ prodotto, reparto, operatore, onConferma, onChiudi }) {
  const [pezzi, setPezzi]   = useState('');
  const [note, setNote]     = useState('');
  const [saving, setSaving] = useState(false);
  const [ok, setOk]         = useState(false);
  const [err, setErr]       = useState('');

  const conferma = async () => {
    const n = parseInt(pezzi);
    if (!n || n <= 0) { setErr('Inserisci il numero di pezzi'); return; }
    setSaving(true);
    setErr('');
    try {
      await api.post('/api/tr/produzioni/', {
        ricetta_id:   prodotto.id,
        ricetta_nome: prodotto.nome,
        pezzi:        n,
        note:         `Operatore: ${operatore.nome_completo || operatore.nome}. ${note}`.trim(),
      });
      setOk(true);
      setTimeout(() => { onConferma(); }, 1400);
    } catch (e) {
      setErr(e.response?.data?.detail || 'Errore registrazione');
      setSaving(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000, padding: 16,
    }}>
      <div style={{
        background: 'white', borderRadius: 20, padding: 28,
        width: '100%', maxWidth: 380,
        boxShadow: '0 16px 48px rgba(0,0,0,0.25)',
      }}>
        {ok ? (
          <div style={{ textAlign: 'center', padding: '16px 0' }}>
            <CheckCircle size={56} color="#16a34a" style={{ marginBottom: 12 }} />
            <div style={{ fontSize: 20, fontWeight: 700, color: '#16a34a' }}>Produzione registrata!</div>
            <div style={{ color: '#6b7280', marginTop: 6 }}>{prodotto.nome} — {pezzi} pz</div>
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
              <div>
                <div style={{ fontSize: 18, fontWeight: 700, color: '#1e293b' }}>{prodotto.nome}</div>
                <div style={{ fontSize: 13, color: '#6b7280', marginTop: 2 }}>Registra produzione</div>
              </div>
              <button onClick={onChiudi} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280' }}>
                <X size={22} />
              </button>
            </div>

            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 13, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 6 }}>
                Numero di pezzi *
              </label>
              <input
                type="number"
                min="1"
                value={pezzi}
                onChange={e => setPezzi(e.target.value)}
                placeholder="es. 24"
                autoFocus
                style={{
                  width: '100%', padding: '12px 14px', borderRadius: 10,
                  border: '2px solid #e5e7eb', fontSize: 20, fontWeight: 700,
                  textAlign: 'center', boxSizing: 'border-box',
                  color: '#1e293b',
                }}
              />
            </div>

            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 13, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 6 }}>
                Note (opzionale)
              </label>
              <textarea
                value={note}
                onChange={e => setNote(e.target.value)}
                placeholder="es. impasto ottimo, variante cioccolato..."
                rows={2}
                style={{
                  width: '100%', padding: '10px 12px', borderRadius: 10,
                  border: '2px solid #e5e7eb', fontSize: 14, resize: 'none',
                  boxSizing: 'border-box', color: '#374151',
                }}
              />
            </div>

            {err && (
              <div style={{ color: '#dc2626', fontSize: 13, marginBottom: 12, fontWeight: 600 }}>{err}</div>
            )}

            <div style={{ display: 'flex', gap: 10 }}>
              <button
                onClick={onChiudi}
                style={{
                  flex: 1, padding: '13px', borderRadius: 12,
                  border: '2px solid #e5e7eb', background: 'white',
                  cursor: 'pointer', fontWeight: 600, fontSize: 15, color: '#6b7280',
                }}
              >
                Annulla
              </button>
              <button
                onClick={conferma}
                disabled={saving || !pezzi}
                style={{
                  flex: 2, padding: '13px', borderRadius: 12, border: 'none',
                  background: pezzi ? reparto.colore : '#e5e7eb',
                  cursor: pezzi ? 'pointer' : 'default',
                  fontWeight: 700, fontSize: 15,
                  color: pezzi ? 'white' : '#9ca3af',
                }}
              >
                {saving ? 'Salvataggio...' : '✓ Conferma'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ─── Griglia prodotti ─────────────────────────────────────────────────────────
function GrigliaProdotti({ reparto, operatore, onLogout }) {
  const isMobile = useIsMobile();
  const [prodotti, setProdotti]   = useState([]);
  const [loading, setLoading]     = useState(true);
  const [search, setSearch]       = useState('');
  const [selezionato, setSelezionato] = useState(null);
  const [toast, setToast]         = useState(null);

  const carica = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/api/tr/tablet/${reparto.id}`);
      setProdotti(res.data.prodotti || []);
    } catch {
      setProdotti([]);
    }
    setLoading(false);
  };

  useEffect(() => { carica(); }, [reparto.id]);

  const prodottiFiltrati = prodotti.filter(p =>
    !search || p.nome?.toLowerCase().includes(search.toLowerCase())
  );

  const mostraToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  };

  const cols = isMobile ? 2 : 4;

  return (
    <div style={{ minHeight: '100vh', background: '#f8fafc' }}>

      {/* Header */}
      <div style={{
        background: reparto.colore,
        padding: '14px 20px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        position: 'sticky', top: 0, zIndex: 100,
        boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'white' }}>
          <span style={{ fontSize: 24 }}>{reparto.emoji}</span>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16 }}>{reparto.label}</div>
            <div style={{ fontSize: 12, opacity: 0.85 }}>
              👤 {operatore.nome_completo || operatore.nome}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={carica}
            style={{
              background: 'rgba(255,255,255,0.2)', border: 'none', borderRadius: 8,
              color: 'white', padding: '7px 12px', cursor: 'pointer', fontSize: 13, fontWeight: 600,
            }}
          >
            ↻
          </button>
          <button
            onClick={onLogout}
            style={{
              background: 'rgba(255,255,255,0.2)', border: 'none', borderRadius: 8,
              color: 'white', padding: '7px 12px', cursor: 'pointer', fontSize: 13,
              display: 'flex', alignItems: 'center', gap: 5,
            }}
          >
            <LogOut size={14} /> Esci
          </button>
        </div>
      </div>

      {/* Ricerca */}
      <div style={{ padding: '12px 16px' }}>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder={`Cerca in ${reparto.label}...`}
          style={{
            width: '100%', padding: '10px 14px', borderRadius: 10,
            border: '2px solid #e5e7eb', fontSize: 15,
            boxSizing: 'border-box', background: 'white',
          }}
        />
      </div>

      {/* Contatore */}
      <div style={{ padding: '0 16px 8px', color: '#6b7280', fontSize: 13 }}>
        {loading ? 'Caricamento...' : `${prodottiFiltrati.length} prodotti`}
      </div>

      {/* Griglia */}
      {loading ? (
        <div style={{ padding: 48, textAlign: 'center', color: '#94a3b8', fontSize: 15 }}>
          Caricamento prodotti...
        </div>
      ) : prodottiFiltrati.length === 0 ? (
        <div style={{ padding: 48, textAlign: 'center', color: '#94a3b8' }}>
          <Package size={40} style={{ marginBottom: 12, opacity: 0.5 }} />
          <div>Nessun prodotto trovato</div>
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${cols}, 1fr)`,
          gap: 12,
          padding: '0 16px 32px',
        }}>
          {prodottiFiltrati.map(p => (
            <CardProdotto
              key={p.id}
              prodotto={p}
              reparto={reparto.id}
              onTap={() => setSelezionato(p)}
              hasVarianti={p.varianti?.length > 0}
            />
          ))}
        </div>
      )}

      {/* Modale registrazione */}
      {selezionato && (
        <ModaleRegistra
          prodotto={selezionato}
          reparto={reparto}
          operatore={operatore}
          onConferma={() => {
            setSelezionato(null);
            mostraToast(`✓ ${selezionato.nome} registrato`);
            carica();
          }}
          onChiudi={() => setSelezionato(null)}
        />
      )}

      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)',
          background: '#16a34a', color: 'white', padding: '12px 24px',
          borderRadius: 12, fontWeight: 600, fontSize: 14, zIndex: 2000,
          boxShadow: '0 4px 16px rgba(0,0,0,0.2)',
        }}>
          {toast}
        </div>
      )}
    </div>
  );
}

// ─── Componente principale ────────────────────────────────────────────────────
export default function TabletCucina() {
  const [fase, setFase]         = useState('reparto');   // reparto | login | griglia
  const [reparto, setReparto]   = useState(null);
  const [operatore, setOperatore] = useState(null);

  if (fase === 'reparto') {
    return <SceltaReparto onReparto={r => { setReparto(r); setFase('login'); }} />;
  }

  if (fase === 'login') {
    return (
      <LoginPIN
        reparto={reparto}
        onLogin={op => { setOperatore(op); setFase('griglia'); }}
        onBack={() => setFase('reparto')}
      />
    );
  }

  return (
    <GrigliaProdotti
      reparto={reparto}
      operatore={operatore}
      onLogout={() => { setOperatore(null); setFase('reparto'); }}
    />
  );
}
