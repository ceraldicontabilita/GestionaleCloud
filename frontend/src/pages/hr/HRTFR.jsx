import React, { useState, useEffect } from 'react';
import { Plus, Trash2, AlertCircle } from 'lucide-react';
import api from '../../api';
import { COLORS } from '../../lib/utils';

function formatEuro(v) {
  if (v == null || isNaN(v)) return '—';
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(v);
}
function formatData(d) {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('it-IT');
}

export default function HRTFR() {
  const [dipendenti, setDipendenti] = useState([]);
  const [selected, setSelected] = useState(null);
  const [situazione, setSituazione] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ importo: '', data: '', note: '' });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get('/api/dipendenti')
      .then(r => {
        const list = Array.isArray(r.data) ? r.data : r.data?.dipendenti || [];
        setDipendenti(list);
      })
      .catch(() => {});
  }, []);

  const caricaSituazione = async (dip) => {
    setSelected(dip);
    setSituazione(null);
    setLoading(true);
    try {
      const [sitRes, accRes] = await Promise.all([
        api.get(`/api/tfr/situazione/${dip.id}`),
        api.get(`/api/tfr/acconti/${dip.id}`),
      ]);
      setSituazione({
        ...sitRes.data,
        acconti: Array.isArray(accRes.data) ? accRes.data : accRes.data?.acconti || [],
      });
    } catch (e) {
      setSituazione({ acconti: [], error: true });
    } finally { setLoading(false); }
  };

  const salvaAcconto = async () => {
    if (!form.importo || !selected) return;
    setSaving(true);
    try {
      await api.post('/api/tfr/acconti', {
        dipendente_id: selected.id,
        importo: Number(form.importo),
        data: form.data || new Date().toISOString().split('T')[0],
        note: form.note,
      });
      setShowForm(false);
      setForm({ importo: '', data: '', note: '' });
      caricaSituazione(selected);
    } catch (e) { console.error(e); }
    finally { setSaving(false); }
  };

  const eliminaAcconto = async (id) => {
    if (!window.confirm('Eliminare questo acconto TFR?')) return;
    try {
      await api.delete(`/api/tfr/acconti/${id}`);
      caricaSituazione(selected);
    } catch (e) { console.error(e); }
  };

  const nome = selected ? (selected.nome_completo || `${selected.cognome || ''} ${selected.nome || ''}`.trim()) : '';

  return (
    <div style={{ padding: 24, display: 'flex', gap: 24, height: 'calc(100vh - 160px)' }}>

      {/* Lista dipendenti */}
      <div style={{ width: 260, minWidth: 260, background: 'white', border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '14px 16px', borderBottom: `1px solid ${COLORS.border}`, fontWeight: 700, fontSize: 14, color: COLORS.text }}>Dipendenti</div>
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {dipendenti.map(d => {
            const n = d.nome_completo || `${d.cognome || ''} ${d.nome || ''}`.trim();
            return (
              <div
                key={d.id}
                data-testid={`tfr-dip-${d.id}`}
                onClick={() => caricaSituazione(d)}
                style={{
                  padding: '10px 16px',
                  cursor: 'pointer',
                  background: selected?.id === d.id ? `${COLORS.primary}10` : 'transparent',
                  borderLeft: selected?.id === d.id ? `3px solid ${COLORS.primary}` : '3px solid transparent',
                  transition: 'all 0.1s',
                }}
              >
                <div style={{ fontWeight: selected?.id === d.id ? 700 : 500, fontSize: 13, color: selected?.id === d.id ? COLORS.primary : COLORS.text }}>{n}</div>
                <div style={{ fontSize: 11, color: COLORS.textMuted }}>{d.mansione || ''}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Dettaglio TFR */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {!selected && (
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: COLORS.textMuted }}>
            <div style={{ textAlign: 'center' }}>
              <AlertCircle size={48} style={{ opacity: 0.2, marginBottom: 16 }} />
              <div style={{ fontWeight: 600 }}>Seleziona un dipendente</div>
              <div style={{ fontSize: 13, marginTop: 4 }}>per vedere la situazione TFR</div>
            </div>
          </div>
        )}

        {selected && (
          <>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: COLORS.text }}>TFR — {nome}</h2>
              <button
                data-testid="btn-nuovo-acconto-tfr"
                onClick={() => setShowForm(v => !v)}
                style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', background: COLORS.primary, color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13 }}
              >
                <Plus size={14} /> Nuovo Acconto
              </button>
            </div>

            {/* Form nuovo acconto */}
            {showForm && (
              <div style={{ background: 'white', border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 20, marginBottom: 20 }}>
                <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 16 }}>Nuovo Acconto TFR</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 2fr', gap: 12, marginBottom: 16 }}>
                  <div>
                    <label style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}>IMPORTO (€) *</label>
                    <input type="number" value={form.importo} onChange={e => setForm(p => ({ ...p, importo: e.target.value }))} placeholder="0.00" style={{ width: '100%', padding: '8px 10px', border: `1px solid ${COLORS.border}`, borderRadius: 6, fontSize: 14, boxSizing: 'border-box' }} />
                  </div>
                  <div>
                    <label style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}>DATA</label>
                    <input type="date" value={form.data} onChange={e => setForm(p => ({ ...p, data: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: `1px solid ${COLORS.border}`, borderRadius: 6, fontSize: 14, boxSizing: 'border-box' }} />
                  </div>
                  <div>
                    <label style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}>NOTE</label>
                    <input value={form.note} onChange={e => setForm(p => ({ ...p, note: e.target.value }))} placeholder="Note opzionali" style={{ width: '100%', padding: '8px 10px', border: `1px solid ${COLORS.border}`, borderRadius: 6, fontSize: 14, boxSizing: 'border-box' }} />
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button onClick={salvaAcconto} disabled={saving || !form.importo} style={{ padding: '8px 18px', background: '#22c55e', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13, fontWeight: 600, opacity: saving || !form.importo ? 0.6 : 1 }}>
                    {saving ? 'Salvataggio…' : 'Salva'}
                  </button>
                  <button onClick={() => setShowForm(false)} style={{ padding: '8px 14px', background: '#f1f5f9', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13 }}>Annulla</button>
                </div>
              </div>
            )}

            {loading && <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>Caricamento…</div>}

            {!loading && situazione && (
              <>
                {/* KPI situazione */}
                {!situazione.error && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 20 }}>
                    {[
                      { label: 'TFR Maturato', value: formatEuro(situazione.tfr_maturato || situazione.montante) },
                      { label: 'Acconti Erogati', value: formatEuro(situazione.acconti_totali || situazione.totale_acconti) },
                      { label: 'TFR Netto', value: formatEuro((situazione.tfr_maturato || 0) - (situazione.acconti_totali || 0)) },
                    ].map(s => (
                      <div key={s.label} style={{ background: 'white', border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: '14px 16px' }}>
                        <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase' }}>{s.label}</div>
                        <div style={{ fontSize: 20, fontWeight: 700, color: COLORS.text, marginTop: 4 }}>{s.value}</div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Lista acconti */}
                <div style={{ background: 'white', border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: 'hidden' }}>
                  <div style={{ padding: '14px 16px', borderBottom: `1px solid ${COLORS.border}`, fontWeight: 700, fontSize: 14, color: COLORS.text }}>
                    Acconti Erogati ({situazione.acconti?.length || 0})
                  </div>
                  {situazione.acconti?.length === 0 ? (
                    <div style={{ padding: 32, textAlign: 'center', color: COLORS.textMuted, fontSize: 13 }}>Nessun acconto erogato</div>
                  ) : (
                    situazione.acconti?.map((a, i) => (
                      <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderBottom: `1px solid ${COLORS.border}` }}>
                        <div>
                          <div style={{ fontWeight: 700, color: COLORS.primary, fontSize: 16 }}>{formatEuro(a.importo)}</div>
                          <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 2 }}>{formatData(a.data)}{a.note ? ` — ${a.note}` : ''}</div>
                        </div>
                        <button
                          data-testid={`btn-elimina-tfr-${i}`}
                          onClick={() => eliminaAcconto(a.id)}
                          style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '6px 12px', background: '#fee2e2', color: '#dc2626', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12 }}
                        >
                          <Trash2 size={13} /> Elimina
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
