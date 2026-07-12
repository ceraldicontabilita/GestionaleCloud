import React, { useEffect, useState } from 'react';
import { RefreshCw, Wallet } from 'lucide-react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, formatDateIT, COLORS } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { Button, Badge } from '../components/ds';

/**
 * Gestione IVA — Fase 1: "IVA disponibile non ancora utilizzata"
 * (SPECIFICA_IVA.md §14). Mostra le fatture di acquisto la cui IVA è stata
 * attribuita per competenza ma non ancora inserita in una liquidazione, con
 * il periodo attribuito e la regola applicata. Le liquidazioni mensili
 * persistite arrivano nelle fasi successive.
 */
const STATO_LABEL = {
  DA_INSERIRE: { label: 'Da inserire', variant: 'warning' },
  INSERITA_IN_LIQUIDAZIONE: { label: 'In liquidazione', variant: 'success' },
  DA_VERIFICARE: { label: 'Da verificare', variant: 'danger' },
  ESCLUSA: { label: 'Esclusa', variant: 'neutral' },
  RINVIATA: { label: 'Rinviata', variant: 'info' },
};

const REGOLA_LABEL = {
  STESSO_MESE: 'Stesso mese',
  ENTRO_15_MESE_SUCCESSIVO: 'Entro il 15',
  RICEVUTA_DOPO_IL_15: 'Dopo il 15',
  OPERAZIONE_ANNO_PRECEDENTE: 'Anno precedente',
  DA_VERIFICARE: '—',
};

export default function GestioneIVA() {
  const { anno } = useAnnoGlobale();
  const [dati, setDati] = useState(null);
  const [loading, setLoading] = useState(true);
  const [ricalcolo, setRicalcolo] = useState(false);
  const [msg, setMsg] = useState(null);

  const carica = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/api/iva/fatture/non-utilizzate?anno=${anno}`);
      setDati(res.data);
    } catch (e) {
      setMsg({ tipo: 'errore', testo: 'Errore: ' + (e.response?.data?.detail || e.message) });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    carica();
  }, [anno]); // eslint-disable-line react-hooks/exhaustive-deps

  const ricalcolaAttribuzione = async () => {
    setRicalcolo(true);
    setMsg(null);
    try {
      const res = await api.post(`/api/iva/ricalcola-attribuzione?anno=${anno}`);
      setMsg({
        tipo: 'ok',
        testo: `Attribuzione ricalcolata su ${res.data?.aggiornate || 0} fatture.`,
      });
      await carica();
    } catch (e) {
      setMsg({ tipo: 'errore', testo: 'Errore ricalcolo: ' + (e.response?.data?.detail || e.message) });
    } finally {
      setRicalcolo(false);
    }
  };

  const fatture = dati?.fatture || [];

  return (
    <PageLayout title="Gestione IVA" icon="📊" subtitle={`IVA disponibile non utilizzata — ${anno}`}>
      <div style={STILI.barra}>
        <div style={STILI.totale} data-testid="iva-totale-disponibile">
          <Wallet size={20} style={{ color: COLORS.primary }} />
          <div>
            <div style={{ fontSize: 12, color: COLORS.textMuted }}>IVA disponibile non utilizzata</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: COLORS.primary }}>
              {formatEuro(dati?.totale_iva_disponibile || 0)}
            </div>
          </div>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <Button variant="secondary" onClick={carica} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'spin' : ''} /> Aggiorna
          </Button>
          <Button
            variant="primary"
            onClick={ricalcolaAttribuzione}
            disabled={ricalcolo}
            data-testid="iva-ricalcola"
          >
            {ricalcolo ? 'Ricalcolo…' : 'Ricalcola attribuzione'}
          </Button>
        </div>
      </div>

      {msg && (
        <div style={{ ...STILI.msg, ...(msg.tipo === 'ok' ? STILI.msgOk : STILI.msgErr) }}>
          {msg.testo}
        </div>
      )}

      {loading ? (
        <div style={STILI.vuoto}>Caricamento…</div>
      ) : fatture.length === 0 ? (
        <div style={STILI.vuoto}>
          Nessuna IVA disponibile non utilizzata per il {anno}. Se hai appena importato
          fatture vecchie, premi «Ricalcola attribuzione».
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={STILI.tabella} data-testid="iva-tabella">
            <thead>
              <tr>
                <th style={STILI.th}>Fornitore</th>
                <th style={STILI.th}>N. fattura</th>
                <th style={STILI.th}>Data doc.</th>
                <th style={STILI.th}>Ricezione</th>
                <th style={STILI.th}>Periodo IVA</th>
                <th style={STILI.th}>Regola</th>
                <th style={{ ...STILI.th, textAlign: 'right' }}>IVA</th>
                <th style={STILI.th}>Stato</th>
              </tr>
            </thead>
            <tbody>
              {fatture.map((f, i) => {
                const st = STATO_LABEL[f.stato_detrazione_iva] || STATO_LABEL.DA_INSERIRE;
                return (
                  <tr key={f.id || i} style={{ borderTop: `1px solid ${COLORS.border}` }}>
                    <td style={STILI.td}>{f.supplier_name || '—'}</td>
                    <td style={STILI.td}>{f.invoice_number || '—'}</td>
                    <td style={STILI.td}>{formatDateIT(f.data_documento)}</td>
                    <td style={STILI.td}>{formatDateIT(f.data_ricezione)}</td>
                    <td style={STILI.td}>
                      <strong>{f.periodo_iva_attribuito || '—'}</strong>
                    </td>
                    <td style={{ ...STILI.td, fontSize: 12, color: COLORS.textMuted }}>
                      {REGOLA_LABEL[f.regola_iva_applicata] || f.regola_iva_applicata || '—'}
                    </td>
                    <td style={{ ...STILI.td, textAlign: 'right', fontWeight: 700 }}>
                      {formatEuro(f.iva_detraibile || f.iva || 0)}
                    </td>
                    <td style={STILI.td}>
                      <Badge variant={st.variant}>{st.label}</Badge>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </PageLayout>
  );
}

const STILI = {
  barra: {
    display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center',
    background: COLORS.card, border: `1px solid ${COLORS.border}`,
    borderRadius: 10, padding: 14, marginBottom: 12,
  },
  totale: { display: 'flex', alignItems: 'center', gap: 10 },
  msg: { padding: '8px 12px', borderRadius: 8, fontSize: 13, marginBottom: 12 },
  msgOk: { background: '#dcfce7', color: '#166534', border: '1px solid #86efac' },
  msgErr: { background: '#fee2e2', color: '#b91c1c', border: '1px solid #fca5a5' },
  vuoto: { padding: 32, textAlign: 'center', color: COLORS.textMuted },
  tabella: { width: '100%', borderCollapse: 'collapse', background: COLORS.card, fontSize: 13 },
  th: {
    textAlign: 'left', padding: '10px 12px', background: COLORS.bgAlt,
    color: COLORS.textMuted, fontSize: 11, textTransform: 'uppercase',
    fontWeight: 700, whiteSpace: 'nowrap',
  },
  td: { padding: '10px 12px', color: COLORS.text, whiteSpace: 'nowrap' },
};
