import React, { useEffect, useState } from 'react';

import api from '../api';
import { COLORS, BORDER_RADIUS, formatEuro, formatDateIT } from '../lib/utils';

/**
 * «Segna le rate passate come pagate»: il titolare dichiara pagate le rate
 * scadute di un mutuo che non hanno la prova della banca (estratti non
 * disponibili). Anteprima sempre prima (`dry_run`), poi conferma forte con la
 * frase che il backend ha restituito. Una rata provata da banca, quietanza o
 * estratto annuale non si tocca; una prova arrivata dopo sostituisce la
 * dichiarazione. Non scrive in Prima Nota ne' nel giornale.
 * La stessa finestra ritira la dichiarazione (`ritira`).
 */
const MOTIVI = [
  { value: 'estratti_precedenti_non_disponibili', label: 'Estratti precedenti non disponibili' },
  { value: 'pagate_da_altro_conto', label: 'Pagate da un altro conto' },
  { value: 'altro', label: 'Altro (scrivi tu)' },
];
const MOTIVI_RITIRO = [
  { value: 'dichiarazione_errata', label: 'Dichiarazione errata' },
  { value: 'rate_non_pagate', label: 'Le rate non risultano pagate' },
  { value: 'altro', label: 'Altro (scrivi tu)' },
];

const centi = c => formatEuro((Number(c) || 0) / 100);
const erroreApi = e => {
  const d = e.response?.data?.detail;
  return (d && (d.message || (typeof d === 'string' ? d : ''))) || e.message;
};

function Chip({ attivo, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={attivo}
      style={{
        minHeight: 44, padding: '8px 14px', borderRadius: BORDER_RADIUS.full, fontWeight: 700,
        fontSize: 13, cursor: 'pointer',
        border: `1px solid ${attivo ? COLORS.primary : COLORS.border}`,
        background: attivo ? COLORS.primarySoft : COLORS.card,
        color: attivo ? COLORS.primary : COLORS.text,
      }}
    >
      {children}
    </button>
  );
}

