import React, { useEffect, useState } from 'react';
import api from '../api';
import { toast } from 'sonner';
import { Badge, Button, Card, Select, StatCard } from './ds';
import { BORDER_RADIUS, COLORS, useIsMobile } from '../lib/utils';

export function DriveFattureImportCard() {
  const isMobile = useIsMobile();
  const [driveStatus, setDriveStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState(null);

  const loadStatus = async () => {
    try {
      const response = await api.get('/api/fatture/drive/status');
      setDriveStatus(response.data || null);
    } catch (error) {
      setMessage({
        ok: false,
        text: error.response?.data?.detail || 'Stato Google Drive non disponibile.',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const syncNow = async () => {
    setSyncing(true);
    setMessage(null);
    try {
      const response = await api.post('/api/fatture/drive/sync');
      const result = response.data || {};
      if (result.status === 'not_configured' || result.status === 'error') {
        setMessage({ ok: false, text: result.message || 'Sincronizzazione non avviata.' });
        return;
      }

      const startedAt = Date.now();
      let status = null;
      while (Date.now() - startedAt < 15 * 60 * 1000) {
        await new Promise(resolve => setTimeout(resolve, 4000));
        try {
          status = (await api.get('/api/fatture/drive/status')).data || null;
          if (status && !status.sync_running) break;
        } catch {
          // Un errore transitorio non interrompe il controllo del processo avviato.
        }
      }

      if (status) setDriveStatus(status);
      if (status?.last_error) {
        setMessage({ ok: false, text: `Sincronizzazione fallita: ${status.last_error}` });
      } else if (status?.sync_running) {
        setMessage({
          ok: true,
          text: 'Sincronizzazione ancora in corso. Lo stato si aggiornera al prossimo caricamento.',
        });
      } else {
        const last = status?.last_result || {};
        setMessage({
          ok: (last.errors || 0) === 0,
          text:
            `Completata: ${last.imported || 0} importate, ` +
            `${last.duplicates || 0} gia presenti, ${last.errors || 0} errori ` +
            `(su ${last.total || 0} file trovati).`,
        });
      }
    } catch (error) {
      setMessage({
        ok: false,
        text:
          error.response?.data?.detail ||
          error.response?.data?.message ||
          `Errore durante la sincronizzazione (${error.response?.status || error.message}).`,
      });
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div data-testid="drive-fatture-card">
      <Card
        title={
          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            Google Drive - Import fatture XML
            {!loading && (
              <Badge variant={driveStatus?.configured ? 'success' : 'warning'}>
                {driveStatus?.configured ? 'Configurato' : 'Non configurato'}
              </Badge>
            )}
          </span>
        }
        actions={
          <Button
            variant="primary"
            size="sm"
            data-testid="drive-sync-btn"
            onClick={syncNow}
            disabled={loading || syncing || !driveStatus?.configured}
          >
            {syncing ? 'Sincronizzazione...' : 'Sincronizza ora'}
          </Button>
        }
      >
        <p style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 16 }}>
          Importa le fatture XML e P7M dalla cartella configurata. Questa e una
          funzione operativa di Documenti: Admin contiene soltanto la configurazione tecnica.
        </p>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)',
            gap: 12,
            marginBottom: 16,
          }}
        >
          <StatCard
            accent="none"
            label="Cartella sorgente"
            value={
              <span style={{ fontSize: 13, wordBreak: 'break-all' }}>
                {driveStatus?.folder_id || 'non impostata'}
              </span>
            }
          />
          <StatCard
            accent="none"
            label="Ultimo aggiornamento"
            value={
              <span style={{ fontSize: 14 }}>
                {driveStatus?.last_sync
                  ? new Date(driveStatus.last_sync).toLocaleString('it-IT').replaceAll('/', '-')
                  : 'mai eseguito'}
              </span>
            }
          />
          <StatCard
            accent="none"
            label="Fatture importate"
            value={<span style={{ fontSize: 14 }}>{driveStatus?.total_imported ?? 0}</span>}
          />
        </div>

        {driveStatus?.last_result && (
          <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 12 }}>
            Ultimo giro: {driveStatus.last_result.total ?? 0} file trovati,{' '}
            {driveStatus.last_result.imported ?? 0} importati,{' '}
            {driveStatus.last_result.duplicates ?? 0} gia presenti,{' '}
            {driveStatus.last_result.errors ?? 0} errori.
          </div>
        )}

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
      setResult(response.data);
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
            Drive fatture:{' '}
            {result.sync_fatture?.importate ??
              result.sync_fatture?.imported ??
              result.sync_fatture?.skipped ??
              JSON.stringify(result.sync_fatture)}
          </div>
          <div>
            Drive corrispettivi:{' '}
            {result.sync_corrispettivi?.importati ??
              result.sync_corrispettivi?.imported ??
              result.sync_corrispettivi?.skipped ??
              JSON.stringify(result.sync_corrispettivi)}
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
