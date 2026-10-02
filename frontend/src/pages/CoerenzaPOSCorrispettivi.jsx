/**
 * CoerenzaPOSCorrispettivi.jsx
 *
 * Verifica coerenza tra pagamenti elettronici (POS) e corrispettivi XML
 * Normativa 2026: obbligo abbinamento RT-POS
 */
import React, { useState, useEffect } from 'react';
import { toast } from 'sonner';
import api from '../api';
import {
  formatDateIT,
  useIsMobile,
  RG,
  pagePad,
  COLORS,
  SHADOWS,
  BORDER_RADIUS,
} from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { euroOppure, NON_DISPONIBILE } from '../lib/vista';
import { Button, Badge, Esito, StatCard, Tabs, Input, TableWrap, Table, Th, Td } from '../components/ds';
import { CreditCard, AlertTriangle, CheckCircle, XCircle, RefreshCw, TrendingUp, Calendar, FileWarning, X, ChevronUp, ChevronDown } from 'lucide-react';

export function formatEuroConSegno(amount) {
  if (amount === null || amount === undefined || amount === '' || Number.isNaN(Number(amount))) return NON_DISPONIBILE;
  const valore = Number(amount);
  const segno = valore > 0 ? '+' : valore < 0 ? '-' : '';
  const assoluto = new Intl.NumberFormat('it-IT', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    useGrouping: true,
  }).format(Math.abs(valore));
  return `€ ${segno}${assoluto}`;
}

export function BadgeRiconciliatoBanca({ riconciliato }) {
  return riconciliato
    ? <Badge variant="success">Riconciliato banca</Badge>
    : null;
}

export function calcolaSaldoXmlPos(giorni = []) {
  const confrontabili = giorni.filter(g =>
    g.pos_manuale_presente &&
    !['no_dati', 'in_attesa_xml', 'chiusa_col_giorno_dopo'].includes(g.stato_serale)
  );
  const saldo = Math.round(
    confrontabili.reduce((totale, g) => totale + Number(g.diff_serale || 0), 0) * 100
  ) / 100;
  const direzione = saldo > 0.01 ? 'piu' : saldo < -0.01 ? 'meno' : 'uguale';
  return { saldo, direzione, giorni: confrontabili.length };
}

