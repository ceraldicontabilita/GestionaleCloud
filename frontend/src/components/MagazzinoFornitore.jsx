import React, { useEffect, useState } from 'react';
import { Package, PackageX } from 'lucide-react';
import { toast } from 'sonner';

import api from '../api';
import { COLORS, BORDER_RADIUS, formatDateIT } from '../lib/utils';

/**
 * Nel magazzino / fuori dal magazzino: un controllo a un tocco sulla scheda del
 * fornitore. Il tocco non salva subito: apre l'anteprima con i numeri veri
 * (fatture, lotti, fatture da prendere), chiede il motivo con dei chip (mani
 * sporche: «Altro» e' l'eccezione) e solo alla conferma scrive, con data e chi
 * l'ha deciso. Non cancella niente: le fatture restano contabili.
 */

export const ORIGINI = {
  erp: '',
  lotti: 'decisione presa in Lotti',
  non_deciso: 'nessuna scelta: entra in magazzino',
};

export function descriviDecisione(fornitore) {
  const escluso = !!fornitore?.esclude_magazzino;
  const parti = [];
  if (fornitore?.magazzino_deciso_il) {
    parti.push(`dal ${formatDateIT(fornitore.magazzino_deciso_il)}`);
  }
  if (fornitore?.magazzino_motivo_testo) parti.push(fornitore.magazzino_motivo_testo);
  if (fornitore?.magazzino_deciso_da) parti.push(fornitore.magazzino_deciso_da);
  const origine = ORIGINI[fornitore?.magazzino_origine] || '';
  if (origine) parti.push(origine);
  return { escluso, testo: parti.join(' · ') };
}

const chipStile = attivo => ({
  minHeight: 44,
  padding: '8px 14px',
  fontSize: 13,
  fontWeight: 700,
  cursor: 'pointer',
  borderRadius: BORDER_RADIUS.md,
  border: `1px solid ${attivo ? COLORS.primary : COLORS.border}`,
  background: attivo ? COLORS.primary : COLORS.card,
  color: attivo ? '#fff' : COLORS.text,
});

function Numero({ etichetta, valore }) {
  return (
    <div
      style={{
        flex: '1 1 110px',
        padding: '8px 10px',
        borderRadius: BORDER_RADIUS.md,
        background: COLORS.bgAlt,
        border: `1px solid ${COLORS.border}`,
      }}
    >
      <div style={{ fontSize: 18, fontWeight: 800, color: COLORS.text }}>{valore}</div>
      <div style={{ fontSize: 11, color: COLORS.textMuted }}>{etichetta}</div>
    </div>
  );
}

