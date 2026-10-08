import React, { useState } from 'react';
import { Check } from 'lucide-react';
import api from '../api';
import { COLORS, formatEuro, formatDateIT } from '../lib/utils';

/**
 * «Conferma questo addebito» su un riscontro PROBABILE o PARZIALE.
 *
 * Il motore a livelli (`f24_controllo_incrociato`) scrive da solo solo il
 * CERTO; qui il titolare sceglie fra i candidati che il motore ha proposto e
 * dice il perche' da una tendina a chip (mai testo libero: «Altro» e'
 * l'eccezione). La scrittura e' la stessa del CERTO, sul backend
 * (`POST /api/f24-riconciliazione/quietanze-banca/{f24_id}/conferma`).
 *
 * - `f24Id`: id del modello o della quietanza (la scheda e' una sola);
 * - `livello`: PROBABILE | PARZIALE (altrove il bottone non compare);
 * - `candidati`: gli addebiti proposti dal motore (`movimento_id`, data, importo);
 * - `motivi`: la tendina letta dal backend (`conferma.motivi`), chiave -> testo;
 * - `onConfermato`: ricarica la lista dopo la scrittura.
 */

export const LIVELLI_CONFERMABILI = ['PROBABILE', 'PARZIALE'];

const stileChip = attivo => ({
  minHeight: 44,
  padding: '8px 14px',
  borderRadius: 999,
  border: `1px solid ${attivo ? COLORS.primary : COLORS.border}`,
  background: attivo ? COLORS.primarySoft : COLORS.card,
  color: attivo ? COLORS.primary : COLORS.text,
  fontWeight: 600,
  fontSize: 13,
  cursor: 'pointer',
  textAlign: 'left',
});

const stileAzione = {
  display: 'inline-flex', alignItems: 'center', gap: 6, minHeight: 44, padding: '8px 14px',
  borderRadius: 10, border: `1px solid ${COLORS.primary}`, background: COLORS.primary, color: '#fff',
  fontWeight: 700, fontSize: 13, cursor: 'pointer',
};

export default function ConfermaAddebitoF24({ f24Id, livello, candidati = [], motivi = {}, onConfermato }) {
  const [aperto, setAperto] = useState(false);
  const [movimentoId, setMovimentoId] = useState(candidati.length === 1 ? candidati[0].movimento_id : '');
  const [motivo, setMotivo] = useState('');
  const [motivoTesto, setMotivoTesto] = useState('');
  const [errore, setErrore] = useState('');
  const [inCorso, setInCorso] = useState(false);

  if (!f24Id || !LIVELLI_CONFERMABILI.includes(livello) || candidati.length === 0) return null;
  const chiaviMotivi = Object.keys(motivi);
  const pronto = movimentoId && motivo && (motivo !== 'altro' || motivoTesto.trim().length >= 3);

  const conferma = async () => {
    setInCorso(true);
    setErrore('');
    try {
      await api.post(`/api/f24-riconciliazione/quietanze-banca/${encodeURIComponent(f24Id)}/conferma`, {
        movimento_id: movimentoId, motivo, motivo_testo: motivo === 'altro' ? motivoTesto.trim() : undefined,
      });
      setAperto(false);
      if (onConfermato) onConfermato();
    } catch (e) {
      const corpo = e.response?.data || {};
      setErrore(corpo.message || corpo.detail || e.message || 'Conferma non riuscita');
    } finally {
      setInCorso(false);
    }
  };

  if (!aperto) {
    return (
      <button
        type="button"
        style={{ ...stileAzione, background: COLORS.card, color: COLORS.primary }}
        onClick={() => setAperto(true)}
        data-testid={`conferma-addebito-${f24Id}`}
      >
        <Check size={14} aria-hidden="true" /> Conferma questo addebito
      </button>
    );
  }

  return (
    <div
      data-testid={`conferma-addebito-form-${f24Id}`}
      style={{ display: 'grid', gap: 10, padding: 12, border: `1px solid ${COLORS.border}`, borderRadius: 10,
        background: COLORS.card, maxWidth: 560 }}
    >
      <div style={{ fontSize: 13, fontWeight: 700 }}>
        Conferma dell'addebito ({livello === 'PARZIALE' ? 'parziale: la differenza resta scritta, nessun conguaglio' : 'probabile'})
      </div>
      {candidati.length > 1 && (
        <div style={{ display: 'grid', gap: 6 }}>
          <span style={{ fontSize: 12.5, color: COLORS.textMuted }}>Quale addebito?</span>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {candidati.map(a => (
              <button
                key={a.movimento_id}
                type="button"
                style={stileChip(movimentoId === a.movimento_id)}
                onClick={() => setMovimentoId(a.movimento_id)}
                data-testid={`candidato-${a.movimento_id}`}
              >
                {formatDateIT(a.data)} · {formatEuro(a.importo)}
              </button>
            ))}
          </div>
        </div>
      )}
      <div style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12.5, color: COLORS.textMuted }}>Perché?</span>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {chiaviMotivi.map(k => (
            <button
              key={k}
              type="button"
              style={stileChip(motivo === k)}
              onClick={() => setMotivo(k)}
              data-testid={`motivo-${k}`}
            >
              {motivi[k]}
            </button>
          ))}
        </div>
        {motivo === 'altro' && (
          <label style={{ display: 'grid', gap: 4, fontSize: 12.5 }}>
            Scrivi il motivo
            <input
              value={motivoTesto}
              onChange={e => setMotivoTesto(e.target.value)}
              maxLength={200}
              style={{ minHeight: 44, padding: '8px 10px', borderRadius: 8, border: `1px solid ${COLORS.border}`, fontSize: 14 }}
              data-testid={`motivo-testo-${f24Id}`}
            />
          </label>
        )}
      </div>
      {errore && (
        <div role="alert" style={{ color: COLORS.danger, fontWeight: 600, fontSize: 13 }}>{errore}</div>
      )}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button
          type="button"
          style={{ ...stileAzione, opacity: pronto && !inCorso ? 1 : 0.5 }}
          disabled={!pronto || inCorso}
          onClick={conferma}
          data-testid={`conferma-invia-${f24Id}`}
        >
          <Check size={14} aria-hidden="true" /> {inCorso ? 'Scrivo…' : 'Conferma'}
        </button>
        <button type="button" style={stileChip(false)} onClick={() => setAperto(false)}>
          Annulla
        </button>
      </div>
    </div>
  );
}
