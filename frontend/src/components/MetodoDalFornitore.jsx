import React, { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';

import api from '../api';
import { COLORS, BORDER_RADIUS, formatDateIT, formatEuroD } from '../lib/utils';

/**
 * «Sempre per cassa dal 01/01/2025»: il metodo Cassa del fornitore vale per le
 * sue fatture dalla data «metodo valido dal». Prima si vede l'elenco (le fatture
 * che chiuderebbe, i residui, quelle che NON tocca e perche'), poi si conferma:
 * parte in background con la stessa conferma di Prima Nota Cassa. Una fattura
 * gia' pagata in banca o con assegno non si sposta mai.
 */

const btn = (primario, disabilitato) => ({
  minHeight: 44,
  padding: '8px 16px',
  fontSize: 13,
  fontWeight: 700,
  borderRadius: BORDER_RADIUS.md,
  border: `1px solid ${primario ? COLORS.primary : COLORS.border}`,
  background: primario ? COLORS.primary : COLORS.card,
  color: primario ? '#fff' : COLORS.text,
  opacity: disabilitato ? 0.5 : 1,
  cursor: disabilitato ? 'not-allowed' : 'pointer',
});

function Elenco({ titolo, righe, mostraMotivo, mostraResiduo }) {
  if (!righe?.length) return null;
  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ fontSize: 12.5, fontWeight: 800, color: COLORS.text }}>
        {titolo} ({righe.length})
      </div>
      <ul style={{ listStyle: 'none', margin: '6px 0 0', padding: 0 }}>
        {righe.map(r => (
          <li
            key={r.id}
            style={{
              padding: '6px 8px',
              marginBottom: 4,
              borderRadius: BORDER_RADIUS.md,
              background: COLORS.bgAlt,
              border: `1px solid ${COLORS.border}`,
              fontSize: 12.5,
              display: 'flex',
              flexWrap: 'wrap',
              gap: '2px 10px',
            }}
          >
            <b>{r.numero || r.id}</b>
            <span>{formatDateIT(r.data)}</span>
            <span style={{ fontVariantNumeric: 'tabular-nums' }}>
              {formatEuroD(mostraResiduo ? r.residuo : r.importo)}
            </span>
            {mostraMotivo && r.motivo && (
              <span style={{ color: COLORS.textMuted, flexBasis: '100%' }}>{r.motivo}</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function MetodoDalFornitore({ fornitore, id, onChiudi, onFatto }) {
  const [piano, setPiano] = useState(null);
  const [errore, setErrore] = useState('');
  const [stato, setStato] = useState(null); // null | in_corso | completato | errore
  const [esito, setEsito] = useState(null);
  const timer = useRef(null);
  const base = `/api/suppliers/${encodeURIComponent(id)}/applica-metodo-dal`;
  const nome = fornitore.ragione_sociale || fornitore.denominazione || fornitore.nome || 'Fornitore';

  useEffect(() => {
    let vivo = true;
    api
      .post(base, null, { params: { dry_run: true } })
      .then(r => vivo && setPiano(r.data))
      .catch(e => vivo && setErrore(e.response?.data?.detail || e.message));
    return () => {
      vivo = false;
      clearTimeout(timer.current);
    };
  }, [base]);

  const attendi = () => {
    timer.current = setTimeout(async () => {
      try {
        const { data } = await api.get(`${base}/stato`);
        if (data.stato === 'completato' || data.stato === 'errore') {
          setStato(data.stato);
          setEsito(data);
          if (data.stato === 'completato') {
            toast.success(`${data.registrate || 0} fatture registrate in Cassa`);
            onFatto?.();
          }
          return;
        }
      } catch (e) {
        setErrore(e.response?.data?.detail || e.message);
        return;
      }
      attendi();
    }, 1500);
  };

  const applica = async () => {
    setErrore('');
    try {
      await api.post(base, null, { params: { dry_run: false } });
      setStato('in_corso');
      attendi();
    } catch (e) {
      setErrore(e.response?.data?.detail || e.message);
    }
  };

  const daChiudere = piano?.da_chiudere_in_cassa || [];

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Cassa dal ${formatDateIT(piano?.dal || fornitore.metodo_pagamento_dal)} per ${nome}`}
      onMouseDown={e => e.target === e.currentTarget && onChiudi()}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1200,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
        background: 'rgba(20, 20, 19, 0.52)',
      }}
    >
      <div
        style={{
          width: 'min(560px, 100%)',
          maxHeight: '92vh',
          overflowY: 'auto',
          background: COLORS.card,
          borderRadius: 12,
          padding: 18,
          border: `1px solid ${COLORS.border}`,
          boxShadow: '0 24px 70px rgba(20, 20, 19, 0.28)',
          textAlign: 'left',
        }}
      >
        <div style={{ fontWeight: 800, fontSize: 16, color: COLORS.text }}>
          Cassa dal {formatDateIT(piano?.dal || fornitore.metodo_pagamento_dal)}
        </div>
        <div style={{ color: COLORS.textMuted, fontSize: 13, marginTop: 4 }}>{nome}</div>

        {!piano && !errore && (
          <div style={{ marginTop: 14, fontSize: 13, color: COLORS.textMuted }}>
            Controllo le fatture…
          </div>
        )}

        {piano && (
          <>
            <div style={{ marginTop: 12, fontSize: 13, color: COLORS.text }}>
              {piano.fatture_dal} fatture dal {formatDateIT(piano.dal)}.{' '}
              {daChiudere.length > 0 ? (
                <>
                  <b>{daChiudere.length}</b> da registrare in Cassa per{' '}
                  <b>{formatEuroD(piano.residuo_da_chiudere)}</b>.
                </>
              ) : (
                'Niente da registrare in Cassa.'
              )}
            </div>
            <Elenco titolo="Da registrare in Cassa" righe={daChiudere} mostraResiduo />
            <Elenco
              titolo="Pagate in banca o con assegno: non si toccano"
              righe={piano.conflitto_banca_o_assegno}
              mostraMotivo
            />
            <Elenco titolo="Non forzate" righe={piano.non_forzate} mostraMotivo />
            <Elenco
              titolo="Segnate pagate ma senza riga di Prima Nota"
              righe={piano.pagate_senza_riga}
              mostraMotivo
            />
            <div style={{ marginTop: 10, fontSize: 12, color: COLORS.textMuted }}>
              Già in Cassa: {(piano.gia_in_cassa || []).length}.
            </div>
          </>
        )}

        {stato === 'in_corso' && (
          <div role="status" style={{ marginTop: 12, fontSize: 13, color: COLORS.text }}>
            Registro in Cassa… puoi chiudere: il lavoro prosegue in sottofondo.
          </div>
        )}
        {stato === 'completato' && esito && (
          <div role="status" style={{ marginTop: 12, fontSize: 13, color: COLORS.success }}>
            Registrate {esito.registrate || 0}, scartate {esito.scartate || 0}.
          </div>
        )}
        {stato === 'errore' && esito && (
          <div role="alert" style={{ marginTop: 12, fontSize: 13, color: COLORS.danger }}>
            Giro fallito: {esito.errore}
          </div>
        )}
        {errore && (
          <div role="alert" style={{ color: COLORS.danger, marginTop: 10, fontSize: 13 }}>
            {errore}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 18 }}>
          <button type="button" onClick={onChiudi} style={btn(false, false)}>
            Chiudi
          </button>
          {piano && daChiudere.length > 0 && !stato && (
            <button type="button" onClick={applica} style={btn(true, false)}>
              Registra {daChiudere.length} in Cassa
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
