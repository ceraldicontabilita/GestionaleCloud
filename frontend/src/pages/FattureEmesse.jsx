import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Download, FileCode, Link2, RefreshCw, Upload, Users, FileOutput } from 'lucide-react';
import api, { messaggioErrore } from '../api';
import { COLORS, formatDateIT } from '../lib/utils';
import { euroOppure } from '../lib/vista';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { scaricaOriginale } from '../lib/scaricaOriginale';
import { urlOriginale } from '../lib/vista';
import { PageLoading, PageEmpty, PageError } from '../components/PageLayout';
import { Badge, Button, ListaAdattiva, PageHeader, RowActions, RowActionButton } from '../components/ds';

// Una fattura fatta dopo lo scontrino non aumenta le entrate: il ricavo, l'IVA
// e l'incasso sono gia' nel corrispettivo del giorno (decisione del titolare,
// 27/09/2026). Qui si vede a quale corrispettivo appartiene.
const STATI = {
  SODDISFATTO: { testo: 'Collegata', variant: 'success' },
  DA_VERIFICARE: { testo: 'Da scegliere', variant: 'warning' },
  ATTESO: { testo: 'Corrispettivo non arrivato', variant: 'neutral' },
};

export function statoCorrispettivo(fattura) {
  const stato = fattura?.corrispettivo?.stato || 'ATTESO';
  return { stato, ...(STATI[stato] || STATI.ATTESO) };
}

export function descriviScontrino(fattura) {
  const s = fattura?.scontrino || {};
  if (!s.data) return 'Scontrino non indicato';
  const numero = s.numero ? ` n. ${s.numero}` : '';
  const fonte = s.fonte === 'data_fattura' ? ' (data della fattura)' : '';
  return `Scontrino del ${formatDateIT(s.data)}${numero}${fonte}`;
}

function SceltaCorrispettivo({ fattura, onScelto }) {
  const [opzioni, setOpzioni] = useState(null);
  const [errore, setErrore] = useState('');
  useEffect(() => {
    let vivo = true;
    api.get(`/api/invoices/emesse/${encodeURIComponent(fattura.id)}/corrispettivi-vicini`)
      .then(r => { if (vivo) setOpzioni(r.data?.corrispettivi || []); })
      .catch(e => { if (vivo) setErrore(messaggioErrore(e)); });
    return () => { vivo = false; };
  }, [fattura.id]);
  const scegli = async id => {
    try {
      await api.post(`/api/invoices/emesse/${encodeURIComponent(fattura.id)}/corrispettivo`, { corrispettivo_id: id });
      onScelto();
    } catch (e) {
      setErrore(messaggioErrore(e));
    }
  };
  if (errore) return <div style={{ color: COLORS.danger, fontSize: 13 }}>{errore}</div>;
  if (opzioni === null) return <div style={{ fontSize: 13, color: COLORS.textMuted }}>Cerco i corrispettivi vicini…</div>;
  if (!opzioni.length) {
    return <div style={{ fontSize: 13, color: COLORS.textMuted }}>Nessun corrispettivo da tre giorni prima a tre dopo lo scontrino.</div>;
  }
  return (
    <div data-testid={`scelta-corrispettivo-${fattura.id}`} style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 6 }}>
      {opzioni.map(c => (
        <Button key={c.id} variant="secondary" size="sm" onClick={() => scegli(c.id)} style={{ minHeight: 44 }}>
          {formatDateIT(c.data)} · {euroOppure(c.totale)}
        </Button>
      ))}
    </div>
  );
}

