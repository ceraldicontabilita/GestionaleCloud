import React, { useState, useEffect } from 'react';
import { Key, Check, X, RefreshCw, Shield, User } from 'lucide-react';
import api from '../../api';
import { COLORS, STYLES, useIsMobile, RG, button, badge } from '../../lib/utils';

export default function GestionePIN() {
  const isMobile = useIsMobile();
  const [dipendenti, setDipendenti] = useState([]);
  const [loading, setLoading]       = useState(true);
  const [saving, setSaving]         = useState(null);
  const [pins, setPins]             = useState({});
  const [visibili, setVisibili]     = useState({});
  const [msg, setMsg]               = useState(null);

  const carica = async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/dipendenti/pin/lista');
      setDipendenti(res.data.dipendenti || []);
    } catch {
      setMsg({ tipo: 'errore', testo: 'Errore caricamento dipendenti' });
    }
    setLoading(false);
  };

  useEffect(() => { carica(); }, []);

  const salvaPin = async (dip) => {
    const pin = (pins[dip.id] || '').trim();
    if (!pin) return;
    if (!/^\d{4}$/.test(pin)) {
      setMsg({ tipo: 'errore', testo: `${dip.nome_completo}: PIN deve essere 4 cifre` });
      return;
    }
    setSaving(dip.id);
    try {
      await api.post(`/api/dipendenti/pin/imposta/${dip.id}`, { pin });
      setPins(p => ({ ...p, [dip.id]: '' }));
      setMsg({ tipo: 'ok', testo: `PIN impostato per ${dip.nome_completo}` });
      carica();
    } catch (e) {
      setMsg({ tipo: 'errore', testo: e.response?.data?.detail || 'Errore salvataggio' });
    }
    setSaving(null);
  };

  const resetPin = async (dip) => {
    if (!window.confirm(`Rimuovere il PIN di ${dip.nome_completo}?`)) return;
    setSaving(dip.id);
    try {
      await api.delete(`/api/dipendenti/pin/reset/${dip.id}`);
      setMsg({ tipo: 'ok', testo: `PIN rimosso per ${dip.nome_completo}` });
      carica();
    } catch {
      setMsg({ tipo: 'errore', testo: 'Errore rimozione PIN' });
    }
    setSaving(null);
  };

  const conPin   = dipendenti.filter(d => d.ha_pin).length;
  const senzaPin = dipendenti.length - conPin;

  return (
    <div style={{ padding: isMobile ? '12px 16px' : '24px 32px', maxWidth: 900, margin: '0 auto' }}>

      <div style={{ ...STYLES.header, marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Shield size={24} color="white" />
          <div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>Gestione PIN Operatori</div>
            <div style={{ fontSize: 13, opacity: 0.85 }}>Imposta i PIN per l'accesso ai tablet</div>
          </div>
        </div>
        <button onClick={carica} style={{ ...button('secondary'), display: 'flex', alignItems: 'center', gap: 6 }}>
          <RefreshCw size={14} /> Aggiorna
        </button>
      </div>

      <div style={{ ...RG.kpi(isMobile), marginBottom: 24 }}>
        {[
          { label: 'Totale',    valore: dipendenti.length, colore: COLORS.primary },
          { label: 'Con PIN',   valore: conPin,             colore: COLORS.success },
          { label: 'Senza PIN', valore: senzaPin,           colore: senzaPin > 0 ? COLORS.warning : COLORS.success },
          { label: 'Copertura', valore: dipendenti.length ? `${Math.round(conPin / dipendenti.length * 100)}%` : '0%', colore: COLORS.info },
        ].map(k => (
          <div key={k.label} style={{ ...STYLES.card, textAlign: 'center' }}>
            <div style={{ fontSize: 28, fontWeight: 800, color: k.colore }}>{k.valore}</div>
            <div style={{ fontSize: 12, color: COLORS.gray, marginTop: 4 }}>{k.label}</div>
          </div>
        ))}
      </div>

      {msg && (
        <div style={{
          padding: '12px 16px', borderRadius: 8, marginBottom: 16,
          background: msg.tipo === 'ok' ? '#dcfce7' : '#fee2e2',
          color:      msg.tipo === 'ok' ? '#16a34a' : '#dc2626',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span>{msg.testo}</span>
          <button onClick={() => setMsg(null)} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
            <X size={16} />
          </button>
        </div>
      )}

      <div style={{ ...STYLES.card, padding: 0 }}>
        <div style={{ padding: '14px 20px', borderBottom: `1px solid ${COLORS.grayLight}`, fontWeight: 600, fontSize: 14, color: COLORS.primary }}>
          Operatori — PIN 4 cifre
        </div>

        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: COLORS.gray }}>Caricamento...</div>
        ) : dipendenti.map((dip, i) => (
          <div key={dip.id} style={{
            display: 'flex', alignItems: 'center', gap: 12,
            padding: '14px 20px',
            borderBottom: i < dipendenti.length - 1 ? `1px solid ${COLORS.grayLight}` : 'none',
            flexWrap: isMobile ? 'wrap' : 'nowrap',
            background: i % 2 === 0 ? 'white' : COLORS.grayBg,
          }}>

            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 150 }}>
              <div style={{
                width: 36, height: 36, borderRadius: '50%', flexShrink: 0,
                background: dip.ha_pin
                  ? `linear-gradient(135deg, ${COLORS.success}, #16a34a)`
                  : `linear-gradient(135deg, ${COLORS.gray}, #4b5563)`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <User size={16} color="white" />
              </div>
              <div>
                <div style={{ fontWeight: 600, fontSize: 14 }}>{dip.nome_completo}</div>
                <div style={{ fontSize: 11, color: COLORS.gray }}>{dip.mansione || '—'}</div>
              </div>
            </div>

            <div style={{ minWidth: 80 }}>
              {dip.ha_pin
                ? <span style={{ ...badge('success'), display: 'flex', alignItems: 'center', gap: 4, width: 'fit-content' }}><Check size={11} /> Attivo</span>
                : <span style={{ ...badge('warning'), width: 'fit-content' }}>Nessun PIN</span>
              }
            </div>

            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                type={visibili[dip.id] ? 'text' : 'password'}
                placeholder="0000"
                maxLength={4}
                value={pins[dip.id] || ''}
                onChange={e => setPins(p => ({ ...p, [dip.id]: e.target.value.replace(/\D/g, '').slice(0, 4) }))}
                style={{
                  width: 80, padding: '8px 10px', borderRadius: 8,
                  border: `2px solid ${COLORS.grayLight}`,
                  fontSize: 18, letterSpacing: 6, textAlign: 'center', fontFamily: 'monospace',
                }}
              />
              <button
                onClick={() => setVisibili(v => ({ ...v, [dip.id]: !v[dip.id] }))}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: COLORS.gray, padding: 4 }}
              >
                <Key size={15} />
              </button>
            </div>

            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={() => salvaPin(dip)}
                disabled={!pins[dip.id] || saving === dip.id}
                style={{ ...button('primary'), opacity: !pins[dip.id] ? 0.4 : 1, padding: '7px 14px', fontSize: 13, display: 'flex', alignItems: 'center', gap: 5 }}
              >
                <Check size={13} /> {saving === dip.id ? '...' : 'Salva'}
              </button>
              {dip.ha_pin && (
                <button
                  onClick={() => resetPin(dip)}
                  disabled={saving === dip.id}
                  style={{ ...button('danger'), padding: '7px 14px', fontSize: 13, display: 'flex', alignItems: 'center', gap: 5 }}
                >
                  <X size={13} /> Reset
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 16, padding: '10px 14px', background: '#eff6ff', borderRadius: 8, fontSize: 12, color: '#1d4ed8', display: 'flex', gap: 8 }}>
        <Shield size={14} style={{ flexShrink: 0, marginTop: 1 }} />
        <span>I PIN vengono salvati come hash bcrypt — non recuperabili, solo reimpostabili. Servono per accedere ai tablet di reparto.</span>
      </div>
    </div>
  );
}