export default function DichiaraRateMutuo({ mutuo, ritira = false, onChiudi, onFatto }) {
  const [motivo, setMotivo] = useState(ritira ? 'dichiarazione_errata' : 'estratti_precedenti_non_disponibili');
  const [motivoAltro, setMotivoAltro] = useState('');
  const [dataLimite, setDataLimite] = useState('');
  const [anteprima, setAnteprima] = useState(null);
  const [caricamento, setCaricamento] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [errore, setErrore] = useState('');

  const percorso = `/api/mutui/${mutuo.mutuo_id}/rate-dichiarate${ritira ? '/ritira' : ''}`;
  const corpo = extra => ({
    motivo,
    motivo_altro: motivo === 'altro' ? motivoAltro : null,
    ...(ritira ? {} : { data_limite: dataLimite || null }),
    ...extra,
  });

  useEffect(() => {
    let vivo = true;
    setAnteprima(null);
    setErrore('');
    if (motivo === 'altro' && !motivoAltro.trim()) return undefined;
    setCaricamento(true);
    api.post(percorso, corpo({ dry_run: true }))
      .then(r => vivo && setAnteprima(r.data.data))
      .catch(e => vivo && setErrore(erroreApi(e)))
      .finally(() => vivo && setCaricamento(false));
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataLimite, motivo, motivoAltro, mutuo.mutuo_id]);

  const conferma = async () => {
    setSalvando(true);
    setErrore('');
    try {
      const { data } = await api.post(percorso, corpo({ dry_run: false, conferma: anteprima.frase_conferma }));
      await onFatto?.(data.data);
      onChiudi?.();
    } catch (e) {
      setErrore(erroreApi(e));
    } finally {
      setSalvando(false);
    }
  };

  const n = anteprima?.numero_rate || 0;
  const provate = anteprima?.gia_provate?.length || 0;
  const elenco = ritira ? MOTIVI_RITIRO : MOTIVI;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={ritira ? 'Ritira la dichiarazione delle rate' : 'Segna le rate passate come pagate'}
      data-testid="dichiara-rate-modal"
      onMouseDown={e => e.target === e.currentTarget && onChiudi?.()}
      style={{
        position: 'fixed', inset: 0, zIndex: 1200, display: 'flex', alignItems: 'center',
        justifyContent: 'center', padding: 16, background: 'rgba(20, 20, 19, 0.52)',
      }}
    >
      <div style={{
        width: 'min(520px, 100%)', maxHeight: '92vh', overflowY: 'auto', background: COLORS.card,
        borderRadius: 12, padding: 18, border: `1px solid ${COLORS.border}`, textAlign: 'left',
        boxShadow: '0 24px 70px rgba(20, 20, 19, 0.28)',
      }}>
        <div style={{ fontWeight: 800, fontSize: 16, color: COLORS.text }}>
          {ritira ? 'Ritira la dichiarazione' : 'Segna le rate passate come pagate'}
        </div>
        <div style={{ color: COLORS.textMuted, fontSize: 13, marginTop: 6 }}>
          {mutuo.tipo_finanziamento} · Delibera {mutuo.numero_delibera}
        </div>
        {!ritira && (
          <div style={{ color: COLORS.textMuted, fontSize: 13, marginTop: 8 }}>
            È una tua dichiarazione, non una prova della banca: resta distinta, non tocca le rate già
            provate e non scrive in Prima Nota. Se arriva l&apos;estratto conto, vince l&apos;estratto.
          </div>
        )}

        <div style={{ fontSize: 12.5, fontWeight: 700, color: COLORS.textMuted, marginTop: 14 }}>Motivo</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 6 }}>
          {elenco.map(m => (
            <Chip key={m.value} attivo={motivo === m.value} onClick={() => setMotivo(m.value)}>{m.label}</Chip>
          ))}
        </div>
        {motivo === 'altro' && (
          <input
            type="text"
            value={motivoAltro}
            onChange={e => setMotivoAltro(e.target.value)}
            aria-label="Motivo, scrivi tu"
            maxLength={300}
            style={{
              display: 'block', marginTop: 8, minHeight: 44, width: '100%', padding: '6px 10px',
              fontSize: 14, border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.md,
            }}
          />
        )}

        {!ritira && (
          <label style={{ display: 'block', marginTop: 14, fontSize: 12.5, fontWeight: 700, color: COLORS.textMuted }}>
            Fino alla scadenza del (vuoto = tutte le rate già scadute)
            <input
              type="date"
              value={dataLimite}
              onChange={e => setDataLimite(e.target.value)}
              style={{
                display: 'block', marginTop: 6, minHeight: 44, width: '100%', padding: '6px 10px',
                fontSize: 14, border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.md,
              }}
            />
          </label>
        )}

        <div
          data-testid="dichiara-rate-anteprima"
          style={{
            marginTop: 14, padding: 12, borderRadius: BORDER_RADIUS.md, background: COLORS.bgAlt,
            border: `1px solid ${COLORS.border}`, fontSize: 13, color: COLORS.text,
          }}
        >
          {caricamento && <span>Calcolo l&apos;anteprima…</span>}
          {!caricamento && anteprima && (
            <>
              <div style={{ fontWeight: 800 }}>
                {n === 0
                  ? (ritira ? 'Nessuna dichiarazione attiva da ritirare.' : 'Nessuna rata da dichiarare.')
                  : `${n} ${n === 1 ? 'rata' : 'rate'} · ${centi(anteprima.totale_cents)}`}
              </div>
              {n > 0 && !ritira && (
                <div style={{ color: COLORS.textMuted, marginTop: 4 }}>
                  Dal {formatDateIT(anteprima.prima_scadenza)} al {formatDateIT(anteprima.ultima_scadenza)}
                  {anteprima.di_cui_anno_attivo > 0 && ` · ${anteprima.di_cui_anno_attivo} dell'anno attivo`}
                </div>
              )}
              {!ritira && (
                <div style={{ color: COLORS.textMuted, marginTop: 4 }}>
                  {provate} già provate (banca, quietanza o estratto annuale), non si toccano
                  {anteprima.gia_pagate_sul_piano?.length > 0 && ` · ${anteprima.gia_pagate_sul_piano.length} già pagate sul piano`}
                  {anteprima.future_escluse?.length > 0 && ` · ${anteprima.future_escluse.length} future escluse`}
                </div>
              )}
              {!ritira && anteprima.nota_data_limite && (
                <div style={{ color: COLORS.warning, marginTop: 4 }}>{anteprima.nota_data_limite}</div>
              )}
            </>
          )}
        </div>
        {errore && <div role="alert" style={{ color: COLORS.danger, marginTop: 10, fontSize: 13 }}>{errore}</div>}

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 16, flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={onChiudi}
            style={{
              minHeight: 44, padding: '8px 14px', borderRadius: 8, fontWeight: 700,
              border: `1px solid ${COLORS.border}`, background: COLORS.card, cursor: 'pointer',
            }}
          >
            Annulla
          </button>
          <button
            type="button"
            onClick={conferma}
            disabled={salvando || caricamento || n === 0 || !anteprima?.frase_conferma}
            data-testid="dichiara-rate-conferma"
            style={{
              minHeight: 44, padding: '8px 14px', borderRadius: 8, fontWeight: 800, border: 0,
              background: COLORS.primary, color: 'white', cursor: salvando ? 'wait' : 'pointer',
              opacity: salvando || caricamento || n === 0 ? 0.5 : 1,
            }}
          >
            {salvando
              ? 'Salvo…'
              : ritira
                ? `Sì, ritiro ${n} ${n === 1 ? 'dichiarazione' : 'dichiarazioni'}`
                : `Sì, dichiaro pagate ${n} ${n === 1 ? 'rata' : 'rate'}`}
          </button>
        </div>
      </div>
    </div>
  );
}
