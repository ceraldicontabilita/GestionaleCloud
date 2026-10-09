import React, { useEffect, useState } from 'react';
import api from '../api';
import { toast } from 'sonner';
import { Badge, Button, Card, Select, StatCard } from './ds';
import { BORDER_RADIUS, COLORS, useIsMobile } from '../lib/utils';

// Un solo ingresso Drive: la cartella unica «DATI SOCIETA CERALDI». I vecchi
// canali per sezione (fatture, corrispettivi, ...) sono smontati: questa
// scheda li interrogava ancora e mostrava «Non configurato» e zero trovati
// mentre la cartella unica importava davvero.
const formatoData = valore => (valore
  ? new Date(valore).toLocaleString('it-IT', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
  : 'mai eseguito');

export function DriveFattureImportCard() {
  const isMobile = useIsMobile();
  const [stato, setStato] = useState(null);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [message, setMessage] = useState(null);

  const loadStatus = async () => {
    try {
      const response = await api.get('/api/documenti/cartella-unica/stato');
      setStato(response.data || null);
      return response.data || null;
    } catch (error) {
      setMessage({
        ok: false,
        text: error.response?.data?.detail || 'Stato della cartella Drive non disponibile.',
      });
      return null;
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const importaTutto = async () => {
    setImporting(true);
    setMessage(null);
    try {
      const response = await api.post('/api/documenti/cartella-unica/giro?tutto=true');
      if (!response.data?.avviato && response.data?.motivo !== 'giro_in_corso') {
        setMessage({ ok: false, text: 'Import non avviato.' });
        return;
      }
      const startedAt = Date.now();
      let attuale = null;
      while (Date.now() - startedAt < 60 * 60 * 1000) {
        await new Promise(resolve => setTimeout(resolve, 5000));
        attuale = await loadStatus();
        if (attuale && !attuale.giro_in_corso) break;
      }
      const ultimo = attuale?.ultimo_giro?.last_result || {};
      if (attuale?.giro_in_corso) {
        setMessage({ ok: true, text: 'Import ancora in corso: i numeri si aggiornano da soli.' });
      } else if (attuale?.ultimo_giro?.last_error) {
        setMessage({ ok: false, text: `Import fermato: ${attuale.ultimo_giro.last_error}` });
      } else {
        setMessage({
          ok: (ultimo.errori || 0) === 0,
          text: `Completato. In cartella restano ${ultimo.restanti ?? 0} file.`,
        });
      }
    } catch (error) {
      setMessage({
        ok: false,
        text: error.response?.data?.detail || `Errore durante l'import (${error.message}).`,
      });
    } finally {
      setImporting(false);
    }
  };

  const ultimo = stato?.ultimo_giro?.last_result || {};
  const registro = stato?.registro || {};
  const inCorso = importing || stato?.giro_in_corso;

  return (
    <div data-testid="drive-fatture-card">
      <Card
        title={
          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            Google Drive - cartella DATI SOCIETA CERALDI
            {!loading && (
              <Badge variant={stato?.attiva ? 'success' : 'warning'}>
                {stato?.attiva ? 'Attiva' : 'Non attiva'}
              </Badge>
            )}
          </span>
        }
        actions={
          <Button
            variant="primary"
            size="sm"
            data-testid="drive-sync-btn"
            onClick={importaTutto}
            disabled={loading || inCorso || !stato?.attiva}
          >
            {inCorso ? 'Import in corso...' : 'Importa tutto da Drive'}
          </Button>
        }
      >
        <p style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 16 }}>
          Fatture XML, F24, quietanze, cedolini, estratti conto, corrispettivi: il gestionale
          riconosce ogni file lasciato nella cartella e lo sposta in ELABORATE. Il giro automatico
          ne prende un lotto ogni 15 minuti; il pulsante li importa tutti adesso.
        </p>

        <div
          data-testid="drive-ultimo-giro"
          style={{
            display: 'grid',
            gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)',
            gap: 12,
            marginBottom: 12,
          }}
        >
          <StatCard accent="none" label="Ancora in cartella" value={ultimo.restanti ?? 0} />
          <StatCard accent="none" label="Elaborati (ultimo giro)" value={ultimo.elaborati ?? 0} />
          <StatCard accent="none" label="Doppioni tolti" value={ultimo.doppioni_cestinati ?? 0} />
          <StatCard
            accent={(ultimo.errori || 0) > 0 ? 'danger' : 'none'}
            label="Errori (ultimo giro)"
            value={ultimo.errori ?? 0}
          />
        </div>

        <div style={{ fontSize: 12.5, color: COLORS.textMuted, marginBottom: 12 }}>
          {registro.ELABORATE ?? 0} file elaborati in tutto · {registro.ERRORI ?? 0} in ERRORI
          {registro.ARRETRATO ? ` · ${registro.ARRETRATO} estratti dell'arretrato fermi in ARRETRATO` : ''}
          {' · '}ultimo giro: {formatoData(stato?.ultimo_giro?.updated_at)}
        </div>

        {message && (
          <div
            role="status"
            style={{
              padding: '8px 12px',
              borderRadius: BORDER_RADIUS.md,
              background: message.ok ? COLORS.successLight : COLORS.dangerLight,
              color: message.ok ? COLORS.success : COLORS.danger,
              fontSize: 13,
            }}
          >
            {message.text}
          </div>
        )}
      </Card>
    </div>
  );
}

