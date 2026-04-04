import React, { useState, useEffect } from 'react';
import { Calendar, Check, X, Clock } from 'lucide-react';
import api from '../../api';
import { COLORS } from '../../lib/utils';

export default function HRPresenze() {
  const [richieste, setRichieste] = useState([]);
  const [dipendenti, setDipendenti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [motifoRifiuto, setMotivoRifiuto] = useState({});

  const load = () => {
    setLoading(true);
    Promise.all([
      api.get('/api/attendance/richieste-pending'),
      api.get('/api/employees?limit=200'),
    ])
      .then(([r, d]) => {
        setRichieste(Array.isArray(r.data) ? r.data : r.data?.richieste || []);
        setDipendenti(Array.isArray(d.data) ? d.data : d.data?.dipendenti || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const approva = async (id) => {
    try {
      await api.put(`/api/attendance/richiesta-assenza/${id}/approva`);
      load();
    } catch (e) { console.error(e); }
  };

  const rifiuta = async (id) => {
    const motivo = motifoRifiuto[id] || '';
    try {
      await api.put(`/api/attendance/richiesta-assenza/${id}/rifiuta`, { motivo });
      load();
    } catch (e) { console.error(e); }
  };

  return (
    <div style={{ padding: 24 }}>
      <h1 style={{ margin: '0 0 24px', fontSize: 22, fontWeight: 700, color: COLORS.text }}>Presenze & Richieste</h1>

      {/* KPI */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 16, marginBottom: 24 }}>
        {[
          { label: 'Richieste in Attesa', value: richieste.filter(r => r.stato === 'pending' || !r.stato).length, icon: <Clock size={20} color={COLORS.primary} /> },
          { label: 'Dipendenti Attivi', value: dipendenti.length, icon: <Calendar size={20} color="#22c55e" /> },
        ].map(s => (
          <div key={s.label} style={{ background: 'white', border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 16 }}>
            <div style={{ width: 44, height: 44, borderRadius: '50%', background: '#f0f4f8', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{s.icon}</div>
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{s.label}</div>
              <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.text }}>{loading ? '…' : s.value}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Richieste Pending */}
      <div style={{ background: 'white', border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: `1px solid ${COLORS.border}`, fontWeight: 700, fontSize: 15, color: COLORS.text }}>
          Richieste Assenza da Approvare
          {richieste.length > 0 && (
            <span style={{ marginLeft: 8, background: COLORS.primary, color: 'white', borderRadius: 99, fontSize: 11, padding: '2px 8px', fontWeight: 700 }}>{richieste.length}</span>
          )}
        </div>

        {loading && <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>Caricamento…</div>}

        {!loading && richieste.length === 0 && (
          <div style={{ padding: 48, textAlign: 'center', color: COLORS.textMuted }}>
            <Check size={40} style={{ marginBottom: 12, opacity: 0.3, color: '#22c55e' }} />
            <div style={{ fontWeight: 600 }}>Nessuna richiesta in attesa</div>
          </div>
        )}

        {!loading && richieste.map((r, i) => (
          <div key={i} style={{ padding: '16px 20px', borderBottom: `1px solid ${COLORS.border}`, display: 'flex', gap: 16, alignItems: 'flex-start' }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, fontSize: 14, color: COLORS.text, marginBottom: 4 }}>
                {r.dipendente_nome || r.employee_name || `Dipendente ${r.employee_id?.slice(-6)}`}
              </div>
              <div style={{ fontSize: 13, color: COLORS.textMuted, marginBottom: 4 }}>
                <strong>{r.tipo || 'Assenza'}</strong> — Dal {new Date(r.data_inizio || r.start_date).toLocaleDateString('it-IT')} al {new Date(r.data_fine || r.end_date).toLocaleDateString('it-IT')}
              </div>
              {r.note && <div style={{ fontSize: 12, color: COLORS.textMuted, fontStyle: 'italic' }}>"{r.note}"</div>}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minWidth: 200 }}>
              <input
                placeholder="Motivo rifiuto (opzionale)"
                value={motifoRifiuto[r.id] || ''}
                onChange={e => setMotivoRifiuto(p => ({ ...p, [r.id]: e.target.value }))}
                style={{ padding: '6px 10px', border: `1px solid ${COLORS.border}`, borderRadius: 6, fontSize: 12 }}
              />
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  data-testid={`btn-approva-${r.id}`}
                  onClick={() => approva(r.id)}
                  style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4, padding: '7px 0', background: '#dcfce7', color: '#16a34a', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12, fontWeight: 600 }}
                >
                  <Check size={13} /> Approva
                </button>
                <button
                  data-testid={`btn-rifiuta-${r.id}`}
                  onClick={() => rifiuta(r.id)}
                  style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4, padding: '7px 0', background: '#fee2e2', color: '#dc2626', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12, fontWeight: 600 }}
                >
                  <X size={13} /> Rifiuta
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