function Clienti() {
  const [dati, setDati] = useState(null);
  const [errore, setErrore] = useState('');
  useEffect(() => {
    api.get('/api/invoices/emesse/clienti')
      .then(r => setDati(r.data?.clienti || []))
      .catch(e => setErrore(messaggioErrore(e)));
  }, []);
  if (errore) return <PageError message={errore} />;
  if (dati === null) return <PageLoading />;
  if (!dati.length) {
    return <PageEmpty message="Nessun cliente. Carica ReportClienti.xls da Documenti › Importa, oppure le fatture emesse: il cliente nasce dalla fattura." />;
  }
  return (
    <ListaAdattiva
      testId="clienti-table"
      dati={dati}
      pageSize={200}
      colonne={[
        { key: 'denominazione', label: 'Cliente', ruoloCard: 'titolo', tdStyle: { fontWeight: 600 } },
        { key: 'partita_iva', label: 'P.IVA / C.F.', ruoloCard: 'sottotitolo',
          render: c => c.partita_iva || c.codice_fiscale || '—', mono: true },
        { key: 'tipo_cliente', label: 'Tipo', ruoloCard: 'dettaglio', render: c => c.tipo_cliente || '—' },
        { key: 'contatti', label: 'Contatti', ruoloCard: 'dettaglio',
          render: c => [c.email, c.pec, c.telefono].filter(Boolean).join(' · ') || '—' },
        { key: 'fatture', label: 'Fatture', align: 'right', ruoloCard: 'dettaglio', render: c => c.fatture || 0 },
        { key: 'totale_fatturato', label: 'Fatturato', align: 'right', mono: true, ruoloCard: 'importo',
          render: c => euroOppure(c.totale_fatturato) },
      ]}
    />
  );
}

