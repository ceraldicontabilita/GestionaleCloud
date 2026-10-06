import React, { useCallback, useEffect, useState } from 'react';
import { Landmark, Link2, RefreshCw } from 'lucide-react';
import api, { messaggioErrore } from '../api';
import { COLORS } from '../lib/utils';
import { useConfirm } from './ui/ConfirmDialog';
import { dataOra, giorno } from './AggiornamentoDati';

/**
 * Banco BPM letto direttamente dalla banca (Enable Banking), in Prima Nota › Banca.
 *
 * I movimenti certamente nuovi entrano da soli due volte al giorno (07:15 e
 * 09:00, scheduler); «Aggiorna ora» fa lo stesso giro subito, dopo aver
 * mostrato quanti sono. Finiscono nell'archivio estratti conto, mai
 * direttamente in Prima Nota: da li' li prendono riconciliazione e Prima Nota
 * Banca come per il CSV. I DA_VERIFICARE restano fuori.
 */
export default function BancaDiretta() {
  const confirm = useConfirm();
  const [stato, setStato] = useState(null);
  const [lavoro, setLavoro] = useState(false);
  const [msg, setMsg] = useState(null);
  const [esito, setEsito] = useState(null);

  const carica = useCallback(async () => {
    try {
      const res = await api.get('/api/banca/enable-banking/stato', { timeout: 15000 });
      setStato(res.data);
    } catch (e) {
      // Riservato all'amministratore (lo decide il backend): per gli altri
      // ruoli il riquadro semplicemente non c'e'.
      const codice = e?.response?.status;
      if (codice === 401 || codice === 403) setStato({ nascosto: true });
      else setStato({ errore: messaggioErrore(e, 'Stato della banca non leggibile') });
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  if (!stato || stato.nascosto) return null;
  if (stato.errore) {
    return <div style={S.box} data-testid="banca-diretta"><div style={S.errore} role="alert">{stato.errore}</div></div>;
  }
  // Lettura diretta spenta su Render: il riquadro resta e dice perche' (prima spariva
  // e nessuno capiva dove fosse «Aggiorna ora»).
  if (!stato.attivo) {
    return (
      <section style={S.box} data-testid="banca-diretta">
        <div style={S.testata}>
          <Landmark size={16} color={COLORS.primary} />
          <strong style={S.titolo}>Banco BPM · movimenti dalla banca</strong>
        </div>
        <div style={S.testo}>
          Lettura diretta spenta: su Render manca <strong>ENABLE_BANKING_ENABLED=true</strong>.
          Finché è spenta i movimenti arrivano solo dall'estratto conto caricato a mano.
        </div>
      </section>
    );
  }

  const collega = async () => {
    setLavoro(true);
    setMsg(null);
    try {
      const res = await api.post('/api/banca/enable-banking/collega', {}, { timeout: 30000 });
      window.location.assign(res.data.url);
    } catch (e) {
      setMsg(messaggioErrore(e, 'Collegamento non avviato'));
      setLavoro(false);
    }
  };

  const aggiorna = async () => {
    setLavoro(true);
    setMsg(null);
    setEsito(null);
    try {
      const giorni = stato.ultimo_import ? 10 : 90;
      const ant = await api.get('/api/banca/enable-banking/anteprima', { params: { giorni }, timeout: 90000 });
      const c = ant.data.conteggi || {};
      const nuovi = Number(c.nuovi || 0);
      if (!nuovi) {
        setEsito({ importati: 0, gia_presenti: c.gia_presenti, da_verificare_esclusi: c.da_verificare });
        return;
      }
      const ok = await confirm({
        title: 'Aggiorna i movimenti Banco BPM',
        message: `Dalla banca arrivano ${nuovi} movimenti nuovi.\n${c.gia_presenti || 0} sono già in archivio, ${c.da_verificare || 0} restano da verificare e non entrano.`,
        confirmText: `Importa ${nuovi}`,
        cancelText: 'Annulla',
      });
      if (!ok) return;
      const res = await api.post('/api/banca/enable-banking/importa', { conferma: true, giorni }, { timeout: 120000 });
      setEsito(res.data);
      carica();
    } catch (e) {
      setMsg(messaggioErrore(e, 'Aggiornamento dalla banca non riuscito'));
    } finally {
      setLavoro(false);
    }
  };

  const giro = stato.giro_automatico;
  let testoGiro = 'Nessun giro automatico ancora eseguito';
  if (giro?.errore) testoGiro = `Ultimo giro automatico ${dataOra(giro.eseguito_il)}: non riuscito (${giro.errore})`;
  else if (giro?.saltato) testoGiro = `Ultimo giro automatico ${dataOra(giro.eseguito_il)}: saltato (${giro.saltato === 'non_collegato' ? 'conto non collegato' : 'lettura spenta'})`;
  else if (giro) testoGiro = `Ultimo giro automatico ${dataOra(giro.eseguito_il)}: ${giro.importati} nuovi importati, ${giro.da_verificare_esclusi} da verificare`;

  return (
    <section style={S.box} data-testid="banca-diretta" aria-live="polite">
      <div style={S.testata}>
        <Landmark size={16} color={COLORS.primary} />
        <strong style={S.titolo}>Banco BPM · movimenti dalla banca</strong>
      </div>
      {!stato.configurato && (
        <div style={S.testo}>Lettura diretta accesa, ma mancano le chiavi di Enable Banking su Render.</div>
      )}
      {stato.configurato && !stato.collegata && (
        <div style={S.testo}>Conto non collegato: premi «Collega Banco BPM» e autorizza in banca.</div>
      )}
      {stato.configurato && stato.collegata && (
        <>
          <div style={S.testo}>
            Collegato, permesso valido fino al <strong>{giorno(stato.valida_fino)}</strong>.
            I movimenti nuovi entrano da soli alle 07:15 e alle 09:00.
          </div>
          <div style={S.nota}>{testoGiro}</div>
        </>
      )}
      {stato.configurato && (
        <div style={S.azioni}>
          {stato.collegata && (
            <button type="button" style={S.primario} onClick={aggiorna} disabled={lavoro}>
              <RefreshCw size={14} /> {lavoro ? 'Lettura dalla banca…' : 'Aggiorna ora'}
            </button>
          )}
          <button type="button" style={S.bottone} onClick={collega} disabled={lavoro}>
            <Link2 size={14} /> {stato.collegata ? 'Ricollega Banco BPM' : 'Collega Banco BPM'}
          </button>
        </div>
      )}
      {msg && <div style={S.errore} role="alert">{msg}</div>}
      {esito && (
        <div style={S.successo} data-testid="esito-banca">
          Importati <strong>{esito.importati ?? 0}</strong> movimenti nuovi
          {' '}· già presenti <strong>{esito.gia_presenti ?? 0}</strong>
          {' '}· da verificare (non importati) <strong>{esito.da_verificare_esclusi ?? 0}</strong>.
        </div>
      )}
    </section>
  );
}

const S = {
  box: {
    background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10,
    padding: '12px 14px', marginBottom: 10, maxWidth: '100%', boxSizing: 'border-box',
    overflowWrap: 'anywhere',
  },
  testata: { display: 'flex', alignItems: 'center', gap: 8 },
  titolo: { fontSize: 14, color: COLORS.text },
  testo: { fontSize: 13, color: COLORS.text, marginTop: 6 },
  nota: { fontSize: 12, color: COLORS.textMuted, marginTop: 4 },
  azioni: { display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 },
  bottone: {
    display: 'inline-flex', alignItems: 'center', gap: 6, minHeight: 44, padding: '0 14px',
    border: `1px solid ${COLORS.border}`, borderRadius: 8, background: COLORS.card,
    color: COLORS.text, fontWeight: 600, cursor: 'pointer',
  },
  primario: {
    display: 'inline-flex', alignItems: 'center', gap: 6, minHeight: 44, padding: '0 14px',
    border: 'none', borderRadius: 8, background: COLORS.primary,
    color: '#fff', fontWeight: 700, cursor: 'pointer',
  },
  errore: {
    marginTop: 8, padding: 10, borderRadius: 8, background: COLORS.dangerLight,
    color: COLORS.danger, fontSize: 13,
  },
  successo: {
    marginTop: 8, padding: '9px 11px', borderRadius: 8,
    color: COLORS.success, background: COLORS.successLight, fontSize: 13,
  },
};
