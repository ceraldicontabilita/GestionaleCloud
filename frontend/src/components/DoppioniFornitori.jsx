import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { ChevronDown, ChevronUp, GitMerge } from 'lucide-react';

import api from '../api';
import { COLORS, BORDER_RADIUS } from '../lib/utils';
import { useConfirm } from './ui/ConfirmDialog';

/**
 * «Possibili doppioni da decidere»: i fornitori che il giro automatico NON fonde
 * (nome solo simile, piu' candidati, due senza P.IVA, stesso codice fiscale con
 * P.IVA diverse). Il giro delle 06:20 fonde da solo solo i certi (stessa P.IVA) e
 * i probabili con un solo candidato; qui la scelta e' del titolare. Un'unione non
 * cancella niente: il fornitore scartato resta, marcato «unificato».
 */

const btn = disabilitato => ({
  minHeight: 44,
  padding: '8px 14px',
  fontSize: 13,
  fontWeight: 700,
  borderRadius: BORDER_RADIUS.md,
  border: `1px solid ${COLORS.primary}`,
  background: COLORS.card,
  color: COLORS.primary,
  opacity: disabilitato ? 0.5 : 1,
  cursor: disabilitato ? 'not-allowed' : 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
});

export default function DoppioniFornitori({ onMerged }) {
  const confirm = useConfirm();
  const [dati, setDati] = useState(null);
  const [aperto, setAperto] = useState(false);
  const [occupato, setOccupato] = useState(false);

  const carica = useCallback(async () => {
    try {
      const res = await api.get('/api/suppliers/duplicati/da-decidere');
      setDati(res.data);
    } catch {
      // Elenco riservato al titolare: senza permesso la scheda non compare.
      setDati(null);
    }
  }, []);

  useEffect(() => {
    carica();
  }, [carica]);

  if (!dati) return null;

  const tieni = async (gruppo, vincente) => {
    const altri = gruppo.fornitori.filter(f => String(f.id) !== String(vincente.id));
    const ok = await confirm({
      title: 'Unisci fornitori',
      message: `Tenere «${vincente.nome}» e unire in lui ${altri.map(f => `«${f.nome}»`).join(', ')}? Fatture, scadenze e movimenti passano a «${vincente.nome}»; gli altri restano in archivio come «unificato».`,
      confirmText: 'Unisci',
      cancelText: 'Annulla',
    });
    if (ok === false) return;
    setOccupato(true);
    try {
      for (const perdente of altri) {
        await api.post('/api/suppliers/duplicati/merge', {
          target_id: String(vincente.id),
          duplicate_id: String(perdente.id),
        });
      }
      toast.success('Fornitori uniti');
      if (onMerged) onMerged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Unione non riuscita');
    } finally {
      await carica();
      setOccupato(false);
    }
  };

  return (
    <section
      data-testid="doppioni-fornitori"
      style={{
        marginBottom: 14,
        background: COLORS.card,
        border: `1px solid ${COLORS.border}`,
        borderRadius: BORDER_RADIUS.lg,
      }}
    >
      <button
        type="button"
        onClick={() => setAperto(v => !v)}
        aria-expanded={aperto}
        data-testid="doppioni-fornitori-toggle"
        style={{
          width: '100%',
          minHeight: 44,
          padding: '10px 14px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 8,
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          color: COLORS.text,
          fontSize: 13.5,
          fontWeight: 700,
          textAlign: 'left',
        }}
      >
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
          <GitMerge size={16} color={dati.count > 0 ? COLORS.primary : COLORS.textSubtle} />
          Possibili doppioni da decidere ({dati.count})
        </span>
        {aperto ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </button>
      {aperto && (
        <div style={{ padding: '0 14px 14px' }}>
          {dati.count === 0 && (
            <div style={{ fontSize: 13, color: COLORS.textMuted }}>
              Nessun doppione da decidere. I certi (stessa P.IVA) li unisce da solo il giro delle 06:20.
            </div>
          )}
          {dati.gruppi.map((g, n) => (
            <div
              key={n}
              data-testid="doppione-gruppo"
              style={{
                marginTop: 10,
                padding: 10,
                borderRadius: BORDER_RADIUS.md,
                background: COLORS.bgAlt,
                border: `1px solid ${COLORS.border}`,
              }}
            >
              <div style={{ fontSize: 12.5, color: COLORS.textMuted, marginBottom: 6 }}>{g.motivo}</div>
              {g.fornitori.map(f => (
                <div
                  key={String(f.id)}
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '6px 10px',
                    padding: '6px 0',
                    borderTop: `1px solid ${COLORS.border}`,
                  }}
                >
                  <div style={{ minWidth: 0, overflowWrap: 'anywhere', fontSize: 13 }}>
                    <strong>{f.nome || 'Senza nome'}</strong>
                    <div style={{ fontSize: 12, color: COLORS.textMuted }}>
                      P.IVA <span style={{ fontFamily: 'monospace' }}>{f.partita_iva || 'non disponibile'}</span>
                      {f.codice_fiscale ? ` · CF ${f.codice_fiscale}` : ''} · {f.usi} documenti collegati
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={occupato}
                    onClick={() => tieni(g, f)}
                    style={btn(occupato)}
                    title={`Tieni «${f.nome}» e unisci gli altri in lui`}
                  >
                    Tieni questo
                  </button>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
