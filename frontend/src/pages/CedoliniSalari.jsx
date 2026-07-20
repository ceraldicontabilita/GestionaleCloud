import React, { useEffect, useState } from 'react';
import { CheckCircle2, FileText, Loader2, Search, TriangleAlert } from 'lucide-react';
import { toast } from 'sonner';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuroD } from '../lib/utils';

const MESI = [
  '', 'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
  'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre',
  'Tredicesima', 'Quattordicesima',
];

export default function CedoliniSalari() {
  const { anno } = useAnnoGlobale();
  const [righe, setRighe] = useState([]);
  const [loading, setLoading] = useState(true);
  const [ricerca, setRicerca] = useState('');
  const [pdfInApertura, setPdfInApertura] = useState(null);

  useEffect(() => {
    let attivo = true;
    setLoading(true);
    api.get(`/api/prima-nota-salari/salari?anno=${encodeURIComponent(anno)}`)
      .then(r => { if (attivo) setRighe(Array.isArray(r.data) ? r.data : []); })
      .catch(() => { if (attivo) toast.error('Impossibile caricare i cedolini'); })
      .finally(() => { if (attivo) setLoading(false); });
    return () => { attivo = false; };
  }, [anno]);

  const apriCedolino = async riga => {
    setPdfInApertura(riga.id);
    try {
      const risposta = await api.get(
        `/api/prima-nota-salari/salari/${encodeURIComponent(riga.id)}/cedolino-pdf`,
        { responseType: 'blob' },
      );
      const url = URL.createObjectURL(new Blob([risposta.data], { type: 'application/pdf' }));
      const finestra = window.open(url, '_blank', 'noopener,noreferrer');
      if (!finestra) {
        const link = document.createElement('a');
        link.href = url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.click();
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (errore) {
      toast.error(errore.response?.data?.detail || 'PDF del cedolino non disponibile');
    } finally {
      setPdfInApertura(null);
    }
  };

  const termine = ricerca.trim().toLowerCase();
  const visibili = righe.filter(r => !termine || `${r.dipendente || ''} ${r.dipendente_nome || ''}`.toLowerCase().includes(termine));

  return (
    <main style={{ maxWidth: 1500, margin: '0 auto', padding: '22px 20px 60px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'end', gap: 16, flexWrap: 'wrap', marginBottom: 18 }}>
        <div>
          <h1 style={{ margin: 0, color: '#0f2744', fontSize: 25 }}>Cedolini paga {anno}</h1>
          <p style={{ margin: '5px 0 0', color: '#64748b' }}>
            Importi letti dai PDF nella cartella Drive e riscontro dei bonifici.
          </p>
        </div>
        <label style={{ position: 'relative', minWidth: 280 }}>
          <Search size={17} style={{ position: 'absolute', left: 12, top: 11, color: '#64748b' }} />
          <input
            value={ricerca}
            onChange={e => setRicerca(e.target.value)}
            placeholder="Cerca dipendente"
            aria-label="Cerca dipendente"
            style={{ width: '100%', minHeight: 40, padding: '8px 12px 8px 38px', border: '1px solid #cbd5e1', borderRadius: 9 }}
          />
        </label>
      </div>

      <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 850 }}>
          <thead style={{ background: '#0f2744', color: '#fff' }}>
            <tr>
              {['Dipendente', 'Periodo', 'Importo busta', 'Bonifico', 'Stato banca'].map(t => (
                <th key={t} style={{ padding: '12px 14px', textAlign: t === 'Dipendente' || t === 'Periodo' ? 'left' : 'right', fontSize: 12 }}>{t}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan="5" style={{ padding: 35, textAlign: 'center', color: '#64748b' }}><Loader2 size={20} className="spin" /> Caricamento...</td></tr>
            )}
            {!loading && visibili.length === 0 && (
              <tr><td colSpan="5" style={{ padding: 35, textAlign: 'center', color: '#64748b' }}>Nessun cedolino trovato.</td></tr>
            )}
            {!loading && visibili.map(r => (
              <tr key={r.id} style={{ borderTop: '1px solid #e2e8f0' }}>
                <td style={{ padding: '11px 14px', fontWeight: 700, color: '#0f2744' }}>{r.dipendente_nome || r.dipendente || '—'}</td>
                <td style={{ padding: '11px 14px', color: '#475569' }}>{MESI[Number(r.mese)] || r.mese || '—'} {r.anno}</td>
                <td style={{ padding: '8px 14px', textAlign: 'right' }}>
                  <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'flex-end', gap: 9, flexWrap: 'wrap' }}>
                    <strong>{formatEuroD(r.importo_busta || 0)}</strong>
                    {r.cedolino_disponibile ? (
                      <button
                        onClick={() => apriCedolino(r)}
                        disabled={pdfInApertura === r.id}
                        style={{ minHeight: 38, border: 0, borderRadius: 8, padding: '8px 11px', background: '#2563eb', color: '#fff', fontWeight: 700, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6 }}
                      >
                        {pdfInApertura === r.id ? <Loader2 size={16} /> : <FileText size={16} />}
                        Vedi cedolino
                      </button>
                    ) : <span style={{ color: '#94a3b8', fontSize: 12 }}>PDF non disponibile</span>}
                  </div>
                </td>
                <td style={{ padding: '11px 14px', textAlign: 'right', fontWeight: 700 }}>{formatEuroD(r.importo_bonifico || 0)}</td>
                <td style={{ padding: '11px 14px', textAlign: 'right' }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: r.riconciliato ? '#15803d' : '#b45309', fontWeight: 700 }}>
                    {r.riconciliato ? <CheckCircle2 size={17} /> : <TriangleAlert size={17} />}
                    {r.riconciliato ? 'Riconciliato' : 'Da verificare'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