export function MagazzinoDialog({ fornitore, escludi, id, onChiudi, onFatto }) {
  const [anteprima, setAnteprima] = useState(null);
  const [errore, setErrore] = useState('');
  const [motivo, setMotivo] = useState('');
  const [testo, setTesto] = useState('');
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    let vivo = true;
    api
      .get(`/api/suppliers/${encodeURIComponent(id)}/magazzino/anteprima`, { params: { escludi } })
      .then(r => vivo && setAnteprima(r.data))
      .catch(e => vivo && setErrore(e.response?.data?.detail || e.message));
    return () => {
      vivo = false;
    };
  }, [id, escludi]);

  const nome = fornitore.ragione_sociale || fornitore.denominazione || fornitore.nome || 'Fornitore';
  const pronto = motivo && (motivo !== 'altro' || testo.trim());

  const conferma = async () => {
    setSalvando(true);
    setErrore('');
    try {
      const { data } = await api.put(`/api/suppliers/${encodeURIComponent(id)}/magazzino`, {
        escludi,
        motivo,
        motivo_testo: motivo === 'altro' ? testo.trim() : '',
      });
      const accodate = data.fatture_accodate_a_lotti || 0;
      toast.success(
        escludi
          ? `${nome}: fuori dal magazzino. Le fatture restano contabili.`
          : `${nome}: nel magazzino${accodate ? `, ${accodate} fatture in arrivo in Lotti` : ''}.`
      );
      onFatto?.(data.supplier);
      onChiudi();
    } catch (e) {
      setErrore(e.response?.data?.detail || e.message);
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={escludi ? `Escludi ${nome} dal magazzino` : `Rimetti ${nome} nel magazzino`}
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
          width: 'min(520px, 100%)',
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
          {escludi ? 'Fuori dal magazzino' : 'Nel magazzino'}
        </div>
        <div style={{ color: COLORS.textMuted, fontSize: 13, marginTop: 4 }}>{nome}</div>

        {!anteprima && !errore && (
          <div style={{ marginTop: 14, fontSize: 13, color: COLORS.textMuted }}>
            Conto fatture e lotti…
          </div>
        )}

        {anteprima && (
          <>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 14 }}>
              <Numero etichetta="fatture contabili" valore={anteprima.fatture_contabili} />
              <Numero etichetta="fatture in Lotti" valore={anteprima.fatture_in_lotti} />
              <Numero
                etichetta="lotti creati"
                valore={`${anteprima.lotti_creati} (${anteprima.lotti_con_giacenza} con giacenza)`}
              />
              {!escludi && (
                <Numero etichetta="fatture da prendere" valore={anteprima.fatture_da_prendere} />
              )}
            </div>
            <ul style={{ margin: '12px 0 0', paddingLeft: 18, fontSize: 13, color: COLORS.text }}>
              {(anteprima.effetto || []).map(riga => (
                <li key={riga} style={{ marginBottom: 4 }}>
                  {riga}
                </li>
              ))}
            </ul>
            {anteprima.gia_cosi && (
              <div style={{ marginTop: 10, fontSize: 12.5, color: COLORS.warning }}>
                Il fornitore è già in questo stato: confermando si aggiorna solo il motivo.
              </div>
            )}

            <div
              style={{ marginTop: 16, fontSize: 12.5, fontWeight: 700, color: COLORS.textMuted }}
            >
              Perché?
            </div>
            <div
              role="radiogroup"
              aria-label="Motivo"
              style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 6 }}
            >
              {(anteprima.motivi || []).map(m => (
                <button
                  key={m.id}
                  type="button"
                  role="radio"
                  aria-checked={motivo === m.id}
                  onClick={() => setMotivo(m.id)}
                  style={chipStile(motivo === m.id)}
                  data-testid={`motivo-${m.id}`}
                >
                  {m.etichetta}
                </button>
              ))}
            </div>
            {motivo === 'altro' && (
              <input
                type="text"
                value={testo}
                maxLength={200}
                onChange={e => setTesto(e.target.value)}
                aria-label="Scrivi il motivo"
                placeholder="Scrivi il motivo"
                style={{
                  marginTop: 10,
                  minHeight: 44,
                  width: '100%',
                  boxSizing: 'border-box',
                  padding: '6px 10px',
                  fontSize: 14,
                  border: `1px solid ${COLORS.border}`,
                  borderRadius: BORDER_RADIUS.md,
                }}
              />
            )}
          </>
        )}

        {errore && (
          <div role="alert" style={{ color: COLORS.danger, marginTop: 10, fontSize: 13 }}>
            {errore}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 18 }}>
          <button type="button" onClick={onChiudi} style={{ ...chipStile(false), minWidth: 90 }}>
            Annulla
          </button>
          <button
            type="button"
            onClick={conferma}
            disabled={!anteprima || !pronto || salvando}
            style={{
              ...chipStile(true),
              minWidth: 120,
              opacity: !anteprima || !pronto || salvando ? 0.5 : 1,
              cursor: !anteprima || !pronto || salvando ? 'not-allowed' : 'pointer',
            }}
          >
            {salvando ? 'Salvo…' : escludi ? 'Escludi' : 'Includi'}
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Due bottoni affiancati, quello attivo pieno. Toccare l'altro apre l'anteprima.
 * `onFatto(fornitoreAggiornato)` riporta lo stato nuovo alla lista.
 */
export default function MagazzinoFornitore({ fornitore, id, onFatto, compatto = false }) {
  const [dialogo, setDialogo] = useState(null); // true = escludere, false = includere
  const { escluso, testo } = descriviDecisione(fornitore);

  const voce = (attiva, icona, etichetta, escludi) => (
    <button
      type="button"
      role="radio"
      aria-checked={attiva}
      onClick={() => !attiva && setDialogo(escludi)}
      data-testid={`magazzino-${escludi ? 'fuori' : 'dentro'}-${id}`}
      style={{
        ...chipStile(attiva),
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        minHeight: compatto ? 40 : 44,
        padding: compatto ? '6px 10px' : '8px 14px',
        cursor: attiva ? 'default' : 'pointer',
      }}
    >
      {icona}
      {etichetta}
    </button>
  );

  return (
    <div data-testid={`magazzino-${id}`} style={{ minWidth: 0 }}>
      <div role="radiogroup" aria-label="Magazzino" style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {voce(!escluso, <Package size={15} aria-hidden="true" />, 'Nel magazzino', false)}
        {voce(escluso, <PackageX size={15} aria-hidden="true" />, 'Fuori dal magazzino', true)}
      </div>
      {testo && (
        <div style={{ marginTop: 4, fontSize: 11.5, color: COLORS.textMuted, overflowWrap: 'anywhere' }}>
          {testo}
        </div>
      )}
      {dialogo !== null && (
        <MagazzinoDialog
          fornitore={fornitore}
          escludi={dialogo}
          id={id}
          onChiudi={() => setDialogo(null)}
          onFatto={onFatto}
        />
      )}
    </div>
  );
}
