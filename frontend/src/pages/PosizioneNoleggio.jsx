import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Car,
  UserRound,
  AlertTriangle,
  CheckCircle2,
  Receipt,
  Landmark,
  FileText,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { COLORS, formatEuro, formatDateIT, useIsMobile } from '../lib/utils';
import { PageSection } from '../components/PageLayout';
import { StatCard, Badge, Select, PageLoader, ListaAdattiva, Button } from '../components/ds';
import LinkContropartita, { ROTTE_CONTROPARTITA } from '../components/LinkContropartita';

/**
 * Posizione noleggio — l'estratto conto in partita doppia di ogni auto e di
 * ogni driver. Un solo motore (GET /api/noleggio/posizione) mette i costi in
 * DARE (fatture del noleggiatore per categoria, verbali dalla posta) e le
 * prove di pagamento in AVERE (allocazioni Banca BPM, quietanze
 * PartenoPay / Mooney / PayPal / PagoPA agganciate ai verbali). Il saldo e'
 * quello che resta aperto. Niente viene associato qui: un movimento che
 * nessuna relazione spiega resta nella lista «da agganciare».
 */

const CATEGORIE = [
  { key: 'canoni', label: 'Canoni' },
  { key: 'bollo', label: 'Bollo' },
  { key: 'pedaggio', label: 'Pedaggi' },
  { key: 'riparazioni', label: 'Riparazioni' },
  { key: 'costi_extra', label: 'Costi extra' },
  { key: 'verbali', label: 'Verbali' },
];

const ETICHETTA_TIPO = {
  costo: { label: 'Costo', variant: 'primary' },
  pagamento: { label: 'Pagamento', variant: 'success' },
  storno: { label: 'Storno', variant: 'accent' },
  pagamento_dichiarato: { label: 'Dichiarato', variant: 'warning' },
};

const ETICHETTA_STATO = {
  pagata: { label: 'Pagata', variant: 'success' },
  parziale: { label: 'Parziale', variant: 'warning' },
  aperta: { label: 'Aperta', variant: 'danger' },
  verificata: { label: 'Banca verificata', variant: 'success' },
  documentale: { label: 'Quietanza', variant: 'info' },
  dichiarata: { label: 'Senza estratto conto', variant: 'warning' },
  storno: { label: 'Storno', variant: 'accent' },
  importo_da_verificare: { label: 'Importo da verificare', variant: 'warning' },
};

export function etichettaFonteQuietanza(fonte) {
  return fonte || 'Nessuna quietanza';
}

function BadgeStato({ stato }) {
  const e = ETICHETTA_STATO[stato] || { label: stato || '—', variant: 'neutral' };
  return <Badge variant={e.variant}>{e.label}</Badge>;
}

function BadgeTipo({ tipo }) {
  const e = ETICHETTA_TIPO[tipo] || { label: tipo || '—', variant: 'neutral' };
  return <Badge variant={e.variant}>{e.label}</Badge>;
}

const importo = v => (v === null || v === undefined ? '—' : formatEuro(v));

function linkProva(prova) {
  if (!prova) return null;
  if (prova.movimento_id) {
    return (
      <LinkContropartita
        compatto
        to={ROTTE_CONTROPARTITA.movimentoBanca(prova.movimento_id)}
        title={`Movimento banca ${prova.movimento_id} del ${formatDateIT(prova.data)}`}
      >
        {prova.fonte || 'Banca BPM'}
      </LinkContropartita>
    );
  }
  if (prova.prima_nota_id) {
    return (
      <LinkContropartita
        compatto
        to={ROTTE_CONTROPARTITA.primaNotaBanca(prova.prima_nota_id)}
        title={`Prima Nota Banca ${prova.prima_nota_id}`}
      >
        {prova.fonte || 'Prima Nota'}
      </LinkContropartita>
    );
  }
  return (
    <span style={{ fontSize: 12, color: COLORS.textMuted }}>
      {prova.fonte || 'Quietanza'}
      {prova.data ? ` · ${formatDateIT(prova.data)}` : ''}
    </span>
  );
}