export default function CoerenzaPOSCorrispettivi() {
  const isMobile = useIsMobile();
  const { anno } = useAnnoGlobale();
  const [loading, setLoading] = useState(true);
  const [dati, setDati] = useState(null);
  const [riepilogoMensile, setRiepilogoMensile] = useState(null);
  // Nuova logica v2: controllo a 2 fasi (aprile 2026)
  const [dueFasi, setDueFasi] = useState(null);
  const [sumup, setSumup] = useState(null);
  const [tab, setTab] = useState('due_fasi');  // nuovo tab default
  const [focusProblemiRequest, setFocusProblemiRequest] = useState(0);
  const [err, setErr] = useState('');

  const apriProblemiDueFasi = () => {
    setTab('due_fasi');
    setFocusProblemiRequest(value => value + 1);
  };

  useEffect(() => {
    loadDati();
  }, [anno]);

  const loadDati = async () => {
    setLoading(true);
    setErr('');
    try {
      const [coerenzaRes, mensileRes, dueFasiRes, sumupRes] = await Promise.all([
        api.get(`/api/pos-corrispettivi/verifica-coerenza?anno=${anno}`),
        api.get(`/api/pos-corrispettivi/riepilogo-mensile?anno=${anno}`),
        api.get(`/api/pos-corrispettivi/controllo-due-fasi?anno=${anno}`),
        api.get(`/api/sumup/riepilogo?anno=${anno}`).catch(error => ({
          data: { configured: false, detail: error.response?.data?.detail || error.message },
        })),
      ]);
      setDati(coerenzaRes.data);
      setRiepilogoMensile(mensileRes.data);
      setDueFasi(dueFasiRes.data);
      setSumup(sumupRes.data);
    } catch (e) {
      setErr('Errore caricamento: ' + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  };

  const getStatoIcon = stato => {
    switch (stato) {
      case 'ok':
        return <CheckCircle size={16} color={COLORS.success} />;
      case 'mancante':
        return <XCircle size={16} color={COLORS.danger} />;
      case 'differenza':
        return <AlertTriangle size={16} color={COLORS.warning} />;
      case 'extra':
        return <FileWarning size={16} color={COLORS.bruno} />;
      default:
        return null;
    }
  };


  if (loading) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <RefreshCw size={32} style={{ animation: 'spin 1s linear infinite', color: COLORS.info }} />
        <p style={{ marginTop: 12, color: COLORS.textMuted }}>Analisi coerenza POS/Corrispettivi...</p>
      </div>
    );
  }

  if (err) {
    return (
      <div
        style={{
          padding: 20,
          background: COLORS.dangerLight,
          borderRadius: BORDER_RADIUS.md,
          color: COLORS.danger,
        }}
      >
        {err}
        <Button variant="danger" size="sm" onClick={loadDati} style={{ marginLeft: 12 }}>
          Riprova
        </Button>
      </div>
    );
  }

  const statsPos = dueFasi?.statistiche || {};
  const gruppiPosVerificati = (statsPos.fase2_ok || 0)
    + (statsPos.fase2_mancante || 0)
    + (statsPos.fase2_diff || 0)
    + (statsPos.fase2_extra || 0);
  const percentualeQuadrata = gruppiPosVerificati > 0
    ? Math.round(((statsPos.fase2_ok || 0) / gruppiPosVerificati) * 1000) / 10
    : 0;

  return (
    <div style={{ padding: 20 }} data-testid="coerenza-pos-page">
      {/* KPI Summary - Compatto */}
      {dueFasi?.statistiche && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(5, 1fr)',
            gap: 12,
            marginBottom: 20,
          }}
        >
          <StatCard
            icon={<CheckCircle size={18} />}
            label="Quadrature POS-Banca"
            value={`${percentualeQuadrata}%`}
            accent="success"
          />
          <StatCard
            icon={<CreditCard size={18} />}
            label="Totale POS reale anno"
            value={euroOppure(statsPos.pos_totale_reale_annuo)}
            subtext={`NUMIA ${euroOppure(statsPos.pos_numia_reale_annuo)} + SUMUP ${euroOppure(statsPos.pos_sumup_reale_annuo)}`}
            accent="info"
          />
          <StatCard
            icon={<TrendingUp size={18} />}
            label="Accrediti bancari reali"
            value={euroOppure(statsPos.fase2_accrediti_totale)}
            accent="accent"
          />
          <StatCard
            icon={<AlertTriangle size={18} />}
            label="Saldo da verificare"
            value={euroOppure(statsPos.fase2_saldo_finale)}
            subtext="Apri i giorni da controllare"
            accent={Math.abs(statsPos.fase2_saldo_finale || 0) > 0.01 ? 'danger' : 'success'}
            onClick={apriProblemiDueFasi}
          />
          <StatCard
            icon={<CreditCard size={18} />}
            label="Venduto SumUp reale"
            value={sumup?.configured ? euroOppure(sumup.totale_venduto) : 'Non configurato'}
            subtext={sumup?.configured ? `${sumup.numero_transazioni || 0} transazioni riuscite` : (sumup?.detail || 'Credenziali assenti')}
            accent={sumup?.configured ? 'info' : 'warning'}
          />
        </div>
      )}
      {(statsPos.fase2_senza_chiusura_terminale || 0) > 0 && (
        <div
          data-testid="avviso-senza-chiusura"
          style={{
            marginTop: -8,
            marginBottom: 16,
            padding: '10px 12px',
            background: COLORS.warningLight,
            borderRadius: BORDER_RADIUS.md,
            color: COLORS.warning,
            fontSize: 13,
          }}
        >
          {TESTO_SENZA_CHIUSURA}: <strong>{statsPos.fase2_senza_chiusura_terminale}</strong>
          {' '}giorni NUMIA, {euroOppure(statsPos.fase2_accrediti_senza_chiusura_totale)} accreditati.
          {' '}Non entrano nelle quadrature né nel saldo: inserisci la chiusura serale per verificarli.
        </div>
      )}
      {(statsPos.fase2_crediti_xml_aperti || 0) > 0 && (
        <div
          data-testid="avviso-credito-xml"
          style={{
            marginTop: -8,
            marginBottom: 16,
            padding: '10px 12px',
            background: COLORS.warningLight,
            borderRadius: BORDER_RADIUS.md,
            color: COLORS.warning,
            fontSize: 13,
          }}
        >
          {TESTO_CREDITO_XML}: <strong>{statsPos.fase2_crediti_xml_aperti}</strong>
          {' '}giorni senza chiusura del terminale, {euroOppure(statsPos.fase2_crediti_xml_aperti_totale)} di credito verso il gestore non ancora provato dalla banca
          {(statsPos.fase2_crediti_xml_differenza_terminale || 0) > 0 && (
            <>, di cui <strong>{statsPos.fase2_crediti_xml_differenza_terminale}</strong> con un totale diverso dal terminale</>
          )}.
          {' '}La chiusura del terminale lo sostituisce, l’accredito al centesimo lo chiude.
        </div>
      )}
      {(statsPos.fase2_duplicati_banca_unificati || 0) > 0 && (
        <div
          style={{
            marginTop: -8,
            marginBottom: 16,
            padding: '10px 12px',
            background: COLORS.infoLight,
            borderRadius: BORDER_RADIUS.md,
            color: COLORS.info,
            fontSize: 13,
          }}
        >
          Fonti bancarie duplicate unificate: <strong>{statsPos.fase2_duplicati_banca_unificati}</strong>
          {' '}su {statsPos.fase2_movimenti_banca_raw || 0} righe sorgente. Le prove originali restano conservate.
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        <Tabs
          items={[
            {
              key: 'due_fasi',
              label: 'Controllo 2 Fasi',
            },
            { key: 'giornaliero', label: 'Giornaliero', icon: <Calendar size={14} /> },
            { key: 'mensile', label: 'Mensile', icon: <TrendingUp size={14} /> },
            {
              key: 'anomalie',
              label: `Anomalie (${dati?.anomalie_count || 0})`,
              icon: <AlertTriangle size={14} />,
            },
          ]}
          value={tab}
          onChange={setTab}
        />
        <Button
          variant="secondary"
          size="sm"
          onClick={loadDati}
          iconLeft={<RefreshCw size={14} />}
          style={{ marginLeft: 'auto' }}
        >
          Aggiorna
        </Button>
      </div>

      {/* Tab nuovo: Controllo 2 Fasi (logica 2026) */}
      {tab === 'due_fasi' && dueFasi && (
        <ControlloDueFasi
          dati={dueFasi}
          isMobile={isMobile}
          onReload={loadDati}
          focusProblemiRequest={focusProblemiRequest}
        />
      )}

      {/* Tab Giornaliero */}
      {tab === 'giornaliero' && dati?.riepilogo_giornaliero && (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Data</Th>
                <Th align="right">Elettronico secondo il registratore</Th>
                <Th align="right">Accreditato su BPM</Th>
                <Th align="right">Differenza</Th>
                <Th align="center">Esito</Th>
              </tr>
            </thead>
            <tbody>
              {dati.riepilogo_giornaliero
                .slice()
                .reverse()
                .map((g, i) => (
                  <tr key={g.data} style={{ borderBottom: `1px solid ${COLORS.gray[100]}` }}>
                    <Td>
                      <span style={{ fontWeight: 600 }}>{formatDateIT(g.data)}</span>
                      <span style={{ marginLeft: 8, fontSize: 11, color: COLORS.textSubtle }}>
                        {g.giorno_settimana}
                      </span>
                    </Td>
                    <Td align="right">{euroOppure(g.elettronico_xml)}</Td>
                    <Td align="right">{euroOppure(g.pos_accreditato)}</Td>
                    <Td align="right">
                      {g.differenza > 0 ? '+' : ''}
                      {euroOppure(g.differenza)}
                    </Td>
                    <Td align="center">
                      <Esito esito={esitoGiorno(g.stato)}>{TESTO_STATO[g.stato] || g.stato}</Esito>
                    </Td>
                  </tr>
                ))}
            </tbody>
          </Table>
        </TableWrap>
      )}

      {/* Tab Mensile — NUMIA e SumUp separati: NUMIA accredita su BPM, SumUp
          paga sulla carta Mastercard SumUp. Il registratore somma tutto
          l'elettronico, quindi si confronta con NUMIA + SumUp. */}
      {tab === 'mensile' && riepilogoMensile?.mesi && (
        <RiepilogoMensilePos riepilogo={riepilogoMensile} anno={anno} />
      )}

      {/* Tab Anomalie */}
      {tab === 'anomalie' && (
        <div>
          {dati?.anomalie?.length === 0 ? (
            <div
              style={{
                padding: 40,
                textAlign: 'center',
                background: COLORS.successLight,
                borderRadius: BORDER_RADIUS.lg,
              }}
            >
              <CheckCircle size={48} color={COLORS.success} />
              <p style={{ marginTop: 12, color: COLORS.success, fontWeight: 600 }}>
                Nessuna anomalia rilevata
              </p>
              <p style={{ fontSize: 13, color: COLORS.textMuted }}>
                I dati POS e corrispettivi XML sono coerenti
              </p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {dati.anomalie.map((a, i) => (
                <div
                  key={a.data}
                  style={{
                    background: COLORS.card,
                    borderRadius: BORDER_RADIUS.lg,
                    border: `1px solid ${COLORS.dangerLight}`,
                    padding: 16,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 16,
                  }}
                >
                  <div
                    style={{
                      width: 48,
                      height: 48,
                      borderRadius: BORDER_RADIUS.md,
                      background: COLORS.dangerLight,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    {getStatoIcon(a.stato)}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>
                      {formatDateIT(a.data)}{' '}
                      <span style={{ fontSize: 12, color: COLORS.textSubtle }}>({a.giorno_settimana})</span>
                    </div>
                    <div style={{ fontSize: 13, color: COLORS.textMuted }}>{a.messaggio}</div>
                    <div style={{ fontSize: 12, marginTop: 4 }}>
                      <span style={{ color: COLORS.info }}>XML: {euroOppure(a.elettronico_xml)}</span>
                      <span style={{ margin: '0 8px', color: COLORS.textSubtle }}>|</span>
                      <span style={{ color: COLORS.bruno }}>POS: {euroOppure(a.pos_accreditato)}</span>
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div
                      style={{
                        fontSize: 18,
                        fontWeight: 700,
                        color: COLORS.danger,
                        marginBottom: 4,
                      }}
                    >
                      {euroOppure(a.differenza)}
                    </div>
                    <div style={{ fontSize: 11, color: COLORS.textMuted }}>
                      Verifica automatica su estratto conto
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Nota normativa */}
      <div
        style={{
          marginTop: 16,
          padding: 12,
          background: COLORS.warningLight,
          borderRadius: BORDER_RADIUS.md,
          fontSize: 12,
          color: COLORS.warning,
          display: 'flex',
          alignItems: 'flex-start',
          gap: 10,
        }}
      >
        <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 2 }} />
        <div>
          <strong>Normativa 2026:</strong> Dal 1° gennaio 2026 è obbligatorio collegare RT e POS.
          Eventuali discrepanze tra corrispettivi e transazioni POS possono generare avvisi
          dall'Agenzia delle Entrate. Accredito POS: Lun-Gio +1g lavorativo, Ven-Dom → Lunedì.
        </div>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════
// COMPONENTE: Controllo Incassi a 2 Fasi (v2 - aprile 2026)
// ═══════════════════════════════════════════════════════════════════════════
//
// Visualizza giorno per giorno:
//   - FASE 1: RT (XML) vs POS reale → errori di battitura + alert compensazione
//   - FASE 2: POS reale vs accredito banca → verifica accrediti
//
// Basato sulla specifica utente (spiegazione_coerenza.xlsx).
// ═══════════════════════════════════════════════════════════════════════════
function ControlloDueFasi({ dati, isMobile, onReload, focusProblemiRequest = 0 }) {
  const stats = dati?.statistiche || {};
  const giorni = dati?.giorni || [];
  const riepilogoSettimanale = dati?.riepilogo_settimanale || [];
  const saldoXmlPos = calcolaSaldoXmlPos(giorni);

  const [filtroStato, setFiltroStato] = useState('tutti'); // tutti | problemi | ok
  const [modalAperta, setModalAperta] = useState(false);
  const [importAperto, setImportAperto] = useState(false);
  const [vista, setVista] = useState('giornaliero'); // giornaliero | settimanale
  const [limiteGiorni, setLimiteGiorni] = useState(200);

  const apriProblemi = () => {
    setVista('giornaliero');
    setFiltroStato('problemi');
    window.setTimeout(() => {
      document.getElementById('pos-giorni-da-verificare')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 0);
  };

  useEffect(() => {
    if (focusProblemiRequest > 0) apriProblemi();
  }, [focusProblemiRequest]);

  const giorniFiltrati = giorni.filter(g => {
    const statoSumUp = (g.fase2_per_circuito || {}).sumup?.stato;
    const sumUpOk = !statoSumUp || statoSumUp === 'no_pos_sumup' ||
      statoSumUp === 'nessun_incasso' || statoSumUp === 'riconciliato';
    if (filtroStato === 'tutti') return true;
    if (filtroStato === 'ok') {
      return g.stato_serale === 'ok' && g.stato_accredito === 'ok' && sumUpOk && g.stato_corrispettivo !== 'manca_xml';
    }
    // problemi: almeno una fase con problemi
    return (!['ok', 'no_dati', 'in_attesa_xml', 'chiusa_col_giorno_dopo'].includes(g.stato_serale)) ||
           (g.stato_accredito !== 'ok' && g.stato_accredito !== 'in_attesa' && g.stato_accredito !== 'no_pos_manuale') ||
           !sumUpOk ||
           creditoXmlAperto(g) ||
           g.stato_corrispettivo === 'manca_xml';
  });

  return (
    <div>
      {/* Toolbar con bottone inserimento manuale */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, alignItems: 'center' }}>
        <Button
          variant="primary"
          onClick={() => setModalAperta(true)}
          style={{ background: COLORS.accent, borderColor: COLORS.accent }}
        >
          + Inserisci chiusura serale
        </Button>
        <Button
          variant="secondary"
          onClick={() => setImportAperto(true)}
          aria-label="Importa totali POS"
        >
          Importa totali POS
        </Button>
        <div style={{ fontSize: 12, color: COLORS.textMuted }}>
          NUMIA si inserisce anche direttamente nella tabella; SumUp arriva dall'API. Ogni circuito salva
          una scrittura distinta in Prima Nota e l'XML resta solo confronto fiscale.
          La differenza è XML − POS: positiva significa che gli scontrini coprono i pagamenti con carta.
        </div>
      </div>

      {modalAperta && (
        <ModalChiusuraSerale
          onClose={() => setModalAperta(false)}
          onSaved={() => {
            setModalAperta(false);
            if (onReload) onReload();
          }}
        />
      )}

      {importAperto && (
        <ModalImportTotaliPos
          onClose={() => setImportAperto(false)}
          onSaved={() => {
            setImportAperto(false);
            if (onReload) onReload();
          }}
        />
      )}

      <div style={{
        background: saldoXmlPos.direzione === 'meno' ? COLORS.warningLight : COLORS.successLight,
        border: `2px solid ${saldoXmlPos.direzione === 'meno' ? COLORS.warning : COLORS.success}`,
        borderRadius: BORDER_RADIUS.lg,
        padding: 16,
        marginBottom: 20,
      }}>
        <strong style={{ fontSize: 15, color: saldoXmlPos.direzione === 'meno' ? COLORS.warning : COLORS.success }}>
          Saldo complessivo XML − POS reale: {formatEuroConSegno(saldoXmlPos.saldo)}
        </strong>
        <div style={{ marginTop: 6, fontSize: 13, color: COLORS.text }}>
          {saldoXmlPos.direzione === 'piu'
            ? `Nel registratore risulta elettronico marcato ${euroOppure(Math.abs(saldoXmlPos.saldo))} IN PIÙ rispetto al terminale POS.`
            : saldoXmlPos.direzione === 'meno'
            ? `Nel registratore risulta elettronico marcato ${euroOppure(Math.abs(saldoXmlPos.saldo))} IN MENO rispetto al terminale POS.`
            : 'Nel totale del periodo, registratore e terminale POS coincidono.'}
          {' '}È un riepilogo informativo di {saldoXmlPos.giorni} giorni confrontabili: non modifica XML né chiusure POS.
        </div>
      </div>

      {/* Statistiche riassuntive */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: isMobile ? 'repeat(2, 1fr)' : 'repeat(5, 1fr)',
        gap: 10,
        marginBottom: 20,
      }}>
        <StatCard
          icon={<FileWarning size={16} />}
          label="XML mancanti (≥7gg)"
          value={stats.fase0_manca_xml || 0}
          subtext={`${stats.fase0_provvisori || 0} provvisori · ${stats.fase0_definitivi_xml || 0} definitivi`}
          accent="accent"
          onClick={apriProblemi}
        />
        <StatCard
          icon={<Calendar size={16} />}
          label="Giorni confrontati"
          value={saldoXmlPos.giorni}
          subtext="con XML e POS reale presenti"
          accent="info"
        />
        <StatCard
          icon={<TrendingUp size={16} />}
          label="Saldo XML − POS reale"
          value={formatEuroConSegno(saldoXmlPos.saldo)}
          subtext="somma delle differenze giornaliere"
          accent={saldoXmlPos.direzione === 'meno' ? 'warning' : 'success'}
        />
        <StatCard
          icon={<CheckCircle size={16} />}
          label="Esito complessivo"
          value={saldoXmlPos.direzione === 'piu' ? 'IN PIÙ' : saldoXmlPos.direzione === 'meno' ? 'IN MENO' : 'COINCIDE'}
          subtext="elettronico marcato nel registratore"
          accent={saldoXmlPos.direzione === 'meno' ? 'warning' : 'success'}
        />
        <StatCard
          icon={<XCircle size={16} />}
          label="Accrediti circuito mancanti"
          value={euroOppure(stats.importo_tot_mancante_banca)}
          subtext={`NUMIA/BPM: ${stats.fase2_mancante || 0} giorni · SumUp payout: ${stats.fase2_sumup_in_attesa_payout || 0}`}
          accent="danger"
          onClick={apriProblemi}
        />
      </div>

      {/* Vista + Filtro */}
      <div id="pos-giorni-da-verificare" style={{ display: 'flex', gap: 6, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center', scrollMarginTop: 16 }}>
        {[
          { k: 'giornaliero', l: 'Giornaliero' },
          { k: 'settimanale', l: 'Settimana per settimana' },
        ].map(o => (
          <Button
            key={o.k}
            size="sm"
            variant={vista === o.k ? 'primary' : 'secondary'}
            onClick={() => setVista(o.k)}
            style={vista === o.k ? { background: COLORS.accent, borderColor: COLORS.accent } : {}}
          >
            {o.l}
          </Button>
        ))}
        <div style={{ width: 1, alignSelf: 'stretch', background: COLORS.border, margin: '2px 4px' }} />
        {vista === 'giornaliero' && [
          { k: 'tutti', l: 'Tutti' },
          { k: 'problemi', l: 'Solo problemi' },
          { k: 'ok', l: 'Solo OK' },
        ].map(o => (
          <Button
            key={o.k}
            size="sm"
            variant={filtroStato === o.k ? 'primary' : 'secondary'}
            onClick={() => setFiltroStato(o.k)}
          >
            {o.l}
          </Button>
        ))}
        {vista === 'giornaliero' && (
          <div style={{ marginLeft: 'auto', fontSize: 12, color: COLORS.textMuted, alignSelf: 'center' }}>
            {giorniFiltrati.length} / {giorni.length} giorni
          </div>
        )}
      </div>

      {vista === 'settimanale' ? (
        <TabellaSettimanale settimane={riepilogoSettimanale} />
      ) : (
      <>
      {/* Tabella giornaliera */}
      <TableWrap>
        <Table>
          <thead>
            <tr style={{ background: COLORS.primary }}>
              <Th style={{ color: '#fff', background: 'transparent' }}>Data</Th>
              <Th align="center" style={{ color: '#fff', background: 'transparent', borderLeft: '2px solid #fff' }}>
                Stato
              </Th>
              <Th colSpan={6} align="center" style={{ color: '#fff', background: 'transparent', borderLeft: '2px solid #fff', borderRight: '2px solid #fff' }}>
                Registratore contro terminali
              </Th>
              <Th colSpan={3} align="center" style={{ color: '#fff', background: 'transparent' }}>
                Dove arrivano i soldi: Numia su BPM, SumUp sulla sua carta
              </Th>
            </tr>
            <tr style={{ background: COLORS.gray[800] }}>
              <Th style={{ color: '#fff', background: 'transparent' }} />
              <Th align="center" style={{ color: '#fff', background: 'transparent', fontSize: 11, borderLeft: '2px solid #fff' }}>Corrispettivo</Th>
              <Th align="right" style={{ color: '#fff', background: 'transparent', fontSize: 11 }}>Elettronico secondo il registratore</Th>
              <Th align="right" style={{ color: '#fff', background: 'transparent', fontSize: 11 }}>POS Numia, chiusura serale</Th>
              <Th align="right" style={{ color: '#fff', background: 'transparent', fontSize: 11 }}>POS SumUp, dall'app</Th>
              <Th align="right" style={{ color: '#fff', background: 'transparent', fontSize: 11 }}>Numia scritto a mano (modifica)</Th>
              <Th align="right" style={{ color: '#fff', background: 'transparent', fontSize: 11, borderRight: '2px solid #fff' }}>Registratore − (Numia + SumUp)</Th>
              <Th align="right" style={{ color: '#fff', background: COLORS.accent, fontSize: 11 }}>POS totale (Numia + SumUp)</Th>
              <Th align="right" style={{ color: '#fff', background: 'transparent', fontSize: 11 }}>Accreditato su BPM</Th>
              <Th align="right" style={{ color: '#fff', background: 'transparent', fontSize: 11 }}>Pagato sulla carta SumUp</Th>
              <Th align="right" style={{ color: '#fff', background: 'transparent', fontSize: 11 }}>Saldo BPM − Numia</Th>
            </tr>
          </thead>
          <tbody>
            {giorniFiltrati.slice(0, limiteGiorni).map((g, i) => (
              <RigaGiornaliera key={g.data} g={g} even={i % 2 === 0} onReload={onReload} />
            ))}
          </tbody>
          {stats && (
            <tfoot>
              <tr style={{ background: COLORS.primary, color: '#fff', fontWeight: 700 }}>
                <Td colSpan={8} align="right" style={{ color: '#fff', background: 'transparent' }}>
                  TOTALE ANNUO POS {euroOppure(stats.pos_totale_reale_annuo)}
                  {' '}= NUMIA {euroOppure(stats.pos_numia_reale_annuo)}
                  {' '}+ SUMUP {euroOppure(stats.pos_sumup_reale_annuo)}
                </Td>
                <Td align="right" style={{ color: '#fff', background: 'transparent' }}>
                  BPM {euroOppure(stats.fase2_accrediti_totale)}
                </Td>
                <Td align="right" style={{ color: '#fff', background: 'transparent' }}>
                  SUMUP {euroOppure(stats.fase2_sumup_pos_totale)}
                </Td>
                <Td align="right" style={{
                  background: 'transparent',
                  color: (stats.fase2_saldo_finale || 0) >= 0 ? COLORS.successLight : COLORS.dangerLight,
                }}>
                  NUMIA Δ {euroOppure(stats.fase2_saldo_finale)}
                </Td>
              </tr>
            </tfoot>
          )}
        </Table>
        {giorniFiltrati.length > limiteGiorni && (
          <div style={{ padding: 12, textAlign: 'center' }}>
            <Button variant="secondary" onClick={() => setLimiteGiorni(l => l + 200)}>
              Mostra altre ({giorniFiltrati.length - limiteGiorni})
            </Button>
          </div>
        )}
        {giorniFiltrati.length === 0 && (
          <div style={{ padding: 40, textAlign: 'center', color: COLORS.textSubtle }}>
            Nessun giorno da mostrare con questo filtro.
          </div>
        )}
      </TableWrap>
      </>
      )}
    </div>
  );
}

// ─── Vista settimanale: quanto incassato vs quanto accreditato, settimana per settimana ───
function TabellaSettimanale({ settimane }) {
  if (!settimane || settimane.length === 0) {
    return (
      <div style={{
        padding: 40, textAlign: 'center', color: COLORS.textSubtle,
        background: COLORS.card, borderRadius: BORDER_RADIUS.lg, border: `1px solid ${COLORS.border}`,
      }}>
        Nessun dato settimanale disponibile per il periodo selezionato.
      </div>
    );
  }
  const statoLabel = {
    ok: 'Chiuso', in_attesa: "In attesa dell'accredito", mancante: 'Manca in banca', differenza: 'Differenza',
    senza_chiusura_terminale: TESTO_SENZA_CHIUSURA,
  };
  const statoEsito = {
    ok: 'chiuso', in_attesa: 'nessun_dato', mancante: 'intervento', differenza: 'verificare',
    senza_chiusura_terminale: 'verificare',
  };
  return (
    <TableWrap>
      <Table>
        <thead>
          <tr style={{ background: COLORS.primary }}>
            <Th style={{ color: '#fff', background: 'transparent' }}>Settimana</Th>
            <Th align="right" style={{ color: '#fff', background: 'transparent' }}>POS Numia</Th>
            <Th align="right" style={{ color: '#fff', background: 'transparent' }}>Accreditato su BPM</Th>
            <Th align="right" style={{ color: '#fff', background: 'transparent' }}>POS SumUp</Th>
            <Th align="right" style={{ color: '#fff', background: 'transparent' }}>BPM − Numia</Th>
            <Th align="center" style={{ color: '#fff', background: 'transparent' }}>Stato</Th>
          </tr>
        </thead>
        <tbody>
          {settimane.map((sw, i) => (
            <tr key={sw.settimana} style={{ background: i % 2 === 0 ? COLORS.card : COLORS.bgAlt, borderBottom: `1px solid ${COLORS.gray[100]}` }}>
              <Td style={{ fontWeight: 600 }}>
                {formatDateIT(sw.data_inizio)} – {formatDateIT(sw.data_fine)}
                <div style={{ fontSize: 10, color: COLORS.textSubtle, fontWeight: 400 }}>
                  {sw.settimana} · {sw.num_giorni_con_pos} giorni con incasso
                </div>
              </Td>
              <Td align="right" style={{ fontWeight: 600 }}>
                {euroOppure(sw.pos_numia_totale)}
              </Td>
              <Td align="right" style={{ fontWeight: 600 }}>
                {sw.accredito_totale > 0 ? euroOppure(sw.accredito_totale) : '—'}
              </Td>
              <Td align="right" style={{ fontWeight: 600 }}>
                {sw.pos_sumup_totale > 0 ? euroOppure(sw.pos_sumup_totale) : '—'}
              </Td>
              <Td align="right" style={{ fontWeight: 700 }}>
                {sw.stato === 'in_attesa' ? '—' : euroOppure(sw.diff_totale)}
              </Td>
              <Td align="center">
                <Esito esito={statoEsito[sw.stato] || 'nessun_dato'}>{statoLabel[sw.stato] || sw.stato}</Esito>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </TableWrap>
  );
}

/**
 * Importo di un singolo circuito POS.
 *
 * Un circuito che non ha ancora risposto NON vale zero: mostrarlo come 0,00
 * farebbe credere che quel terminale non abbia incassato, che e'
 * un'affermazione diversa e potenzialmente falsa. Resta quindi "in attesa".
 */
export function CellaCircuito({ g, circuito }) {
  const valore = (g.pos_per_circuito || {})[circuito];
  const fonte = (g.fonte_pos_per_circuito || {})[circuito];
  const assente = valore === null || valore === undefined;
  const etichettaFonte = {
    api: 'API SumUp',
    api_sumup: 'API SumUp',
    estratto_conto_numia: 'Estratto BPM',
    numia_non_usato_estratto: 'Non usato (estratto BPM)',
    excel: 'Estratto / Excel',
    manuale: 'Manuale',
    inserimento_manuale_terminale: 'Manuale',
    terminale: 'Terminale',
  }[fonte];

  return (
    <Td align="right" style={{ fontSize: 12 }}>
      {assente
        ? <em style={{ color: COLORS.textSubtle, fontSize: 11 }}>in attesa</em>
        : (
          <>
            <div>{euroOppure(valore)}</div>
            {etichettaFonte && (
              <div style={{ color: COLORS.textMuted, fontSize: 10, marginTop: 2 }}>
                {etichettaFonte}
              </div>
            )}
          </>
        )}
    </Td>
  );
}

export function EditorPosReale({ g, onSaved }) {
  const valoreNumia = (g.pos_per_circuito || {}).numia;
  const numiaPresente = valoreNumia !== null && valoreNumia !== undefined;
  const valoreIniziale = numiaPresente
    ? Number(valoreNumia || 0).toFixed(2).replace('.', ',')
    : '';
  const [valore, setValore] = useState(valoreIniziale);
  const [importoSalvato, setImportoSalvato] = useState(
    numiaPresente ? Number(valoreNumia || 0) : null
  );
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    const nuovoNumia = (g.pos_per_circuito || {}).numia;
    const presente = nuovoNumia !== null && nuovoNumia !== undefined;
    setValore(presente
      ? Number(nuovoNumia || 0).toFixed(2).replace('.', ',')
      : '');
    setImportoSalvato(presente ? Number(nuovoNumia || 0) : null);
  }, [g.data, valoreNumia]);

  const normalizzato = String(valore).trim().replace(/\s/g, '').replace(',', '.');
  const importoCorrente = Number(normalizzato);
  const valoreModificato = normalizzato !== '' && (
    !Number.isFinite(importoCorrente)
    || importoSalvato === null
    || Math.round(importoCorrente * 100) !== Math.round(importoSalvato * 100)
  );

  const salva = async () => {
    const importo = importoCorrente;
    if (normalizzato === '' || !Number.isFinite(importo) || importo < 0) {
      toast.error('Inserisci un importo POS valido, anche 0,00');
      return;
    }
    setSalvando(true);
    try {
      const res = await api.put('/api/pos-corrispettivi/chiusura-giornaliera', {
        data: g.data,
        importo,
        gestore: 'numia',
        note: 'Inserimento manuale NUMIA da Coerenza POS',
      });
      setImportoSalvato(importo);
      toast.success(res.data?.message || `POS NUMIA del ${formatDateIT(g.data)} salvato`);
      if (onSaved) await onSaved();
    } catch (e) {
      toast.error('Errore salvataggio POS: ' + (e.response?.data?.detail || e.message));
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div style={{ display: 'flex', gap: 5, justifyContent: 'flex-end', alignItems: 'center', minWidth: 168 }}>
      <Input
        aria-label={`POS NUMIA reale ${g.data}`}
        type="text"
        inputMode="decimal"
        value={valore}
        onChange={e => setValore(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter') salva();
        }}
        placeholder="0,00"
        disabled={salvando}
        style={{ width: 92, textAlign: 'right', padding: '6px 8px', minHeight: 36 }}
      />
      {valoreModificato && (
        <Button
          type="button"
          size="sm"
          variant="primary"
          onClick={salva}
          disabled={salvando}
          aria-label={`Salva POS NUMIA ${g.data}`}
          style={{ minHeight: 36, padding: '6px 9px' }}
        >
          {salvando ? '...' : 'Salva'}
        </Button>
      )}
    </div>
  );
}

function RigaGiornaliera({ g, even, onReload }) {
  const [espansa, setEspansa] = useState(false);
  const [dettaglioBancaAperto, setDettaglioBancaAperto] = useState(false);
  const faseSumUp = (g.fase2_per_circuito || {}).sumup || {};
  const payoutSumUp = faseSumUp.payout;
  const diffSerColor = g.stato_serale === 'ok' ? COLORS.success :
                       g.stato_serale === 'no_dati' || g.stato_serale === 'chiusa_col_giorno_dopo' ? COLORS.textSubtle :
                       g.stato_serale === 'in_attesa_xml' ? COLORS.bruno : COLORS.danger;
  // Regola colori richiesta: differenza POSITIVA (banca ha accreditato di
  // più) → VERDE; NEGATIVA (accredito minore o mancante) → ROSSO.
  const diffAccrColor = g.stato_accredito === 'ok' ? COLORS.success :
                        g.stato_accredito === 'in_attesa' ? COLORS.info :
                        g.stato_accredito === 'no_pos_manuale' ? COLORS.textSubtle :
                        g.stato_accredito === 'raggruppato' ? COLORS.textSubtle :
                        g.stato_accredito === 'mancante' ? COLORS.danger :
                        g.stato_accredito === 'senza_chiusura_terminale' ? COLORS.warning :
                        (g.diff_accredito || 0) >= 0 ? COLORS.success : COLORS.danger;

  const statoAccrLabel = {
    'ok': 'OK',
    'in_attesa': 'In attesa',
    'no_pos_manuale': '—',
    'raggruppato': '↳ nel gruppo',
    'mancante': 'Mancante',
    'differenza': 'Diff.',
    'extra': 'Extra',
    'senza_chiusura_terminale': TESTO_SENZA_CHIUSURA,
  }[g.stato_accredito] || g.stato_accredito;

  // Badge stato corrispettivo (fase 0)
  const statoCorr = g.stato_corrispettivo;
  const statoCorrBadge = {
    'definitivo_xml': { label: 'XML', variant: 'success' },
    'provvisorio': { label: 'Provv.', variant: 'warning' },
    'manca_xml': { label: 'No XML', variant: 'accent' },
    'sconosciuto': { label: '—', variant: 'neutral' },
  }[statoCorr] || { label: '—', variant: 'neutral' };

  return (
    <>
    <tr style={{ background: even ? COLORS.card : COLORS.bgAlt, borderBottom: g.dettaglio_gruppo && espansa ? 'none' : `1px solid ${COLORS.gray[100]}` }}>
      <Td style={{ fontWeight: 600 }}>
        {formatDateIT(g.data)}
      </Td>
      <Td align="center" style={{ borderLeft: `2px solid ${COLORS.border}` }}>
        <Badge variant={statoCorrBadge.variant}>{statoCorrBadge.label}</Badge>
      </Td>
      <Td align="right" style={{ borderLeft: `2px solid ${COLORS.border}` }}>
        {g.xml_elettronico > 0 ? euroOppure(g.xml_elettronico) : (statoCorr !== 'definitivo_xml' ? <em style={{ color: COLORS.textSubtle, fontSize: 11 }}>attendo XML</em> : '—')}
      </Td>
      <CellaCircuito g={g} circuito="numia" />
      <CellaCircuito g={g} circuito="sumup" />
      <Td align="right">
        <EditorPosReale g={g} onSaved={onReload} />
      </Td>
      <Td
        align="right"
        style={{
          borderRight: `2px solid ${COLORS.border}`,
          color: diffSerColor,
          fontWeight: 600,
        }}
      >
        {g.stato_serale === 'no_dati' ? '—'
          : g.stato_serale === 'in_attesa_xml' ? <em style={{ color: COLORS.bruno, fontSize: 11 }}>attendo XML</em>
          : g.stato_serale === 'chiusa_col_giorno_dopo'
            ? <em style={{ fontSize: 11 }}>chiusa il {formatDateIT(g.chiusa_con)}</em>
          : (
            <>
              {formatEuroConSegno(g.diff_serale)}
              {(g.giorni_nella_chiusura || []).length > 0 && (
                <div style={{ fontSize: 11, fontWeight: 400, color: COLORS.textMuted }}>
                  con {g.giorni_nella_chiusura.map(formatDateIT).join(', ')}
                </div>
              )}
            </>
          )}
      </Td>
      <Td align="right">
        {g.pos_totale_giornaliero !== null && g.pos_totale_giornaliero !== undefined
          ? (
            <>
              <div style={{ fontWeight: 800, color: COLORS.primary }}>
                {euroOppure(g.pos_totale_giornaliero)}
              </div>
              <div style={{ fontSize: 10, color: g.pos_totale_completo ? COLORS.success : COLORS.warning, marginTop: 2 }}>
                {g.pos_totale_completo ? 'NUMIA + SUMUP' : 'PARZIALE · circuito mancante'}
              </div>
            </>
          )
          : '—'}
        {g.capogruppo && g.giorni_gruppo > 1 && (
          <Button
            type="button"
            variant="ghost"
            onClick={() => setEspansa(v => !v)}
            style={{
              display: 'block', marginLeft: 'auto', marginTop: 2,
              fontSize: 10, color: COLORS.primary, fontWeight: 700,
              padding: 0, minHeight: 'auto',
              textDecoration: 'underline', textDecorationStyle: 'dotted',
            }}
            title="Mostra il dettaglio giorno per giorno di questo accredito"
          >
            gruppo {g.giorni_gruppo} gg: {euroOppure(g.pos_gruppo)} {espansa ? <ChevronUp size={12} aria-hidden="true" /> : <ChevronDown size={12} aria-hidden="true" />}
          </Button>
        )}
      </Td>
      <Td
        align="right"
        style={{
          color: diffAccrColor,
          fontWeight: 600,
        }}
      >
        {g.accredito_banca > 0 && (
          <Button
            type="button"
            variant="ghost"
            onClick={() => setDettaglioBancaAperto(v => !v)}
            aria-expanded={dettaglioBancaAperto}
            aria-label={`Dettaglio accrediti BPM ${g.data}`}
            style={{
              display: 'block', marginLeft: 'auto', marginBottom: 3,
              padding: 0, minHeight: 'auto', color: 'inherit', fontWeight: 800,
              textDecoration: 'underline', textDecorationStyle: 'dotted',
            }}
            title="Mostra i singoli accrediti BPM che formano il totale"
          >
            {euroOppure(g.accredito_banca)} {dettaglioBancaAperto ? <ChevronUp size={12} aria-hidden="true" /> : <ChevronDown size={12} aria-hidden="true" />}
          </Button>
        )}
        {g.riconciliato_banca_reale ? (
          <BadgeRiconciliatoBanca riconciliato />
        ) : (
          <div style={{ fontSize: 11, textTransform: 'uppercase', fontWeight: 700 }}>
            {statoAccrLabel}
          </div>
        )}
        {g.stato_accredito === 'ok' || g.stato_accredito === 'differenza' || g.stato_accredito === 'extra'
          ? euroOppure(g.diff_accredito)
          : g.stato_accredito === 'mancante'
            ? euroOppure(g.diff_accredito)
            : null}
        {g.numero_movimenti_banca > 0 && (
          <div style={{ fontSize: 10, color: COLORS.textMuted, marginTop: 2 }}>
            BPM · {g.numero_movimenti_banca}{' '}
            {g.numero_movimenti_banca === 1 ? 'movimento' : 'movimenti'}
          </div>
        )}
        {g.credito_pos_da_xml && (
          <div
            data-testid={`credito-xml-${g.data}`}
            style={{
              fontSize: 10, marginTop: 3, fontWeight: 600,
              color: creditoXmlAperto(g) ? COLORS.warning : COLORS.success,
            }}
          >
            {TESTO_CREDITO_XML} {euroOppure(g.credito_pos_da_xml.importo)}
            {' · '}
            {TESTO_CREDITO_XML_STATO[g.credito_pos_da_xml.stato] || g.credito_pos_da_xml.stato}
            {g.credito_pos_da_xml.differenza_terminale !== null
              && g.credito_pos_da_xml.differenza_terminale !== undefined
              && ` (${formatEuroConSegno(g.credito_pos_da_xml.differenza_terminale)})`}
          </div>
        )}
      </Td>
      <Td align="right" style={{ fontWeight: 600 }}>
        {faseSumUp.stato === 'no_pos_sumup' ? '—' : faseSumUp.stato === 'nessun_incasso' ? (
          <Badge variant="neutral">Nessun incasso</Badge>
        ) : (
          <>
            {faseSumUp.stato === 'riconciliato' ? (
              <Badge variant="success">Payout riconciliato</Badge>
            ) : faseSumUp.stato === 'payout_da_verificare' ? (
              <Badge variant="warning">Payout da verificare</Badge>
            ) : (
              <Badge variant="info">In attesa payout</Badge>
            )}
            <div style={{ fontSize: 10, color: COLORS.textMuted, marginTop: 3 }}>
              Mastercard SumUp
            </div>
            {payoutSumUp?.netto_gruppi > 0 && (
              <div style={{ fontSize: 10, color: COLORS.textMuted }}>
                Netto gruppo {euroOppure(payoutSumUp.netto_gruppi)}
                {payoutSumUp.commissioni_gruppi > 0
                  ? ` · costi ${euroOppure(payoutSumUp.commissioni_gruppi)}`
                  : ''}
              </div>
            )}
            {payoutSumUp?.rettifiche_gruppi > 0 && (
              <div style={{ fontSize: 10, color: COLORS.textMuted }}>
                Rettifica SumUp {euroOppure(payoutSumUp.rettifiche_gruppi)}
              </div>
            )}
          </>
        )}
      </Td>
      <Td
        align="right"
        style={{
          fontWeight: 700,
          color: g.saldo_progressivo == null ? COLORS.textSubtle
            : g.saldo_progressivo >= 0 ? COLORS.success : COLORS.danger,
        }}
      >
        {g.saldo_progressivo == null ? '' : euroOppure(g.saldo_progressivo)}
      </Td>
    </tr>
    {g.dettaglio_gruppo && espansa && (
      <tr style={{ background: even ? COLORS.card : COLORS.bgAlt, borderBottom: `1px solid ${COLORS.gray[100]}` }}>
        <Td colSpan={11} style={{ padding: '0 8px 10px 24px' }}>
          <div style={{
            background: COLORS.bgAlt, border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.md,
            padding: '8px 12px', fontSize: 11, color: COLORS.gray[700],
          }}>
            <div style={{ fontWeight: 700, marginBottom: 4, color: COLORS.primary }}>
              Accredito di {euroOppure(g.accredito_banca)} del {formatDateIT(g.data_accredito_attesa)} — da dove arriva:
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <tbody>
                {g.dettaglio_gruppo.map(dg => (
                  <tr key={dg.data}>
                    <td style={{ padding: '2px 8px 2px 0' }}>↳ {formatDateIT(dg.data)}</td>
                    <td style={{ padding: '2px 0', textAlign: 'right', fontWeight: 600 }}>{euroOppure(dg.pos_manuale)}</td>
                  </tr>
                ))}
                <tr style={{ borderTop: `1px solid ${COLORS.border}` }}>
                  <td style={{ padding: '4px 8px 0 0', fontWeight: 700 }}>Totale incassato</td>
                  <td style={{ padding: '4px 0 0', textAlign: 'right', fontWeight: 700 }}>{euroOppure(g.pos_gruppo)}</td>
                </tr>
                <tr>
                  <td style={{ padding: '2px 8px 0 0', fontWeight: 700 }}>Accreditato in banca</td>
                  <td style={{ padding: '2px 0 0', textAlign: 'right', fontWeight: 700 }}>{euroOppure(g.accredito_banca)}</td>
                </tr>
                <tr>
                  <td style={{ padding: '2px 8px 0 0', fontWeight: 700 }}>Differenza</td>
                  <td style={{
                    padding: '2px 0 0', textAlign: 'right', fontWeight: 700,
                    color: g.diff_accredito >= 0 ? COLORS.success : COLORS.danger,
                  }}>{euroOppure(g.diff_accredito)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </Td>
      </tr>
    )}
    {dettaglioBancaAperto && g.accredito_banca > 0 && (
      <tr style={{ background: even ? COLORS.card : COLORS.bgAlt, borderBottom: `1px solid ${COLORS.gray[100]}` }}>
        <Td colSpan={11} style={{ padding: '0 8px 12px 24px' }}>
          <div style={{
            background: COLORS.card, border: `1px solid ${COLORS.border}`,
            borderRadius: BORDER_RADIUS.md, padding: '10px 12px',
          }}>
            <div style={{ fontWeight: 800, color: COLORS.primary, marginBottom: 7 }}>
              Accrediti NUMIA su BPM che compongono {euroOppure(g.accredito_banca)}
            </div>
            {(g.movimenti_banca || []).length > 0 ? (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                <thead>
                  <tr style={{ color: COLORS.textMuted, textAlign: 'left' }}>
                    <th style={{ padding: '3px 8px 5px 0' }}>Data banca</th>
                    <th style={{ padding: '3px 8px 5px 0' }}>Causale</th>
                    <th style={{ padding: '3px 0 5px', textAlign: 'right' }}>Importo</th>
                  </tr>
                </thead>
                <tbody>
                  {(g.movimenti_banca || []).map((movimento, indice) => (
                    <tr key={movimento.id || `${g.data}-${indice}`} style={{ borderTop: `1px solid ${COLORS.gray[100]}` }}>
                      <td style={{ padding: '5px 8px 5px 0', whiteSpace: 'nowrap' }}>
                        {formatDateIT(movimento.data_contabile)}
                      </td>
                      <td style={{ padding: '5px 8px 5px 0', color: COLORS.gray[700] }}>
                        {movimento.descrizione || '—'}
                        {movimento.duplicati_unificati > 0
                          ? ` · ${movimento.duplicati_unificati} copia/e duplicate unificate`
                          : ''}
                      </td>
                      <td style={{ padding: '5px 0', textAlign: 'right', fontWeight: 700 }}>
                        {euroOppure(movimento.importo)}
                      </td>
                    </tr>
                  ))}
                  <tr style={{ borderTop: `2px solid ${COLORS.border}` }}>
                    <td colSpan={2} style={{ padding: '7px 8px 0 0', fontWeight: 800 }}>
                      Totale ricalcolato ({(g.movimenti_banca || []).length} movimenti)
                    </td>
                    <td style={{ padding: '7px 0 0', textAlign: 'right', fontWeight: 800 }}>
                      {euroOppure((g.movimenti_banca || []).reduce(
                        (somma, movimento) => somma + Number(movimento.importo || 0), 0
                      ))}
                    </td>
                  </tr>
                </tbody>
              </table>
            ) : (
              <div style={{ fontSize: 12, color: COLORS.warning }}>
                Il totale è presente, ma il backend non ha restituito il dettaglio delle righe sorgente.
              </div>
            )}
          </div>
        </Td>
      </tr>
    )}
    </>
  );
}


// ═══════════════════════════════════════════════════════════════════════════
// MODALE: Inserimento chiusura serale (corrispettivo manuale + POS reale)
// ═══════════════════════════════════════════════════════════════════════════
// Un form compatto per inserire in un colpo solo i due dati che l'utente ha
// a fine giornata: il totale del corrispettivo e il POS reale battuto.
// Il corrispettivo è marcato come "provvisorio" finché non arriva XML AdE.
// ═══════════════════════════════════════════════════════════════════════════
function ModalChiusuraSerale({ onClose, onSaved }) {
  const oggi = new Date().toISOString().slice(0, 10);
  const [dataForm, setDataForm] = useState(oggi);
  const [totale, setTotale] = useState('');
  const [posReale, setPosReale] = useState('');
  const [note, setNote] = useState('');
  const [salvando, setSalvando] = useState(false);
  const [errore, setErrore] = useState('');

  const salva = async () => {
    if (!dataForm) {
      setErrore('Inserisci la data');
      return;
    }
    const t = parseFloat(totale.replace(',', '.'));
    if (isNaN(t) || t <= 0) {
      setErrore('Il totale corrispettivo deve essere un numero maggiore di 0');
      return;
    }
    const p = posReale ? parseFloat(posReale.replace(',', '.')) : null;
    if (p !== null && (isNaN(p) || p < 0)) {
      setErrore('Il POS reale deve essere un numero >= 0');
      return;
    }

    setSalvando(true);
    setErrore('');
    try {
      await api.post('/api/corrispettivi/manuale', {
        data: dataForm,
        totale: t,
        pos_reale_serale: p,
        note: note || undefined,
      });
      if (onSaved) onSaved();
    } catch (e) {
      setErrore(e?.response?.data?.detail || e?.message || 'Errore salvataggio');
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 10000, padding: 16,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: COLORS.card, borderRadius: BORDER_RADIUS.xl, padding: 20,
          width: '100%', maxWidth: 480,
          boxShadow: SHADOWS.modal,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 17, color: COLORS.text }}>
            Chiusura serale
          </h3>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            style={{ padding: 4 }}
          >
            <X size={18} color={COLORS.textMuted} />
          </Button>
        </div>

        <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 16, lineHeight: 1.5 }}>
          Inserisci il totale del corrispettivo giornaliero (provvisorio) e il POS reale
          letto dall'hardware. Quando arriverà l'XML dall'Agenzia Entrate, il totale sarà
          sostituito automaticamente col dato ufficiale.
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>
            Data
          </label>
          <Input
            type="date"
            value={dataForm}
            max={oggi}
            onChange={e => setDataForm(e.target.value)}
          />
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>
            Totale corrispettivo (€) *
          </label>
          <Input
            type="text"
            inputMode="decimal"
            value={totale}
            onChange={e => setTotale(e.target.value)}
            placeholder="es. 1250,50"
          />
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>
            POS reale dalla chiusura serale (€)
          </label>
          <Input
            type="text"
            inputMode="decimal"
            value={posReale}
            onChange={e => setPosReale(e.target.value)}
            placeholder="es. 450,00 (opzionale)"
          />
          <div style={{ fontSize: 11, color: COLORS.textSubtle, marginTop: 4 }}>
            Facoltativo ma consigliato: il totale battuto al POS fisico (per il confronto con il registratore).
          </div>
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>
            Note
          </label>
          <Input
            type="text"
            value={note}
            onChange={e => setNote(e.target.value)}
            placeholder="Eventuale nota"
          />
        </div>

        {errore && (
          <div style={{
            padding: 10, background: COLORS.dangerLight, border: `1px solid ${COLORS.danger}`,
            color: COLORS.danger, borderRadius: BORDER_RADIUS.sm, fontSize: 13, marginBottom: 12,
          }}>
            {errore}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Button variant="secondary" onClick={onClose} disabled={salvando}>
            Annulla
          </Button>
          <Button
            variant="primary"
            onClick={salva}
            disabled={salvando}
            style={{ background: COLORS.accent, borderColor: COLORS.accent }}
          >
            {salvando ? 'Salvo...' : 'Salva chiusura'}
          </Button>
        </div>
      </div>
    </div>
  );
}


export function parseTotaliPosTesto(testo) {
  const righe = [];
  const dateViste = new Set();
  const linee = String(testo || '').split(/\r?\n/);
  for (let indice = 0; indice < linee.length; indice += 1) {
    const linea = linee[indice].trim();
    if (!linea || /^data\b/i.test(linea)) continue;
    const match = linea.match(/^(\d{4}-\d{2}-\d{2})\s*[;\t]\s*([0-9]+(?:[.,][0-9]{1,2})?)$/);
    if (!match) throw new Error(`Riga ${indice + 1} non valida: usa AAAA-MM-GG;importo`);
    const data = match[1];
    const parsedDate = new Date(`${data}T00:00:00Z`);
    if (Number.isNaN(parsedDate.getTime()) || parsedDate.toISOString().slice(0, 10) !== data) {
      throw new Error(`Data non valida alla riga ${indice + 1}`);
    }
    if (dateViste.has(data)) throw new Error(`Data duplicata: ${data}`);
    dateViste.add(data);
    const importo = Number(match[2].replace(',', '.'));
    if (!Number.isFinite(importo) || importo < 0) {
      throw new Error(`Importo non valido alla riga ${indice + 1}`);
    }
    righe.push({ data, importo: Math.round(importo * 100) / 100 });
  }
  if (!righe.length) throw new Error('Incolla almeno una giornata POS');
  return righe;
}


export function ModalImportTotaliPos({ onClose, onSaved }) {
  const [testo, setTesto] = useState('');
  const [salvando, setSalvando] = useState(false);
  const [errore, setErrore] = useState('');
  let anteprima = null;
  try {
    if (testo.trim()) {
      const righe = parseTotaliPosTesto(testo);
      anteprima = {
        righe,
        totale: righe.reduce((somma, riga) => somma + riga.importo, 0),
      };
    }
  } catch (e) {
    anteprima = { errore: e.message };
  }

  const importa = async () => {
    setErrore('');
    let righe;
    try {
      righe = parseTotaliPosTesto(testo);
    } catch (e) {
      setErrore(e.message);
      return;
    }
    setSalvando(true);
    try {
      const res = await api.post('/api/pos-corrispettivi/chiusure-giornaliere/batch', {
        righe,
        note: 'Import Numia: solo acquisti approvati',
      });
      if (res.data?.errori) {
        setErrore(`${res.data.errori} giornate non sono state salvate`);
        return;
      }
      toast.success(`${res.data?.salvati || righe.length} totali POS importati`);
      if (onSaved) onSaved(res.data);
    } catch (e) {
      setErrore(e?.response?.data?.detail || e?.message || 'Errore importazione');
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 10000, padding: 16,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: COLORS.card, borderRadius: BORDER_RADIUS.xl, padding: 20,
          width: '100%', maxWidth: 620, boxShadow: SHADOWS.modal,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <h3 style={{ margin: 0, fontSize: 17, color: COLORS.text }}>Importa totali POS giornalieri</h3>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Chiudi importazione POS">
            <X size={18} color={COLORS.textMuted} />
          </Button>
        </div>
        <p style={{ fontSize: 12, color: COLORS.textMuted, lineHeight: 1.5 }}>
          Una riga per giorno nel formato <code>AAAA-MM-GG;importo</code>. Il valore diventa il
          POS reale del terminale; il pagamento elettronico XML resta invariato.
        </p>
        <textarea
          aria-label="Totali POS giornalieri"
          value={testo}
          onChange={e => setTesto(e.target.value)}
          placeholder={'2026-07-01;1685,80\n2026-07-02;1666,90'}
          rows={14}
          disabled={salvando}
          style={{
            width: '100%', resize: 'vertical', border: `1px solid ${COLORS.border}`,
            borderRadius: BORDER_RADIUS.md, padding: 10, fontFamily: 'monospace',
            fontSize: 13, color: COLORS.text, background: COLORS.card,
          }}
        />
        {anteprima?.righe && (
          <div style={{ marginTop: 8, fontSize: 12, color: COLORS.success }}>
            {anteprima.righe.length} giornate · totale {euroOppure(anteprima.totale)}
          </div>
        )}
        {(errore || anteprima?.errore) && (
          <div style={{ marginTop: 8, color: COLORS.danger, fontSize: 12 }}>
            {errore || anteprima.errore}
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
          <Button variant="secondary" onClick={onClose} disabled={salvando}>Annulla</Button>
          <Button
            variant="primary"
            onClick={importa}
            disabled={salvando || !anteprima?.righe}
            aria-label="Conferma importazione POS"
          >
            {salvando ? 'Importo...' : 'Importa e aggiorna Prima Nota'}
          </Button>
        </div>
      </div>
    </div>
  );
}


/** Stato della riga giornaliera → esito della regola unica del colore. */
export function esitoGiorno(stato) {
  if (stato === 'ok') return 'chiuso';
  if (stato === 'mancante') return 'intervento';
  if (stato === 'differenza' || stato === 'extra') return 'verificare';
  return 'nessun_dato';
}

/** Giorno NUMIA il cui POS e' letto dall'accredito stesso: niente da verificare. */
export const TESTO_SENZA_CHIUSURA = 'Senza chiusura terminale: accredito non verificabile';

/** Credito POS aperto dal solo XML (nessuna chiusura del terminale). */
export const TESTO_CREDITO_XML = 'Credito POS da XML';
export const TESTO_CREDITO_XML_STATO = {
  senza_chiusura_terminale: 'aperto, senza chiusura terminale',
  differenza_con_chiusura_terminale: 'il terminale dice un altro totale',
  riconciliato: 'chiuso dall’accredito',
};

/** Il credito da XML e' ancora un'attesa (non provato dalla banca). */
export function creditoXmlAperto(g) {
  const credito = g && g.credito_pos_da_xml;
  return Boolean(credito && credito.stato !== 'riconciliato');
}

const TESTO_STATO = {
  ok: 'Chiuso',
  mancante: 'Manca in banca',
  differenza: 'Differenza',
  extra: 'Più del POS',
};

/** Esito del mese secondo la regola unica del colore. */
export function esitoMese(mese) {
  if (mese.stato === 'vuoto') return 'nessun_dato';
  if (mese.stato === 'error') return 'intervento';
  if (mese.stato === 'warning') return 'verificare';
  return 'chiuso';
}

export function RiepilogoMensilePos({ riepilogo, anno }) {
  const [tutte, setTutte] = useState(false);
  const cifra = { fontVariantNumeric: 'tabular-nums' };
  const colonne = [
    { chiave: 'elettronico_xml', titolo: 'Elettronico secondo il registratore' },
    { chiave: 'pos_numia', titolo: 'POS Numia, chiusura serale' },
    { chiave: 'pos_sumup', titolo: "POS SumUp, dall'app" },
    { chiave: 'pos_accreditato', titolo: 'Accreditato su BPM' },
    { chiave: 'sumup_pagato', titolo: 'Pagato sulla carta SumUp' },
    { chiave: 'differenza_xml_pos', titolo: 'Registratore − (Numia + SumUp)', segno: true, extra: true },
    { chiave: 'pos_in_attesa_xml', titolo: 'POS in attesa di XML', extra: true },
    { chiave: 'differenza_pos_banca', titolo: 'BPM − Numia', segno: true, extra: true, assente: 'Non verificabile' },
    { chiave: 'pos_numia_senza_chiusura', titolo: 'Numia senza chiusura (da BPM)', extra: true },
    { chiave: 'sumup_rettifiche', titolo: 'Rettifiche SumUp', extra: true },
    { chiave: 'sumup_commissioni', titolo: 'Commissioni SumUp', extra: true },
    { chiave: 'contanti', titolo: 'Contanti', extra: true },
    { chiave: 'totale_corrispettivi', titolo: 'Corrispettivi', extra: true },
  ].filter(c => tutte || !c.extra);
  const valore = (riga, c) => {
    const v = riga[c.chiave];
    if (v === undefined || v === null) return c.assente || '—';
    return c.segno ? formatEuroConSegno(v) : euroOppure(v);
  };
  return (
    <>
      <p style={{ margin: '0 0 10px', fontSize: 13, color: COLORS.textMuted }}>
        NUMIA si confronta con gli accrediti su BPM; SumUp con i pagamenti sulla sua carta, per data
        del pagamento (un pagamento può coprire più giorni di vendita e non si divide). Il registratore si
        confronta solo con i giorni che hanno l'XML: un giorno chiuso dall'RT col giorno dopo va con quella
        chiusura, uno ancora in attesa di XML resta fuori. I giorni Numia senza chiusura del terminale non
        sono verificabili contro BPM.
      </p>
      <Button variant="secondary" size="sm" onClick={() => setTutte(v => !v)} style={{ marginBottom: 10, minHeight: 44 }}
        data-testid="mensile-tutte-colonne">
        {tutte ? 'Mostra meno colonne' : 'Mostra tutte le colonne'}
      </Button>
      <TableWrap>
        <Table>
          <thead>
            <tr>
              <Th>Mese</Th>
              {colonne.map(c => <Th key={c.chiave} align="right">{c.titolo}</Th>)}
              <Th align="center">Esito</Th>
            </tr>
          </thead>
          <tbody>
            {riepilogo.mesi.map(m => (
              <tr key={m.mese} style={{ borderBottom: `1px solid ${COLORS.gray[100]}` }} data-testid={`mensile-${m.mese}`}>
                <Td style={{ fontWeight: 600 }}>{m.nome} {anno}</Td>
                {colonne.map(c => <Td key={c.chiave} align="right" style={cifra}>{valore(m, c)}</Td>)}
                <Td align="center"><Esito esito={esitoMese(m)} /></Td>
              </tr>
            ))}
            <tr style={{ background: COLORS.bgAlt, fontWeight: 700 }}>
              <Td style={{ fontWeight: 700 }}>Totale {anno}</Td>
              {colonne.map(c => (
                <Td key={c.chiave} align="right" style={{ ...cifra, fontWeight: 700 }}>{valore(riepilogo.totali || {}, c)}</Td>
              ))}
              <Td />
            </tr>
          </tbody>
        </Table>
      </TableWrap>
    </>
  );
}