export function AnnoImportazioneCard() {
  const [anno, setAnno] = useState(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState(null);

  const currentYear = new Date().getFullYear();
  const yearOptions = Array.from({ length: 6 }, (_, index) => currentYear - 4 + index);

  useEffect(() => {
    api
      .get('/api/config-import/anno')
      .then(response => setAnno(response.data.anno))
      .catch(() => setAnno(currentYear))
      .finally(() => setLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const saveYear = async nextYear => {
    setSaving(true);
    try {
      await api.put('/api/config-import/anno', { anno: nextYear });
      setAnno(nextYear);
      toast.success(`Anno di importazione impostato su ${nextYear}`);
    } catch (error) {
      toast.error(`Errore salvataggio: ${error.response?.data?.detail || error.message}`);
    } finally {
      setSaving(false);
    }
  };

  const importYear = async () => {
    setImporting(true);
    setResult(null);
    try {
      const response = await api.post('/api/config-import/importa-anno', { anno });
      if (!response.data.started) {
        throw new Error(`È già in corso l'import ${response.data.anno ?? ''}`.trim());
      }
      let stato = response.data;
      while (['avvio', 'in_corso'].includes(stato.stato)) {
        await new Promise(resolve => setTimeout(resolve, 2000));
        stato = (await api.get('/api/config-import/importa-anno/stato')).data;
      }
      if (stato.stato === 'errore') throw new Error(stato.errore || 'Import non riuscito');
      setResult(stato.risultato);
      toast.success(`Import ${anno} completato`);
    } catch (error) {
      toast.error(`Errore import: ${error.response?.data?.detail || error.message}`);
    } finally {
      setImporting(false);
    }
  };

  return (
    <Card title="Import Drive per anno">
      <p style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 12 }}>
        Scegli l'anno operativo per fatture e corrispettivi, quindi importa i
        documenti di quell'anno nel flusso contabile. Il caricamento manuale resta sempre attivo.
      </p>
      {loading ? (
        <span style={{ fontSize: 13, color: COLORS.textMuted }}>Caricamento...</span>
      ) : (
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <Select
            value={anno ?? ''}
            onChange={event => saveYear(parseInt(event.target.value, 10))}
            disabled={saving || importing}
            data-testid="select-anno-importazione-attivo"
            style={{ minWidth: 140 }}
          >
            {yearOptions.map(option => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </Select>
          <Button
            onClick={importYear}
            disabled={saving || importing || !anno}
            data-testid="importa-anno-btn"
          >
            {importing ? `Import ${anno} in corso...` : `Importa ${anno ?? ''} da Drive`}
          </Button>
        </div>
      )}

      {result && (
        <div
          style={{
            marginTop: 12,
            fontSize: 12,
            background: COLORS.successLight,
            border: `1px solid ${COLORS.success}`,
            borderRadius: BORDER_RADIUS.md,
            padding: 10,
          }}
          data-testid="esito-import-anno"
        >
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Esito import {result.anno}</div>
          <div>
            Drive:{' '}
            {result.drive?.saltato
              ?? `${result.drive?.elaborati ?? 0} file elaborati, ${result.drive?.errori ?? 0} errori, ${result.drive?.restanti ?? 0} ancora in cartella`}
          </div>
          <div>
            Ripresi dall'archivio: {result.promozione_archivio?.corrispettivi_promossi ?? 0}{' '}
            corrispettivi, {result.promozione_archivio?.fatture_promosse ?? 0} fatture
          </div>
        </div>
      )}
    </Card>
  );
}