function linkDocumento(doc) {
  if (!doc) return null;
  if (doc.tipo === 'fattura' && doc.id) {
    return (
      <LinkContropartita
        compatto
        to={ROTTE_CONTROPARTITA.fattura(doc.id)}
        title={`Fattura ${doc.numero || ''} ${doc.fornitore || ''}`.trim()}
      >
        {doc.numero || 'Fattura'}
      </LinkContropartita>
    );
  }
  if (doc.tipo === 'verbale' && doc.numero) {
    return (
      <LinkContropartita
        compatto
        to={`/verbali-noleggio/${encodeURIComponent(doc.numero)}`}
        title={`Verbale ${doc.numero}`}
      >
        {doc.numero}
      </LinkContropartita>
    );
  }
  return <span>{doc.numero || '—'}</span>;
}

function nomeDriver(d) {
  if (!d) return 'Non assegnato';
  return d.driver || d.driver_id || 'Non assegnato';
}

export default function PosizioneNoleggio() {
  const { anno } = useAnnoGlobale();
  const isMobile = useIsMobile();
  const [dati, setDati] = useState(null);
  const [loading, setLoading] = useState(true);
  const [errore, setErrore] = useState('');
  const [drivers, setDrivers] = useState([]);
  const [aperte, setAperte] = useState({});
  const [assegnazione, setAssegnazione] = useState({});
  const [salvataggio, setSalvataggio] = useState('');

  const carica = useCallback(async () => {
    setLoading(true);
    setErrore('');
    try {
      const [posizione, elenco] = await Promise.all([
        api.get(`/api/noleggio/posizione?anno=${anno}`),
        api.get('/api/noleggio/drivers'),
      ]);
      setDati(posizione.data);
      setDrivers(elenco.data?.drivers || []);
    } catch (e) {
      setDati(null);
      setErrore(e?.response?.data?.detail || e.message || 'Posizione non disponibile');
    } finally {
      setLoading(false);
    }
  }, [anno]);

  useEffect(() => {
    carica();
  }, [carica]);

  const assegnaDriver = async targa => {
    const driverId = assegnazione[targa];
    if (!driverId) return;
    const scelto = drivers.find(d => d.id === driverId);
    setSalvataggio(targa);
    try {
      await api.put(`/api/noleggio/veicoli/${targa}`, {
        driver_id: driverId,
        driver: scelto?.nome_completo || '',
      });
      await carica();
    } catch (e) {
      setErrore(e?.response?.data?.detail || e.message || 'Assegnazione non riuscita');
    } finally {
      setSalvataggio('');
    }
  };

  const controlli = dati?.controlli || {};
  const totali = dati?.totali || {};

  const colonneRighe = useMemo(
    () => [
      {
        key: 'data',
        label: 'Data',
        ruoloCard: 'sottotitolo',
        render: r => formatDateIT(r.data),
      },
      { key: 'tipo', label: 'Tipo', ruoloCard: 'dettaglio', render: r => <BadgeTipo tipo={r.tipo} /> },
      {
        key: 'categoria',
        label: 'Categoria',
        ruoloCard: 'dettaglio',
        render: r => CATEGORIE.find(c => c.key === r.categoria)?.label || r.categoria,
      },
      { key: 'descrizione', label: 'Descrizione', ruoloCard: 'titolo' },
      {
        key: 'documento',
        label: 'Documento',
        ruoloCard: 'dettaglio',
        render: r => linkDocumento(r.documento),
      },
      {
        key: 'dare',
        label: 'Dare',
        align: 'right',
        mono: true,
        ruoloCard: 'importo',
        render: r =>
          r.tipo === 'costo' || r.tipo === 'storno' ? (
            importo(r.dare)
          ) : (
            <span style={{ color: COLORS.success }}>{importo(r.avere)}</span>
          ),
      },
      {
        key: 'avere',
        label: 'Avere',
        align: 'right',
        mono: true,
        ruoloCard: 'omesso',
        render: r => (r.tipo === 'pagamento' || r.tipo === 'storno' ? importo(r.avere) : ''),
      },
      { key: 'prova', label: 'Prova', ruoloCard: 'dettaglio', render: r => linkProva(r.prova) },
      { key: 'stato', label: 'Stato', ruoloCard: 'dettaglio', render: r => <BadgeStato stato={r.stato} /> },
      { key: 'driver', label: 'Driver', ruoloCard: 'dettaglio', render: r => nomeDriver(r.driver) },
    ],
    []
  );

  const colonneVerbali = useMemo(
    () => [
      { key: 'numero_verbale', label: 'Verbale', ruoloCard: 'titolo' },
      { key: 'data_verbale', label: 'Data', ruoloCard: 'sottotitolo', render: v => formatDateIT(v.data_verbale) },
      {
        key: 'importo',
        label: 'Importo',
        align: 'right',
        mono: true,
        ruoloCard: 'importo',
        render: v =>
          v.in_fattura ? importo(v.importo_riaddebito) : v.importo_da_verificare ? 'da verificare' : importo(v.importo_verificato),
      },
      {
        key: 'origine',
        label: 'Arrivato da',
        ruoloCard: 'dettaglio',
        render: v => (v.in_fattura ? `Riaddebito ${v.fattura?.numero || ''}`.trim() : 'Posta / PEC'),
      },
      {
        key: 'fonte_quietanza',
        label: 'Quietanza',
        ruoloCard: 'dettaglio',
        render: v =>
          v.pagato ? (
            <Badge variant="success">{etichettaFonteQuietanza(v.fonte_quietanza)}</Badge>
          ) : (
            <Badge variant="danger">Da pagare</Badge>
          ),
      },
      {
        key: 'driver_competente',
        label: 'Driver alla data',
        ruoloCard: 'dettaglio',
        render: v => nomeDriver(v.driver_competente),
      },
      {
        key: 'trattenute',
        label: 'Trattenuta',
        ruoloCard: 'dettaglio',
        render: v =>
          v.trattenute?.length
            ? v.trattenute.map(t => `${formatEuro(t.importo)} (${t.stato || 'proposta'})`).join(', ')
            : '—',
      },
    ],
    []
  );

  const colonneDriver = useMemo(
    () => [
      {
        key: 'driver',
        label: 'Driver',
        ruoloCard: 'titolo',
        render: d => (d.senza_driver ? 'Senza driver assegnato' : d.driver || d.driver_id),
      },
      { key: 'veicoli', label: 'Auto', ruoloCard: 'sottotitolo', render: d => d.veicoli.join(', ') },
      { key: 'dare', label: 'Dare', align: 'right', mono: true, ruoloCard: 'dettaglio', render: d => importo(d.dare) },
      { key: 'avere', label: 'Avere', align: 'right', mono: true, ruoloCard: 'dettaglio', render: d => importo(d.avere) },
      {
        key: 'saldo',
        label: 'Saldo',
        align: 'right',
        mono: true,
        ruoloCard: 'importo',
        render: d => <span style={{ color: d.saldo > 0 ? COLORS.danger : COLORS.success }}>{importo(d.saldo)}</span>,
      },
      {
        key: 'verbali',
        label: 'Verbali',
        ruoloCard: 'dettaglio',
        render: d => `${d.verbali} (${d.verbali_aperti} aperti, ${formatEuro(d.verbali_importo)})`,
      },
      { key: 'trattenute', label: 'Trattenute', align: 'right', mono: true, ruoloCard: 'dettaglio', render: d => importo(d.trattenute) },
    ],
    []
  );

  const colonneCandidati = useMemo(
    () => [
      { key: 'data', label: 'Data', ruoloCard: 'sottotitolo', render: c => formatDateIT(c.data) },
      { key: 'controparte', label: 'Controparte', ruoloCard: 'titolo' },
      { key: 'descrizione', label: 'Causale', ruoloCard: 'dettaglio' },
      { key: 'importo', label: 'Importo', align: 'right', mono: true, ruoloCard: 'importo', render: c => importo(c.importo) },
      {
        key: 'per',
        label: 'Manca',
        ruoloCard: 'dettaglio',
        render: c => (c.per === 'verbale' ? 'Verbale da agganciare' : 'Fattura da agganciare'),
      },
      {
        key: 'link',
        label: '',
        ruoloCard: 'azioni',
        render: c => (
          <LinkContropartita compatto to={ROTTE_CONTROPARTITA.movimentoBanca(c.movimento_id)} title={c.descrizione}>
            Apri in riconciliazione
          </LinkContropartita>
        ),
      },
    ],
    []
  );

  if (loading) return <PageLoader />;

  if (errore || !dati) {
    return (
      <PageSection>
        <div role="alert" style={{ color: COLORS.danger, marginBottom: 12 }}>
          Posizione noleggio non disponibile{errore ? `: ${errore}` : ''}.
        </div>
        <Button onClick={carica}>Riprova</Button>
      </PageSection>
    );
  }

  return (
    <div data-testid="posizione-noleggio">
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
          gap: 12,
          marginBottom: 20,
        }}
      >
        <StatCard icon={<FileText size={18} />} label={`Costi ${anno} (Dare)`} value={formatEuro(totali.dare)} accent="primary" />
        <StatCard icon={<Landmark size={18} />} label="Pagato con prova (Avere)" value={formatEuro(totali.avere)} accent="success" />
        <StatCard
          icon={totali.saldo > 0 ? <AlertTriangle size={18} /> : <CheckCircle2 size={18} />}
          label="Saldo aperto"
          value={formatEuro(totali.saldo)}
          accent={totali.saldo > 0 ? 'danger' : 'success'}
          subtext={totali.avere_non_verificato ? `${formatEuro(totali.avere_non_verificato)} dichiarati senza estratto conto` : null}
        />
        <StatCard
          icon={<Receipt size={18} />}
          label="Verbali senza quietanza"
          value={String((controlli.verbali_senza_quietanza || []).length)}
          accent="warning"
        />
        <StatCard
          icon={<UserRound size={18} />}
          label="Auto senza driver"
          value={String((controlli.auto_senza_driver || []).length)}
          accent={(controlli.auto_senza_driver || []).length ? 'warning' : 'success'}
        />
        <StatCard
          icon={<Landmark size={18} />}
          label="Pagamenti da agganciare"
          value={String(controlli.pagamenti_senza_documento || 0)}
          accent={controlli.pagamenti_senza_documento ? 'warning' : 'success'}
          subtext="Uscite verso noleggiatori o Comune senza documento"
        />
      </div>

      {dati.veicoli.length === 0 && (
        <PageSection>
          <div style={{ color: COLORS.textMuted }}>
            Nessuna fattura di noleggio, veicolo o verbale per il {anno}.
          </div>
        </PageSection>
      )}

      {dati.veicoli.map(v => {
        const aperta = !!aperte[v.targa];
        const cessato = ['cessato', 'chiuso', 'archiviato'].includes(String(v.stato_contratto || '').toLowerCase());
        const r = v.riepilogo;
        return (
          <PageSection key={v.targa} style={{ borderLeft: `4px solid ${r.saldo > 0 ? COLORS.warning : COLORS.success}` }}>
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
                gap: 12,
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <Car size={18} color={COLORS.primaryLight} aria-hidden="true" />
                  <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: '-0.02em', fontFamily: 'monospace' }}>
                    {v.targa}
                  </span>
                  <span style={{ fontWeight: 600 }}>{[v.marca, v.modello].filter(Boolean).join(' ') || 'Modello da definire'}</span>
                  <Badge variant={cessato ? 'neutral' : 'info'}>{cessato ? 'Contratto cessato' : 'Contratto attivo'}</Badge>
                </div>
                <div style={{ fontSize: 13, color: COLORS.textMuted, marginTop: 4 }}>
                  {v.fornitore_noleggio || 'Noleggiatore da definire'}
                  {v.contratto ? ` · contratto ${v.contratto}` : ''}
                </div>
              </div>
              <div style={{ textAlign: isMobile ? 'left' : 'right' }}>
                <div style={{ fontSize: 12, color: COLORS.textMuted }}>Saldo aperto</div>
                <div style={{ fontSize: 22, fontWeight: 800, color: r.saldo > 0 ? COLORS.danger : COLORS.success, fontVariantNumeric: 'tabular-nums' }}>
                  {formatEuro(r.saldo)}
                </div>
                <div style={{ fontSize: 12, color: COLORS.textMuted }}>
                  Dare {formatEuro(r.dare)} · Avere {formatEuro(r.avere)}
                </div>
              </div>
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: isMobile ? '1fr' : 'minmax(220px, 1fr) 2fr',
                gap: 16,
                marginTop: 16,
              }}
            >
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: COLORS.textMuted, textTransform: 'uppercase' }}>
                  Driver attuale
                </div>
                <div style={{ fontSize: 15, fontWeight: 700, margin: '4px 0 8px' }}>{nomeDriver(v.driver_attuale)}</div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <Select
                    aria-label={`Assegna driver a ${v.targa}`}
                    value={assegnazione[v.targa] || ''}
                    onChange={e => setAssegnazione(prev => ({ ...prev, [v.targa]: e.target.value }))}
                    style={{ minHeight: 44, minWidth: 180 }}
                  >
                    <option value="">Scegli dipendente…</option>
                    {drivers.map(d => (
                      <option key={d.id} value={d.id}>
                        {d.nome_completo}
                      </option>
                    ))}
                  </Select>
                  <Button
                    size="sm"
                    onClick={() => assegnaDriver(v.targa)}
                    disabled={!assegnazione[v.targa] || salvataggio === v.targa}
                    style={{ minHeight: 44 }}
                  >
                    {salvataggio === v.targa ? 'Salvo…' : 'Assegna'}
                  </Button>
                </div>
                {v.assegnazioni?.length > 0 && (
                  <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 8 }}>
                    Storico:{' '}
                    {v.assegnazioni
                      .map(a => `${a.driver || a.driver_id} dal ${formatDateIT(a.dal)}${a.al ? ` al ${formatDateIT(a.al)}` : ''}`)
                      .join(' · ')}
                  </div>
                )}
              </div>

              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ borderBottom: `2px solid ${COLORS.border}` }}>
                      <th style={{ textAlign: 'left', padding: '6px 8px', fontSize: 11, color: COLORS.textMuted }}>Categoria</th>
                      <th style={{ textAlign: 'right', padding: '6px 8px', fontSize: 11, color: COLORS.textMuted }}>Dare</th>
                      <th style={{ textAlign: 'right', padding: '6px 8px', fontSize: 11, color: COLORS.textMuted }}>Avere</th>
                      <th style={{ textAlign: 'right', padding: '6px 8px', fontSize: 11, color: COLORS.textMuted }}>Saldo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {CATEGORIE.filter(c => r.per_categoria?.[c.key] && (r.per_categoria[c.key].dare || r.per_categoria[c.key].avere)).map(c => {
                      const pc = r.per_categoria[c.key];
                      return (
                        <tr key={c.key} style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                          <td style={{ padding: '6px 8px' }}>{c.label}</td>
                          <td style={{ padding: '6px 8px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{formatEuro(pc.dare)}</td>
                          <td style={{ padding: '6px 8px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{formatEuro(pc.avere)}</td>
                          <td
                            style={{
                              padding: '6px 8px',
                              textAlign: 'right',
                              fontVariantNumeric: 'tabular-nums',
                              fontWeight: 700,
                              color: pc.saldo > 0 ? COLORS.danger : COLORS.success,
                            }}
                          >
                            {formatEuro(pc.saldo)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <div style={{ marginTop: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setAperte(prev => ({ ...prev, [v.targa]: !aperta }))}
                aria-expanded={aperta}
                style={{ minHeight: 44 }}
              >
                {aperta ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                {aperta ? 'Nascondi movimenti' : `Movimenti (${v.righe.length}) e verbali (${v.verbali.length})`}
              </Button>
              {v.fatture_aperte > 0 && <Badge variant="danger">{v.fatture_aperte} fatture senza pagamento</Badge>}
              {v.verbali_aperti > 0 && <Badge variant="warning">{v.verbali_aperti} verbali da pagare</Badge>}
            </div>

            {aperta && (
              <div style={{ marginTop: 12 }}>
                <h4 style={{ margin: '8px 0', fontSize: 14 }}>Prima nota noleggio {v.targa}</h4>
                <ListaAdattiva
                  colonne={colonneRighe}
                  dati={v.righe}
                  pageSize={25}
                  chiave={(riga, i) => `${riga.tipo}-${riga.documento?.id || ''}-${riga.prova?.id || ''}-${i}`}
                  testId={`righe-${v.targa}`}
                />
                <h4 style={{ margin: '16px 0 8px', fontSize: 14 }}>Verbali {v.targa}</h4>
                {v.verbali.length === 0 ? (
                  <div style={{ color: COLORS.textMuted, fontSize: 13 }}>Nessun verbale per questa targa.</div>
                ) : (
                  <ListaAdattiva
                    colonne={colonneVerbali}
                    dati={v.verbali}
                    pageSize={25}
                    chiave={s => s.numero_verbale}
                    testId={`verbali-${v.targa}`}
                  />
                )}
              </div>
            )}
          </PageSection>
        );
      })}

      <PageSection title="Posizione per driver" icon={<UserRound size={16} />}>
        {dati.driver.length === 0 ? (
          <div style={{ color: COLORS.textMuted }}>Nessun movimento attribuibile a un driver.</div>
        ) : (
          <ListaAdattiva
            colonne={colonneDriver}
            dati={dati.driver}
            pageSize={50}
            chiave={(d, i) => d.driver_id || d.driver || `senza-${i}`}
            testId="posizione-driver"
          />
        )}
        <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 8 }}>
          Ogni riga pesa sul driver che aveva l&apos;auto alla data del costo o del verbale, secondo lo storico assegnazioni.
        </div>
      </PageSection>

      <PageSection title="Pagamenti da agganciare" icon={<Landmark size={16} />}>
        {dati.pagamenti_senza_documento.length === 0 ? (
          <div style={{ color: COLORS.success }}>Ogni uscita verso noleggiatori e Comune di Napoli ha il suo documento.</div>
        ) : (
          <ListaAdattiva
            colonne={colonneCandidati}
            dati={dati.pagamenti_senza_documento}
            pageSize={25}
            chiave={c => c.movimento_id}
            testId="pagamenti-candidati"
          />
        )}
        <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 8 }}>
          Il gestionale non aggancia mai per solo importo: l&apos;abbinamento si conferma dalla Riconciliazione bancaria
          (per le fatture) o dalla scheda del verbale (per le quietanze).
        </div>
      </PageSection>

      {controlli.verbali_senza_targa > 0 && (
        <PageSection title="Verbali senza targa" icon={<AlertTriangle size={16} />}>
          <div style={{ fontSize: 13 }}>
            {controlli.verbali_senza_targa} verbali in archivio non dicono a quale auto appartengono
            {(controlli.verbali_senza_targa_esempi || []).length > 0 && (
              <>
                {' '}
                (es. {controlli.verbali_senza_targa_esempi.map(x => x.numero_verbale).join(', ')}
                {controlli.verbali_senza_targa > controlli.verbali_senza_targa_esempi.length ? ', …' : ''})
              </>
            )}
            . Si completano dalla scheda del verbale con targa e importo letti dal PDF.
          </div>
        </PageSection>
      )}
    </div>
  );
}