export default function FattureEmesse() {
  const { anno } = useAnnoGlobale();
  const navigate = useNavigate();
  const [vista, setVista] = useState('fatture');
  const [dati, setDati] = useState(null);
  const [errore, setErrore] = useState('');
  const [aperta, setAperta] = useState(null);
  const [avviso, setAvviso] = useState('');

  const carica = useCallback(async () => {
    setErrore('');
    try {
      const r = await api.get(`/api/invoices/emesse?anno=${anno}`);
      setDati(r.data || { fatture: [], riepilogo: {} });
    } catch (e) {
      setErrore(messaggioErrore(e));
    }
  }, [anno]);

  useEffect(() => { carica(); }, [carica]);

  const scarica = async (fattura, formato) => {
    setAvviso('');
    try {
      const url = formato === 'xml'
        ? urlOriginale({ tipo: 'fattura_emessa', id: fattura.id })
        : `/api/invoices/emesse/${encodeURIComponent(fattura.id)}/vista?scarica=true`;
      await scaricaOriginale(url, `fattura_${fattura.numero_fattura}`);
    } catch (e) {
      setAvviso(`Scaricamento non riuscito: ${messaggioErrore(e)}`);
    }
  };

  const fatture = dati?.fatture || [];
  const riepilogo = dati?.riepilogo || {};
  const perStato = riepilogo.per_stato || {};
  const daScegliere = (perStato.DA_VERIFICARE || 0) + (perStato.ATTESO || 0);

  const pastiglie = useMemo(() => [
    { etichetta: 'Fatture emesse', valore: String(riepilogo.numero || 0), nota: `Anno ${anno}`, tono: 'neutro' },
    { etichetta: 'Totale fatturato', valore: euroOppure(riepilogo.totale),
      nota: 'Già nei corrispettivi: non aumenta le entrate', tono: 'neutro' },
    { etichetta: 'Collegate al corrispettivo', valore: String(perStato.SODDISFATTO || 0),
      nota: 'Il giorno dello scontrino', tono: 'ok' },
    { etichetta: 'Da sistemare', valore: String(daScegliere),
      nota: 'Corrispettivo da scegliere o non ancora arrivato', tono: daScegliere ? 'attenzione' : 'ok' },
  ], [anno, riepilogo.numero, riepilogo.totale, perStato.SODDISFATTO, daScegliere]);

  const colonne = [
    { key: 'numero_fattura', label: 'Numero', ruoloCard: 'titolo', tdStyle: { fontWeight: 700, whiteSpace: 'nowrap' } },
    { key: 'data_fattura', label: 'Data', ruoloCard: 'sottotitolo', render: f => formatDateIT(f.data_fattura) },
    { key: 'cliente_nome', label: 'Cliente', ruoloCard: 'dettaglio', render: f => f.cliente_nome || '—' },
    { key: 'scontrino', label: 'Scontrino', ruoloCard: 'dettaglio', render: f => descriviScontrino(f) },
    {
      key: 'corrispettivo', label: 'Corrispettivo', ruoloCard: 'dettaglio',
      render: f => {
        const s = statoCorrispettivo(f);
        return (
          <div>
            <Badge variant={s.variant}>{s.testo}</Badge>
            {s.stato === 'SODDISFATTO' && f.corrispettivo?.data && (
              <span style={{ fontSize: 12.5, color: COLORS.textMuted, marginLeft: 6 }}>
                del {formatDateIT(f.corrispettivo.data)}
              </span>
            )}
            {aperta === f.id && <SceltaCorrispettivo fattura={f} onScelto={() => { setAperta(null); carica(); }} />}
          </div>
        );
      },
    },
    { key: 'totale', label: 'Totale', align: 'right', mono: true, ruoloCard: 'importo', render: f => euroOppure(f.totale) },
    {
      key: 'azioni', label: '', ruoloCard: 'azioni',
      render: f => (
        <RowActions>
          <RowActionButton onClick={() => scarica(f, 'vista')} title="Scarica la fattura leggibile" data-testid={`scarica-${f.id}`}>
            <Download size={16} /> Scarica fattura
          </RowActionButton>
          <RowActionButton onClick={() => scarica(f, 'xml')} title="Scarica l'XML originale">
            <FileCode size={16} /> XML
          </RowActionButton>
          {statoCorrispettivo(f).stato !== 'SODDISFATTO' || f.corrispettivo?.scelto_da_titolare ? (
            <RowActionButton onClick={() => setAperta(aperta === f.id ? null : f.id)} title="Scegli il corrispettivo">
              <Link2 size={16} /> Scegli corrispettivo
            </RowActionButton>
          ) : null}
        </RowActions>
      ),
    },
  ];

  return (
    <div style={{ width: '100%' }}>
      <PageHeader
        title="Fatture emesse"
        subtitle="Le fatture fatte dopo lo scontrino: ricavo, IVA e incasso sono già nel corrispettivo del giorno, qui non si contano di nuovo."
        icon={<FileOutput size={20} />}
        pastiglie={pastiglie}
        actions={(
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Button variant="primary" iconLeft={<Upload size={16} />} onClick={() => navigate('/documenti/import')} style={{ minHeight: 44 }}>
              Carica fatture o clienti
            </Button>
            <Button variant="secondary" iconLeft={<RefreshCw size={16} />} onClick={carica} style={{ minHeight: 44 }}>
              Rileggi
            </Button>
          </div>
        )}
        style={{ marginBottom: 14 }}
      />
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <Button variant={vista === 'fatture' ? 'primary' : 'secondary'} iconLeft={<FileOutput size={16} />}
          onClick={() => setVista('fatture')} style={{ minHeight: 44 }} data-testid="vista-fatture">
          Fatture
        </Button>
        <Button variant={vista === 'clienti' ? 'primary' : 'secondary'} iconLeft={<Users size={16} />}
          onClick={() => setVista('clienti')} style={{ minHeight: 44 }} data-testid="vista-clienti">
          Clienti
        </Button>
      </div>
      {avviso && <div role="alert" style={{ color: COLORS.danger, marginBottom: 10, fontSize: 13.5 }}>{avviso}</div>}
      {vista === 'clienti' ? <Clienti /> : (
        errore ? <PageError message={errore} /> : dati === null ? <PageLoading /> : !fatture.length ? (
          <PageEmpty message={`Nessuna fattura emessa nel ${anno}. Caricale da Documenti › Importa (XML o ZIP dal portale): il gestionale le riconosce da sole.`} />
        ) : (
          <ListaAdattiva testId="fatture-emesse-table" dati={fatture} pageSize={200} colonne={colonne}
            resetKey={`${anno}-${fatture.length}`} />
        )
      )}
    </div>
  );
}
