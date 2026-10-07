import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { FileText, FileDown, RefreshCw, Webhook, FlaskConical, KeyRound } from 'lucide-react';
import api from '../api';
import { COLORS, BORDER_RADIUS, formatDateIT, formatDateTimeIT, formatEuro } from '../lib/utils';
import { Button, Badge, PageHeader, TableWrap, Table, Th, Td, RowActions, RowActionButton } from '../components/ds';

// A-Cube: le fatture passive arrivano dallo SdI / dal Cassetto fiscale via API.
// In sandbox sono simulate e non entrano mai in contabilità; in produzione
// passano dallo smistatore dei documenti, come la cartella unica Drive.

const STATI = {
  importata: { variant: 'success', label: 'Importata' },
  simulata: { variant: 'info', label: 'Prova sandbox' },
  registrata: { variant: 'neutral', label: 'Registrata' },
  da_importare: { variant: 'warning', label: 'Da importare' },
  errore_import: { variant: 'danger', label: 'Errore import' },
  quarantena: { variant: 'danger', label: 'Quarantena A-Cube' },
};

const errore = e => e.response?.data?.detail || e.response?.data?.message || e.message;

export default function IntegrazioneACube() {
  const [stato, setStato] = useState(null);
  const [fatture, setFatture] = useState([]);
  const [totale, setTotale] = useState(0);
  const [limite, setLimite] = useState(50);
  const [lavoro, setLavoro] = useState('');

  const carica = useCallback(async (n = limite) => {
    try {
      const [s, f] = await Promise.all([
        api.get('/api/acube/stato'),
        api.get(`/api/acube/fatture?limite=${n}`),
      ]);
      setStato(s.data);
      setFatture(f.data.fatture || []);
      setTotale(f.data.totale || 0);
    } catch (e) {
      toast.error('A-Cube non leggibile', { description: errore(e) });
    }
  }, [limite]);

  useEffect(() => { carica(); }, [carica]);

  const esegui = async (chiave, chiamata, messaggio) => {
    setLavoro(chiave);
    try {
      const r = await chiamata();
      toast.success(messaggio(r.data));
      await carica();
    } catch (e) {
      toast.error('Operazione non riuscita', { description: errore(e) });
    } finally {
      setLavoro('');
    }
  };

  const verificaAccesso = () => esegui('accesso', () => api.post('/api/acube/verifica-accesso'),
    d => (d.ok ? `${d.messaggio} (${d.ambiente})` : d.messaggio));
  const registraWebhook = () => esegui('webhook', () => api.post('/api/acube/registra-webhook'),
    d => `Webhook registrato su A-Cube (${d.ambiente})`);
  const controllaOra = () => esegui('controlla', () => api.post('/api/acube/controlla'),
    d => `Trovate ${d.trovate}, nuove ${d.acquisite}, già presenti ${d.gia_presenti}`);
  const simula = () => esegui('simula', () => api.post('/api/acube/simula'),
    d => `Fattura di prova ${d.numero} inviata: arriva col webhook in pochi secondi`);

  const apri = async (f, formato) => {
    try {
      const r = await api.get(`/api/acube/fatture/${f.uuid}/vista?formato=${formato}`, { responseType: 'blob' });
      const url = URL.createObjectURL(r.data);
      window.open(url, '_blank', 'noopener');
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) {
      toast.error('Fattura non apribile', { description: errore(e) });
    }
  };

  const sandbox = stato?.ambiente === 'sandbox';
  const importate = fatture.filter(f => f.stato === 'importata').length;
  const problemi = fatture.filter(f => ['errore_import', 'quarantena', 'da_importare'].includes(f.stato)).length;

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '16px 0' }}>
      <PageHeader
        title="A-Cube · fatture passive via API"
        subtitle="Le fatture dei fornitori arrivano da A-Cube col webhook, con un controllo di riserva ogni mattina alle 6:20."
        pastiglie={[
          {
            etichetta: 'Ambiente',
            valore: stato ? (sandbox ? 'Sandbox' : 'Produzione') : null,
            nota: stato ? (stato.import_attivo ? 'importa in contabilità' : 'non tocca la contabilità') : '',
            tono: stato ? (sandbox ? 'attenzione' : 'ok') : 'neutro',
          },
          {
            etichetta: 'Credenziali',
            valore: stato ? (stato.configurato ? 'Presenti' : 'Mancanti') : null,
            nota: 'ACUBE_EMAIL e ACUBE_PASSWORD su Render',
            tono: stato ? (stato.configurato ? 'ok' : 'male') : 'neutro',
          },
          {
            etichetta: 'Fatture ricevute',
            valore: totale,
            nota: sandbox ? 'di prova' : `${importate} importate fra le ultime`,
          },
          {
            etichetta: 'Da guardare',
            valore: problemi,
            nota: 'errori, quarantena o in attesa',
            tono: problemi ? 'male' : 'ok',
          },
        ]}
      />

      {sandbox && (
        <div style={{
          background: COLORS.warningLight, border: `1px solid ${COLORS.warning}`,
          borderRadius: BORDER_RADIUS.md, padding: '10px 14px', fontSize: 13, color: COLORS.text, marginBottom: 12,
        }}>
          Ambiente di <strong>prova</strong>: le fatture qui sono simulate e non entrano in Fatture, Prima nota
          o IVA. Per la produzione basta mettere <code>ACUBE_ENV=production</code> su Render dopo l'attivazione A-Cube.
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
        <Button variant="secondary" size="sm" iconLeft={<KeyRound size={14} />} disabled={!!lavoro} onClick={verificaAccesso}>
          {lavoro === 'accesso' ? 'Verifico…' : 'Verifica accesso'}
        </Button>
        <Button variant="secondary" size="sm" iconLeft={<Webhook size={14} />} disabled={!!lavoro} onClick={registraWebhook}
          data-testid="acube-registra-webhook">
          {lavoro === 'webhook' ? 'Registro…' : (stato?.webhook_segreto_presente ? 'Aggiorna webhook' : 'Registra webhook')}
        </Button>
        <Button variant="secondary" size="sm" iconLeft={<RefreshCw size={14} />} disabled={!!lavoro} onClick={controllaOra}>
          {lavoro === 'controlla' ? 'Controllo…' : 'Controlla ora (ultimi 5 giorni)'}
        </Button>
        {sandbox && (
          <Button size="sm" iconLeft={<FlaskConical size={14} />} disabled={!!lavoro} onClick={simula}
            data-testid="acube-simula">
            {lavoro === 'simula' ? 'Invio…' : 'Simula fattura passiva'}
          </Button>
        )}
        <Button variant="secondary" size="sm" iconLeft={<RefreshCw size={14} />} onClick={() => carica()}>
          Aggiorna
        </Button>
      </div>

      {stato?.ultimo_controllo && (
        <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 8 }}>
          Ultimo controllo: {formatDateTimeIT(stato.ultimo_controllo)}
        </div>
      )}

      {fatture.length === 0 ? (
        <div style={{ color: COLORS.textMuted, padding: 24, textAlign: 'center' }}>
          Nessuna fattura ricevuta da A-Cube{sandbox ? ': prova con «Simula fattura passiva».' : '.'}
        </div>
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Ricevuta</Th>
                <Th>Fornitore</Th>
                <Th>Numero</Th>
                <Th>Data</Th>
                <Th style={{ textAlign: 'right' }}>Totale</Th>
                <Th>Stato</Th>
                <Th></Th>
              </tr>
            </thead>
            <tbody>
              {fatture.map(f => {
                const s = STATI[f.stato] || { variant: 'neutral', label: f.stato || '—' };
                return (
                  <tr key={f.uuid} data-testid={`acube-riga-${f.uuid}`}>
                    <Td>{formatDateTimeIT(f.registrata_il)}</Td>
                    <Td>
                      <div>{f.fornitore || 'Dato non disponibile'}</div>
                      {f.fornitore_piva && <div style={{ fontSize: 11, color: COLORS.textMuted }}>{f.fornitore_piva}</div>}
                    </Td>
                    <Td>{f.numero || '—'}</Td>
                    <Td>{f.data ? formatDateIT(f.data) : '—'}</Td>
                    <Td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                      {f.totale != null ? formatEuro(f.totale) : '—'}
                    </Td>
                    <Td>
                      <Badge variant={s.variant} title={f.esito_import || f.notice || ''}>{s.label}</Badge>
                    </Td>
                    <Td>
                      <RowActions>
                        <RowActionButton title="Apri la fattura" onClick={() => apri(f, 'html')}>
                          <FileText size={16} />
                        </RowActionButton>
                        <RowActionButton title="PDF" onClick={() => apri(f, 'pdf')}>
                          <FileDown size={16} />
                        </RowActionButton>
                      </RowActions>
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        </TableWrap>
      )}
      {fatture.length < totale && (
        <div style={{ textAlign: 'center', marginTop: 12 }}>
          <Button variant="secondary" size="sm" onClick={() => { const n = limite + 50; setLimite(n); carica(n); }}>
            Mostra altri
          </Button>
        </div>
      )}
    </div>
  );
}
