import React, { useMemo, useState, useEffect } from 'react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuroD, formatDateIT, useIsMobile } from '../lib/utils';
import { useHashState } from '../hooks/useHashState';
import ModalFattura from '../components/ModalFattura';
import InAttesaDocumento from '../components/InAttesaDocumento';
import AssociaMovimentoBanca from '../components/AssociaMovimentoBanca';
import AssociaAssegnoFattura from '../components/AssociaAssegnoFattura';
import DocumentViewerModal from '../components/DocumentViewerModal';
import FinanziamentoSoci from './FinanziamentoSoci';
import { useConfirm } from '../components/ui/ConfirmDialog';
import {
  Banknote,
  CreditCard,
  Eye,
  FileText,
  Landmark,
  Pencil,
  ReceiptText,
} from 'lucide-react';

/**
 * PRIMA NOTA — ricostruita da zero (richiesta utente 17/07/2026).
 *
 * LOGICA UNICA, SEMPLICE:
 *  - Registro con SALDO PROGRESSIVO CONTINUO: riporto iniziale (modificabile)
 *    + ogni movimento aggiorna il saldo in ordine cronologico.
 *  - CASSA: si alimenta dal corrispettivo giornaliero — il TOTALE in DARE
 *    (entrata "Corrispettivi") e in AVERE la sola quota del PAGAMENTO
 *    ELETTRONICO (uscita "POS Verso Banca"). Più versamenti, prelevamenti
 *    e fatture pagate in contanti.
 *  - BANCA: solo operazioni del gestionale (Corrispettivi POS, Versamenti,
 *    Fatture, Utenze, F24, Stipendi, Assegni, PayPal). L'estratto conto
 *    NON viene sommato qui: sta nella pagina Riconciliazione.
 *  - A video dal più recente al meno recente; dentro la giornata prima
 *    l'entrata del corrispettivo, poi l'uscita POS.
 *
 * Niente card doppie, niente pannelli paralleli: 4 numeri (Riporto,
 * Entrate, Uscite, Saldo) e il registro.
 */

const BLU = '#0f2744';
const VERDE = '#16a34a';
const ROSSO = '#dc2626';
const MESI = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic'];
const PER_PAGINA = 50;

const CATEGORIE = {
  cassa: ['Corrispettivi', 'POS Verso Banca', 'Versamento Banca', 'Prelevamento Banca',
    'Fatture', 'Spese', 'Altro'],
  banca: ['Corrispettivi POS', 'Versamento Banca', 'Prelevamento Banca', 'Fatture', 'Utenze',
    'Pagamento PayPal', 'Rimborso', 'Stipendi', 'Commissioni bancarie', 'Assegni', 'F24', 'Altro'],
};

const eur = v => formatEuroD(v || 0);

function parseImportoIT(input) {
  const v = parseFloat(String(input ?? '').replace(/\./g, '').replace(',', '.'));
  return isNaN(v) ? null : v;
}

const testoRicerca = valore => String(valore ?? '').trim().toLocaleLowerCase('it-IT');

export function etichettaTabProvvisori(provvisori = [], attesaBanca = []) {
  return `\u26a0\ufe0f Da decidere (${provvisori.length}) \u00b7 \ud83c\udfe6 Attesa banca (${attesaBanca.length})`;
}

export function puoAssociareAssegno(pagamento = {}) {
  if (pagamento.fonte_metodo === 'assegno_compilato' || pagamento.assegno_numero) return true;
  const codice = String(pagamento.strumento_bancario?.codice || '').trim().toLowerCase();
  if (!codice) return true;
  return ['assegno', 'altro', 'non_classificato', 'sconosciuto'].includes(codice);
}

export function numeroFatturaMovimento(movimento = {}) {
  return movimento.numero_fattura || movimento.fattura_numero || movimento.invoice_number || '';
}

export function nomeFornitoreMovimento(movimento = {}) {
  const esplicito = movimento.fornitore || movimento.ragione_sociale ||
    movimento.supplier_name || movimento.cedente_denominazione;
  if (esplicito) return esplicito;

  const numero = numeroFatturaMovimento(movimento);
  const sembraFattura = movimento.fattura_id || numero ||
    /fattur|nota credito/i.test(`${movimento.categoria || ''} ${movimento.descrizione || ''}`);
  if (!sembraFattura) return '';

  // Compatibilita' con le righe storiche, che salvavano il fornitore solo
  // nella descrizione: "Pagamento fattura N. - Ragione sociale".
  const descrizione = String(movimento.descrizione || '');
  const separatore = descrizione.indexOf(' - ');
  return separatore >= 0 ? descrizione.slice(separatore + 3).trim() : '';
}

export function dataDocumentoMovimento(movimento = {}) {
  return movimento.data_fattura || movimento.fattura_data || movimento.invoice_date || movimento.data || '';
}

export function filtraMovimentiPrimaNota(movimenti = [], filtri = {}) {
  const numero = testoRicerca(filtri.numeroFattura);
  const fornitore = testoRicerca(filtri.fornitore);
  const data = String(filtri.data || '').trim();
  const generico = testoRicerca(filtri.testo);

  return movimenti.filter(movimento => {
    if (numero && !testoRicerca(numeroFatturaMovimento(movimento)).includes(numero)) return false;
    if (fornitore && !testoRicerca(nomeFornitoreMovimento(movimento)).includes(fornitore)) return false;
    if (data && dataDocumentoMovimento(movimento) !== data) return false;
    if (generico) {
      const campi = [
        movimento.descrizione,
        movimento.numero_assegno || movimento.assegno_numero,
        movimento.importo,
      ];
      if (!campi.some(campo => testoRicerca(campo).includes(generico))) return false;
    }
    return true;
  });
}

export function filtraFattureProvvisorie(fatture = [], filtri = {}) {
  const numero = testoRicerca(filtri.numeroFattura);
  const numeroDdt = testoRicerca(filtri.numeroDdt);
  const fornitore = testoRicerca(filtri.fornitore);
  const data = String(filtri.data || '').trim();
  return fatture.filter(fattura => {
    const numeroFattura = fattura.fattura_numero || fattura.numero_fattura || fattura.invoice_number || '';
    const nomeFornitore = fattura.fornitore || fattura.supplier_name || '';
    const dataFattura = fattura.fattura_data || fattura.data || fattura.invoice_date || '';
    const ddt = (fattura.dati_ddt || []).map(item => item?.numero).filter(Boolean);
    return (!numero || testoRicerca(numeroFattura).includes(numero)) &&
      (!numeroDdt || ddt.some(valore => testoRicerca(valore).includes(numeroDdt))) &&
      (!fornitore || testoRicerca(nomeFornitore).includes(fornitore)) &&
      (!data || dataFattura === data);
  });
}

function FiltriFattura({
  numeroFattura, numeroDdt = '', data, fornitore,
  onNumeroFattura, onNumeroDdt, onData, onFornitore,
}) {
  const stileCampo = {
    display: 'flex', flexDirection: 'column', gap: 5, minWidth: 0,
  };
  const stileLabel = {
    color: '#475569', fontSize: 11, fontWeight: 800, textTransform: 'uppercase',
  };
  const stileInput = {
    width: '100%', minWidth: 0, boxSizing: 'border-box', minHeight: 42,
    padding: '8px 10px', border: '1px solid #cbd5e1', borderRadius: 8,
    background: 'white', color: '#0f172a', fontSize: 13,
  };
  return (
    <div
      data-testid="filtri-fattura-prima-nota"
      style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
        gap: 10, padding: 12, margin: '12px 0 8px', background: '#f8fafc',
        border: '1px solid #dbe4ee', borderRadius: 12,
      }}
    >
      <label style={stileCampo}>
        <span style={stileLabel}>Numero fattura</span>
        <input
          aria-label="Filtra per numero fattura"
          placeholder="Es. V1-8016"
          value={numeroFattura}
          onChange={e => onNumeroFattura(e.target.value)}
          style={stileInput}
        />
      </label>
      {onNumeroDdt && (
        <label style={stileCampo}>
          <span style={stileLabel}>Numero DDT</span>
          <input
            aria-label="Filtra per numero DDT"
            placeholder="Es. DDT862"
            value={numeroDdt}
            onChange={e => onNumeroDdt(e.target.value)}
            style={stileInput}
          />
        </label>
      )}
      <label style={stileCampo}>
        <span style={stileLabel}>Data fattura</span>
        <input
          type="date"
          aria-label="Filtra per data fattura"
          value={data}
          onChange={e => onData(e.target.value)}
          style={stileInput}
        />
      </label>
      <label style={stileCampo}>
        <span style={stileLabel}>Nome fornitore</span>
        <input
          aria-label="Filtra per nome fornitore"
          placeholder="Es. San Carlo"
          value={fornitore}
          onChange={e => onFornitore(e.target.value)}
          style={stileInput}
        />
      </label>
    </div>
  );
}

function BadgeCategoria({ categoria }) {
  const testo = categoria || '—';
  const lower = testo.toLowerCase();
  let Icona = FileText;
  let colore = '#475569';
  if (lower.includes('pos')) { Icona = CreditCard; colore = '#2563eb'; }
  else if (lower.includes('corrispettiv')) { Icona = ReceiptText; colore = '#16a34a'; }
  else if (lower.includes('fattur')) { Icona = FileText; colore = '#3b82f6'; }
  else if (lower.includes('banca') || lower.includes('f24')) { Icona = Landmark; colore = '#0f2744'; }
  else if (lower.includes('cassa') || lower.includes('contant')) { Icona = Banknote; colore = '#15803d'; }
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minHeight: 30, background: '#f1f5f9', borderRadius: 7, padding: '4px 8px', fontSize: 11, fontWeight: 650, color: colore, whiteSpace: 'nowrap' }}>
      <Icona size={15} aria-hidden="true" /> {testo}
    </span>
  );
}

/* ------------------------------ card numero ------------------------------ */
function Card({ titolo, valore, colore, onEdit, testId }) {
  return (
    <div
      style={{
        background: 'white', borderRadius: 12, border: '1px solid #e2e8f0',
        borderLeft: `4px solid ${colore}`, padding: '10px 14px', minWidth: 0,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>
          {titolo}
        </span>
        {onEdit && (
          <button
            onClick={onEdit}
            data-testid={testId}
            title="Modifica"
            style={{
              background: '#fef3c7', border: '1px solid #d97706', borderRadius: 6,
              width: 40, height: 40, display: 'inline-flex', alignItems: 'center',
              justifyContent: 'center', padding: 0, cursor: 'pointer',
            }}
          >
            <Pencil size={18} />
          </button>
        )}
      </div>
      <div
        style={{
          fontSize: 17, fontWeight: 800, color: colore, whiteSpace: 'nowrap',
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
        }}
      >
        {eur(valore)}
      </div>
    </div>
  );
}

/* --------------------------- riparto entrate --------------------------- */
// Distinzione delle ENTRATE per origine (richiesta utente 18/07/2026):
// serve a vedere subito se la riconciliazione POS cassa→banca è coerente
// e a separare versamenti, note di credito e finanziamenti dei soci.
const SOCI_RE = /(vincenzo|antonietta|valerio)\s+ceraldi|ceraldi\s+(vincenzo|antonietta|valerio)|giuseppina\s+pane|pane\s+giuseppina|finanziament\w*\s+soc|apporto\s+soc/i;

function tipoEntrataBanca(m) {
  const t = `${m.categoria || ''} ${m.descrizione || ''} ${m.source || ''}`.toLowerCase();
  // L'API esclude i crediti POS virtuali dal conto Banca. Qui restano solo
  // accrediti effettivi, separati per circuito e quindi verificabili.
  if (/sumup/.test(t) && /payout|accredito|incas|pos/.test(t)) return 'pos_sumup';
  if (/numia|nexi/.test(t) && /accredito|incas|pos/.test(t)) return 'pos_numia';
  if (m.source === 'accredito_payout' || /incas.*p\.o\.s|inc\.pos/.test(t)) return 'pos_altro';
  if (/nota\s*d[i']\s*credito|storno|rimborso/.test(t)) return 'nc';
  if (SOCI_RE.test(t)) return 'soci';
  if (/versament/.test(t)) return 'versamenti';
  if (/paypal/.test(t)) return 'paypal';
  if (/amazon|ecommerce|marketplace/.test(t)) return 'ecommerce';
  if (/chp\s+legal|risarciment|indennizz/.test(t)) return 'legale';
  if (/^\s*\d{4}\b/.test(String(m.categoria || '')) || m.source === 'export_bancario_operativo') return 'storico';
  return 'altro';
}

function tipoEntrataCassa(m) {
  if (m.categoria === 'Corrispettivi') return 'corrispettivi';
  const t = `${m.categoria || ''} ${m.descrizione || ''}`.toLowerCase();
  if (SOCI_RE.test(t)) return 'soci';
  if (/prelevament|prelievo/.test(t)) return 'prelievo';
  return 'altro';
}

const RIGHE_RIPARTO = {
  banca: [
    ['pos_numia', 'Accrediti POS Numia/Nexi su BPM'],
    ['pos_sumup', 'Payout POS SumUp su Mastercard'],
    ['pos_altro', 'Altri accrediti POS su conto'],
    ['versamenti', '💰 Versamenti contanti'],
    ['nc', '↩️ Note di credito / rimborsi'],
    ['soci', '👥 Finanziamento soci'],
    ['paypal', 'Incassi e rimborsi PayPal'],
    ['ecommerce', 'Incassi e rimborsi e-commerce'],
    ['legale', 'Risarcimenti e indennizzi'],
    ['storico', 'Movimenti storici importati da banca'],
    ['altro', 'Entrate bancarie da classificare'],
  ],
  cassa: [
    ['corrispettivi', '🧾 Corrispettivi'],
    ['prelievo', '🏧 Prelievi da banca'],
    ['soci', '👥 Apporto soci'],
    ['altro', '📄 Altre entrate'],
  ],
};

function RipartoEntrate({ sezione, cassa, banca, mese }) {
  const delMese = lista => (mese === null
    ? lista
    : lista.filter(m => parseInt((m.data || '').slice(5, 7), 10) === mese + 1));

  const dati = sezione === 'banca' ? banca : cassa;
  const classifica = sezione === 'banca' ? tipoEntrataBanca : tipoEntrataCassa;

  const { totali, posBanca, posCassa } = useMemo(() => {
    const tot = {};
    delMese(dati.movimenti || []).forEach(m => {
      if (m.tipo !== 'entrata') return;
      const k = classifica(m);
      tot[k] = (tot[k] || 0) + Math.abs(m.importo || 0);
    });
    const pb = delMese(banca.movimenti || [])
      .filter(m => m.tipo === 'entrata' && tipoEntrataBanca(m).startsWith('pos_'))
      .reduce((s, m) => s + Math.abs(m.importo || 0), 0);
    const pc = delMese(cassa.movimenti || [])
      .filter(m => m.tipo === 'uscita' &&
        (/pos(?:\s+(?:numia|nexi|sumup))?\s+verso\s+banca|battuto\s+pos/i.test(m.categoria || '')))
      .reduce((s, m) => s + Math.abs(m.importo || 0), 0);
    return { totali: tot, posBanca: pb, posCassa: pc };
  }, [dati, banca, cassa, mese, sezione]);

  const diffPos = posBanca - posCassa;
  const posOk = Math.abs(diffPos) < 0.01;
  const confrontoPosDisponibile = cassa.loaded === true && banca.loaded === true;
  const righe = RIGHE_RIPARTO[sezione].filter(([k]) => (totali[k] || 0) > 0.004);
  if (righe.length === 0 && (!confrontoPosDisponibile || (posCassa === 0 && posBanca === 0))) return null;

  return (
    <div
      data-testid={`riparto-entrate-${sezione}`}
      style={{
        background: 'white', borderRadius: 12, border: '1px solid #e2e8f0',
        borderLeft: `4px solid ${VERDE}`, padding: '10px 14px', marginTop: 10,
      }}
    >
      <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: 6 }}>
        Dettaglio entrate {mese !== null ? MESI[mese] : ''} per origine
      </div>
      <div style={{ display: 'grid', gap: 4 }}>
        {righe.map(([k, label]) => (
          <div key={k} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 13 }}>
            <span style={{ color: '#334155' }}>{label}</span>
            <b style={{ fontFamily: 'ui-monospace, Menlo, monospace', color: VERDE, whiteSpace: 'nowrap' }}>
              {eur(totali[k])}
            </b>
          </div>
        ))}
      </div>
      {confrontoPosDisponibile && (posCassa > 0 || posBanca > 0) && (
        <div
          style={{
            marginTop: 8, paddingTop: 8, borderTop: '1px dashed #e2e8f0',
            fontSize: 12.5, display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap',
          }}
        >
          <span style={{ color: '#334155' }}>
            {posOk ? '↔️' : '⚠️'} POS reali: chiusure terminali <b>{eur(posCassa)}</b> · accrediti effettivi <b>{eur(posBanca)}</b>
            {posOk && " (quadrati per importo complessivo; il dettaglio resta separato per circuito)"}
          </span>
          {!posOk && (
            <b style={{ color: ROSSO, fontFamily: 'ui-monospace, Menlo, monospace' }}>
              Credito POS ancora da incassare / differenza temporale {eur(posCassa - posBanca)}
            </b>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------ carta Nexi ------------------------------ */
// Le spese carta non arrivano mai in estratto conto bancario, solo
// l'addebito mensile: quando lo vediamo, chiediamo lo statement Nexi se
// manca e mostriamo la quadratura (richiesta utente 18/07/2026).
export function CartaNexi({ anno }) {
  const [stato, setStato] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState('');
  const fileRef = React.useRef(null);
  const richiestaRef = React.useRef(0);

  const carica = async () => {
    const richiesta = ++richiestaRef.current;
    try {
      const r = await api.get(`/api/nexi/stato?anno=${encodeURIComponent(anno)}`);
      if (richiesta === richiestaRef.current) setStato(r.data);
    } catch (e) {
      console.error('Stato Nexi:', e);
    }
  };
  useEffect(() => {
    setStato(null);
    carica();
    return () => { richiestaRef.current += 1; };
  }, [anno]);

  const v = stato?.verifica;
  if (!v || v.addebiti_trovati === 0) return null;

  const upload = async e => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setMsg('');
    try {
      const formData = new FormData();
      formData.append('file', file);
      const r = await api.post('/api/nexi/upload-pdf', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setMsg(r.data.success
        ? `✅ Caricate ${r.data.operazioni} operazioni.`
        : `⚠️ ${r.data.message || 'Import non riuscito'}`);
      carica();
    } catch (e2) {
      setMsg(`❌ ${e2.response?.data?.detail || e2.message}`);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const daCompletare = v.dettagli.filter(d => d.stato !== 'riconciliato');
  if (daCompletare.length === 0) return null;

  return (
    <div
      data-testid="carta-nexi-widget"
      style={{
        background: 'white', borderRadius: 12, border: '1px solid #e2e8f0',
        borderLeft: `4px solid #d97706`, padding: '10px 14px', marginTop: 10,
      }}
    >
      <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: 6 }}>
        💳 Carta Nexi — addebiti da verificare
      </div>
      <div style={{ display: 'grid', gap: 6 }}>
        {daCompletare.map((d, idx) => (
          <div key={`${d.periodo}-${d.data_addebito}-${d.importo}-${idx}`} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 12.5, flexWrap: 'wrap' }}>
            <span style={{ color: '#334155' }}>
              {d.stato === 'estratto_mancante' ? '📎 Manca lo statement' : '⚠️ Non quadra'} — periodo {d.periodo}
              {' '}(addebito {formatDateIT(d.data_addebito)})
            </span>
            <b style={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>
              {eur(d.importo)}
              {d.totale_carta != null && ` (operazioni ${eur(d.totale_carta)}`}
              {d.oneri_carta > 0 && ` + oneri ${eur(d.oneri_carta)}`}
              {d.totale_carta != null && ')'}
            </b>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 8, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <button
          onClick={() => fileRef.current?.click()} disabled={uploading}
          style={{ background: '#d97706', color: 'white', border: 'none', borderRadius: 7, padding: '6px 12px', fontSize: 12.5, fontWeight: 700, cursor: 'pointer', opacity: uploading ? 0.6 : 1 }}
        >
          {uploading ? '⏳ Caricamento…' : '📎 Allega estratto Nexi (PDF)'}
        </button>
        <input ref={fileRef} type="file" accept="application/pdf" onChange={upload} style={{ display: 'none' }} />
        {msg && <span style={{ fontSize: 12, color: '#475569' }}>{msg}</span>}
      </div>
    </div>
  );
}

/* --------------------------- modal movimento --------------------------- */
export function MovimentoModal({ tipo, movimento, onClose, onSaved }) {
  const oggi = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({
    data: movimento?.data?.slice(0, 10) || oggi,
    tipo: movimento?.tipo || 'uscita',
    // Il parser accetta il formato italiano: inizializziamo con la virgola.
    // Con String(1098.28) il punto veniva interpretato come separatore delle
    // migliaia al salvataggio, trasformando 1.098,28 in 109.828,00.
    importo: movimento?.importo != null
      ? Number(movimento.importo).toFixed(2).replace('.', ',')
      : '',
    descrizione: movimento?.descrizione || '',
    categoria: movimento?.categoria || (tipo === 'cassa' ? 'Spese' : 'Altro'),
    numero_assegno: movimento?.numero_assegno || movimento?.assegno_numero || '',
  });
  const [errore, setErrore] = useState('');
  const [saving, setSaving] = useState(false);

  const categorie = CATEGORIE[tipo].includes(form.categoria)
    ? CATEGORIE[tipo]
    : [form.categoria, ...CATEGORIE[tipo]];

  const salva = async () => {
    const importo = parseImportoIT(form.importo);
    if (!form.data || !importo || !form.descrizione.trim()) {
      setErrore('Servono data, importo e descrizione.');
      return;
    }
    setSaving(true);
    setErrore('');
    try {
      const body = { ...form, importo: Math.abs(importo) };
      if (movimento?.id) {
        await api.put(`/api/prima-nota/${tipo}/${movimento.id}`, body);
      } else {
        await api.post(`/api/prima-nota/${tipo}`, body);
      }
      onSaved();
    } catch (e) {
      setErrore(e.response?.data?.message || e.response?.data?.detail || e.message);
      setSaving(false);
    }
  };

  const campo = { width: '100%', padding: '9px 10px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 14, boxSizing: 'border-box' };
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(15,39,68,0.55)', zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 14,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{ background: 'white', borderRadius: 14, padding: 18, width: '100%', maxWidth: 420 }}
      >
        <h3 style={{ margin: '0 0 12px', color: BLU, fontSize: 16 }}>
          {movimento ? '📝 Modifica movimento' : '➕ Nuovo movimento'} — {tipo === 'cassa' ? 'Cassa' : 'Banca'}
        </h3>
        <div style={{ display: 'grid', gap: 10 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <input type="date" value={form.data} onChange={e => setForm({ ...form, data: e.target.value })} style={campo} />
            <select value={form.tipo} onChange={e => setForm({ ...form, tipo: e.target.value })} style={campo}>
              <option value="entrata">Entrata (Dare)</option>
              <option value="uscita">Uscita (Avere)</option>
            </select>
          </div>
          <input
            placeholder="Importo (es. 1.234,56)" inputMode="decimal" value={form.importo}
            onChange={e => setForm({ ...form, importo: e.target.value })} style={campo}
          />
          <input
            placeholder="Descrizione" value={form.descrizione}
            onChange={e => setForm({ ...form, descrizione: e.target.value })} style={campo}
          />
          <select value={form.categoria} onChange={e => setForm({ ...form, categoria: e.target.value })} style={campo}>
            {categorie.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          {tipo === 'banca' && (
            <input
              aria-label="Numero assegno"
              placeholder="Numero assegno (facoltativo)"
              value={form.numero_assegno}
              onChange={e => setForm({ ...form, numero_assegno: e.target.value })}
              style={campo}
            />
          )}
          {errore && <div style={{ color: ROSSO, fontSize: 13 }}>{errore}</div>}
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={onClose} style={{ padding: '9px 16px', borderRadius: 8, border: '1px solid #d1d5db', background: 'white', cursor: 'pointer' }}>
              Annulla
            </button>
            <button
              onClick={salva} disabled={saving}
              style={{ padding: '9px 18px', borderRadius: 8, border: 'none', background: BLU, color: 'white', fontWeight: 700, cursor: 'pointer', opacity: saving ? 0.6 : 1 }}
            >
              {saving ? '⏳…' : '💾 Salva'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------- registro ------------------------------- */
function Registro({ tipo, dati, mese, onRicarica, onModificaRiporto }) {
  const isMobile = useIsMobile();
  const [pagina, setPagina] = useState(1);
  const [cerca, setCerca] = useState('');
  const [fNumeroFattura, setFNumeroFattura] = useState('');
  const [fNumeroDdt, setFNumeroDdt] = useState('');
  const [fDataFattura, setFDataFattura] = useState('');
  const [fFornitore, setFFornitore] = useState('');
  const [fCategoria, setFCategoria] = useState('');
  const [fTipo, setFTipo] = useState('');
  const [editing, setEditing] = useState(null);
  const [nuovo, setNuovo] = useState(false);
  const [fatturaView, setFatturaView] = useState(null);
  const [documentView, setDocumentView] = useState(null);
  const [busy, setBusy] = useState(null);

  const movimenti = dati.movimenti || [];
  const riporto = dati.saldo_precedente || 0;

  useEffect(() => { setPagina(1); }, [
    mese, cerca, fNumeroFattura, fDataFattura, fFornitore, fCategoria, fTipo,
  ]);

  // ORDINE DENTRO LA GIORNATA (regola utente 17/07/2026): prima il
  // CORRISPETTIVO, poi l'uscita del POS, poi i pagamenti delle fatture,
  // per ultimo il versamento in banca. Vale sia a video sia per il
  // calcolo del saldo progressivo.
  const rango = m => {
    if (m.tipo === 'entrata') return m.categoria === 'Corrispettivi' ? 0 : 1;
    if (m.categoria === 'POS Verso Banca' || m.categoria === 'Corrispettivi POS') return 2;
    if (m.categoria === 'Versamento Banca') return 4;
    return 3; // fatture, utenze e altre uscite
  };

  // Ordine del registro A VIDEO: giorni dal più recente, dentro la
  // giornata corrispettivo → POS → fatture → versamento.
  const ordineVideo = (a, b) =>
    (b.data || '').localeCompare(a.data || '') ||
    rango(a) - rango(b) ||
    (a.created_at || '').localeCompare(b.created_at || '');

  // SALDO PROGRESSIVO CONTINUO nell'ORDINE DEL REGISTRO (regola utente
  // 18/07/2026, esempio 20-21/01): si parte dal riporto in fondo e si
  // sale riga per riga — OGNI riga vale la riga sotto ± il suo importo,
  // anche a cavallo dei giorni. La somma è commutativa, quindi i totali
  // di giornata e dell'anno non cambiano; cambia solo il punto in cui
  // ogni singola riga "fotografa" il saldo, che ora segue la lettura.
  // Sempre su TUTTO l'anno, mai sulla selezione filtrata.
  const saldoDi = useMemo(() => {
    const mappa = {};
    let saldo = riporto;
    const lista = [...movimenti].sort(ordineVideo);
    for (let i = lista.length - 1; i >= 0; i--) {
      const m = lista[i];
      saldo += (m.tipo === 'entrata' ? 1 : -1) * Math.abs(m.importo || 0);
      mappa[m.id] = saldo;
    }
    return mappa;
  }, [movimenti, riporto]);

  // Filtri di ricerca + ordine A VIDEO: dal più recente al meno recente,
  // dentro la giornata prima l'entrata (corrispettivo) poi l'uscita (POS).
  const visibili = useMemo(() => {
    let lista = movimenti;
    if (mese !== null) lista = lista.filter(m => parseInt((m.data || '').slice(5, 7), 10) === mese + 1);
    if (fCategoria) lista = lista.filter(m => m.categoria === fCategoria);
    if (fTipo) lista = lista.filter(m => m.tipo === fTipo);
    lista = filtraMovimentiPrimaNota(lista, {
      numeroFattura: fNumeroFattura,
      data: fDataFattura,
      fornitore: fFornitore,
      testo: cerca,
    });
    return [...lista].sort(ordineVideo);
  }, [
    movimenti, mese, fCategoria, fTipo, cerca,
    fNumeroFattura, fDataFattura, fFornitore,
  ]);

  const totPagine = Math.max(1, Math.ceil(visibili.length / PER_PAGINA));
  const paginaCorrente = Math.min(pagina, totPagine);
  const righe = visibili.slice((paginaCorrente - 1) * PER_PAGINA, paginaCorrente * PER_PAGINA);
  const ultimaPagina = paginaCorrente === totPagine;

  const categorieUsate = useMemo(
    () => [...new Set(movimenti.map(m => m.categoria).filter(Boolean))].sort(),
    [movimenti]);

  const sposta = async mov => {
    const verso = tipo === 'cassa' ? 'banca' : 'cassa';
    setBusy(mov.id);
    try {
      await api.post('/api/prima-nota/sposta-movimento', { movimento_id: mov.id, da: tipo, a: verso });
      onRicarica();
    } finally {
      setBusy(null);
    }
  };

  // Evidenza di riconciliazione reale in Banca:
  // - per le fatture (caso Leasys: senza questo, una fattura registrata
  //   non si distingue da una davvero riconciliata con l'estratto conto);
  // - per i trasferimenti POS cassa→banca (l'utente ha fatto notare che
  //   il pareggio cassa=banca è solo coerenza di TRASCRIZIONE — stesso
  //   importo copiato tra i due registri — e non prova che la banca
  //   abbia davvero accreditato quella cifra);
  // - per i pagamenti via PayPal (evidenza reale ma non è l'estratto
  //   conto bancario: testo dedicato, non spacciato per riconciliazione
  //   bancaria).
  // Il backend valorizza mov.riconciliazione solo con un ID di
  // collegamento reale a un movimento/transazione, mai col solo flag
  // booleano "riconciliato" (troppo permissivo: alcuni flussi lo
  // impostano senza nessun riscontro — vedi _arricchisci_riconciliazione
  // in prima_nota_module/banca.py).
  const badgeRiconciliazione = mov => {
    if (tipo !== 'banca' || !mov.riconciliazione) return null;
    const {
      verificata, automatica, match_score, tipo: tipoRic, accreditato_ec,
      importo_atteso, differenza_ec, accredito_trovato,
    } = mov.riconciliazione;
    const isPos = tipoRic === 'pos_trasferimento';
    const isPaypal = tipoRic === 'paypal';
    const isVersamento = tipoRic === 'versamento_contanti';
    if (verificata) {
      const importoInfo = isPos && accreditato_ec ? ` (${eur(accreditato_ec)} accreditati)` : '';
      const title = isPaypal
        ? 'Riconciliato con una transazione PayPal reale'
        : isPos
        ? `Trasferimento POS riconciliato con l'estratto conto${importoInfo}`
        : isVersamento
        ? 'Versamento cassa riconciliato con il movimento reale dell\'estratto conto'
        : (automatica ? `Riconciliato automaticamente con l'estratto conto (punteggio ${match_score ?? '—'})` : "Riconciliato con l'estratto conto");
      return (
        <span
          title={title}
          style={{ background: '#dcfce7', color: '#15803d', border: '1px solid #86efac', borderRadius: 6, padding: '3px 7px', fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap' }}
        >
          ✅ Riconciliato{importoInfo}
        </span>
      );
    }
    const posNonQuadrato = isPos && accredito_trovato;
    const testoPos = posNonQuadrato
      ? `⚠️ Non quadra (${eur(accreditato_ec)} accreditati; differenza ${eur(differenza_ec)})`
      : null;
    return (
      <span
        title={posNonQuadrato
          ? `Accredito POS trovato ma non quadrato: attesi ${eur(importo_atteso)}, accreditati ${eur(accreditato_ec)}, differenza ${eur(differenza_ec)}`
          : isPaypal
          ? "Nessuna transazione PayPal di riscontro trovata: verificare"
          : isPos
          ? "Nessun accredito trovato in estratto conto per questo trasferimento POS: verificare in Coerenza POS"
          : isVersamento
          ? "Versamento registrato in cassa: in attesa del movimento reale nell'estratto conto"
          : "Nessun addebito trovato in estratto conto per questa fattura: verificare in Riconciliazione"}
        style={{ background: '#fef3c7', color: '#b45309', border: '1px solid #fcd34d', borderRadius: 6, padding: '3px 7px', fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap' }}
      >
        {testoPos || '⚠️ Da verificare'}
      </span>
    );
  };

  const badgeDocumento = mov => {
    const pagamento = mov.pagamento_documento || mov.documenti_pagamento?.[0];
    const pulsantePagamento = pagamento ? (
      <button
        type="button"
        onClick={() => setDocumentView({
          fetchUrl: pagamento.view_url,
          title: `Pagamento ${pagamento.nome_file || mov.data || ''}`.trim(),
          subtitle: `${pagamento.data || ''} · ${eur(pagamento.importo || 0)}`,
        })}
        title="Vedi PDF del pagamento"
        aria-label="Vedi PDF del pagamento"
        style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minHeight: 36, background: VERDE, color: 'white', border: 'none', borderRadius: 8, padding: '6px 10px', fontSize: 11, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap' }}
      >
        <ReceiptText size={16} aria-hidden="true" /> Pagamento
      </button>
    ) : null;
    if (mov.fattura_id) {
      return (
        <span style={{ display: 'inline-flex', gap: 6, flexWrap: 'wrap' }}>
          <button
            onClick={() => setFatturaView({ id: mov.fattura_id, numero: mov.numero_fattura })}
            title="Vedi fattura"
            aria-label={`Vedi fattura ${mov.numero_fattura || ''}`.trim()}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minHeight: 36, background: '#3b82f6', color: 'white', border: 'none', borderRadius: 8, padding: '6px 10px', fontSize: 11, fontWeight: 700, cursor: 'pointer' }}
          >
            <FileText size={16} aria-hidden="true" /> Fattura
          </button>
          {pulsantePagamento}
        </span>
      );
    }
    if (pulsantePagamento) return pulsantePagamento;
    if (mov.corrispettivo_id || mov.xml_filename) {
      const href = mov.corrispettivo_id
        ? `/api/corrispettivi/${mov.corrispettivo_id}/view`
        : `/api/corrispettivi/view-by-filename?filename=${encodeURIComponent(mov.xml_filename)}`;
      return (
        <button
          type="button"
          onClick={() => setDocumentView({
            src: href,
            title: `Corrispettivo ${mov.data || ''}`.trim(),
          })}
          title="Vedi corrispettivo"
          aria-label={`Vedi corrispettivo ${mov.data || ''}`.trim()}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minHeight: 36, background: VERDE, color: 'white', border: 'none', borderRadius: 8, padding: '6px 10px', fontSize: 11, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap' }}
        >
          <ReceiptText size={16} aria-hidden="true" /> Corrispettivo
        </button>
      );
    }
    return null;
  };

  const bottoniRiga = mov => (
    <span style={{ display: 'inline-flex', gap: 7, whiteSpace: 'nowrap', alignItems: 'center' }}>
      <button
        onClick={() => sposta(mov)} disabled={busy === mov.id}
        title={tipo === 'cassa' ? 'Sposta in banca' : 'Sposta in cassa'}
        aria-label={tipo === 'cassa' ? 'Sposta in banca' : 'Sposta in cassa'}
        style={{ width: 40, height: 40, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: BLU, color: 'white', border: 'none', borderRadius: 8, padding: 0, cursor: 'pointer', opacity: busy === mov.id ? 0.5 : 1 }}
      >
        {tipo === 'cassa' ? <Landmark size={19} /> : <Banknote size={19} />}
      </button>
      <button
        onClick={() => setEditing(mov)}
        title="Modifica"
        aria-label="Modifica movimento"
        style={{ width: 40, height: 40, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: '#f1f5f9', color: '#334155', border: '1px solid #cbd5e1', borderRadius: 8, padding: 0, cursor: 'pointer' }}
      >
        <Pencil size={18} />
      </button>
    </span>
  );

  const rigaRiporto = (
    <div
      data-testid={`riga-saldo-iniziale-${tipo}`}
      style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8,
        padding: '10px 14px', background: '#fffbeb', border: '1px solid #d97706',
        borderRadius: 10, marginTop: 8,
      }}
    >
      <span style={{ fontSize: 13, fontWeight: 700, color: '#92400e' }}>
        🏁 Saldo iniziale al 01/01 (riporto)
      </span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontWeight: 800, fontFamily: 'ui-monospace, Menlo, monospace', color: riporto >= 0 ? BLU : ROSSO }}>
          {eur(riporto)}
        </span>
        <button
          onClick={onModificaRiporto}
          data-testid={`modifica-saldo-iniziale-${tipo}`}
          title="Modifica saldo iniziale"
          aria-label="Modifica saldo iniziale"
          style={{ width: 40, height: 40, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: '#fef3c7', color: '#92400e', border: '1px solid #d97706', borderRadius: 8, padding: 0, cursor: 'pointer' }}
        >
          <Pencil size={18} />
        </button>
      </span>
    </div>
  );

  // Card giornaliere (mobile) raggruppate per data
  const gruppiGiorno = useMemo(() => {
    const gruppi = [];
    righe.forEach(m => {
      const ultimo = gruppi[gruppi.length - 1];
      if (!ultimo || ultimo.data !== m.data) gruppi.push({ data: m.data, righe: [] });
      gruppi[gruppi.length - 1].righe.push(m);
    });
    return gruppi;
  }, [righe]);

  const stileInput = { padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 13, minWidth: 0 };

  return (
    <div>
      <FiltriFattura
        numeroFattura={fNumeroFattura}
        data={fDataFattura}
        fornitore={fFornitore}
        onNumeroFattura={setFNumeroFattura}
        onData={setFDataFattura}
        onFornitore={setFFornitore}
      />
      {/* filtri + nuovo movimento */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '12px 0' }}>
        <input
          aria-label="Cerca in descrizione, importo o assegno"
          placeholder="🔍 Descrizione, importo o assegno…" value={cerca} onChange={e => setCerca(e.target.value)}
          style={{ ...stileInput, flex: '1 1 140px' }}
        />
        <select value={fCategoria} onChange={e => setFCategoria(e.target.value)} style={stileInput}>
          <option value="">Tutte le categorie</option>
          {categorieUsate.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={fTipo} onChange={e => setFTipo(e.target.value)} style={stileInput}>
          <option value="">Dare + Avere</option>
          <option value="entrata">Solo Dare ↑</option>
          <option value="uscita">Solo Avere ↓</option>
        </select>
        <button
          onClick={() => setNuovo(true)}
          style={{ background: BLU, color: 'white', border: 'none', borderRadius: 8, padding: '8px 14px', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}
        >
          ➕ Nuovo
        </button>
      </div>

      {/* paginazione */}
      {totPagine > 1 && (
        <div
          style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            background: BLU, color: 'white', borderRadius: 10, padding: '8px 12px', marginBottom: 10, fontSize: 13,
          }}
        >
          <span>📄 {paginaCorrente}/{totPagine} — {visibili.length} movimenti</span>
          <span style={{ display: 'flex', gap: 4 }}>
            {[['«', 1], ['‹', paginaCorrente - 1], ['›', paginaCorrente + 1], ['»', totPagine]].map(([s, p]) => (
              <button
                key={s} onClick={() => setPagina(Math.min(totPagine, Math.max(1, p)))}
                aria-label={s === '«' ? 'Prima pagina' : s === '‹' ? 'Pagina precedente' : s === '›' ? 'Pagina successiva' : 'Ultima pagina'}
                style={{
                  width: 42, height: 42, border: `2px solid ${BLU}`,
                  background: 'white', color: BLU, borderRadius: 8, padding: 0,
                  cursor: 'pointer', fontSize: 22, fontWeight: 900,
                  lineHeight: 1, opacity: (p < 1 || p > totPagine) ? 0.45 : 1,
                }}
              >
                {s}
              </button>
            ))}
          </span>
        </div>
      )}

      {righe.length === 0 && (
        <div style={{ padding: 30, textAlign: 'center', color: '#6b7280', background: 'white', borderRadius: 12, border: '1px solid #e2e8f0' }}>
          Nessun movimento{mese !== null ? ` a ${MESI[mese]}` : ''}.
        </div>
      )}

      {isMobile ? (
        /* ------------------- MOBILE: card per giornata ------------------- */
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {gruppiGiorno.map(g => {
            const netto = g.righe.reduce((s, m) => s + (m.tipo === 'entrata' ? 1 : -1) * Math.abs(m.importo || 0), 0);
            return (
              <div key={g.data} style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                <div
                  style={{
                    display: 'flex', justifyContent: 'space-between', gap: 8, padding: '6px 11px',
                    background: BLU, color: 'white', borderRadius: 8, fontSize: 12.5, fontWeight: 700,
                  }}
                >
                  <span>📅 {formatDateIT(g.data)}</span>
                  <span style={{ fontFamily: 'ui-monospace, Menlo, monospace', color: netto >= 0 ? '#86efac' : '#fca5a5' }}>
                    {netto >= 0 ? '+' : ''}{eur(netto)}
                  </span>
                </div>
                {g.righe.map(m => (
                  <div
                    key={m.id}
                    data-testid={`movimento-card-${m.id}`}
                    style={{
                      background: 'white', borderRadius: 11, border: '1px solid #e2e8f0',
                      borderLeft: `4px solid ${m.tipo === 'entrata' ? VERDE : ROSSO}`, padding: '9px 12px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
                      <BadgeCategoria categoria={m.categoria} />
                      <span
                        style={{
                          fontWeight: 800, whiteSpace: 'nowrap', fontFamily: 'ui-monospace, Menlo, monospace',
                          color: m.tipo === 'entrata' ? VERDE : ROSSO,
                        }}
                      >
                        {m.tipo === 'entrata' ? '+' : '−'}{eur(Math.abs(m.importo))}
                      </span>
                    </div>
                    <div style={{ fontSize: 12.5, color: '#334155', margin: '5px 0', wordBreak: 'break-word' }}>
                      {m.descrizione || '—'}
                      {tipo === 'banca' && (m.numero_assegno || m.assegno_numero) && (
                        <div style={{ marginTop: 3, color: '#1d4ed8', fontWeight: 700 }}>
                          Assegno n. {m.numero_assegno || m.assegno_numero}
                        </div>
                      )}
                    </div>
                    {(numeroFatturaMovimento(m) || nomeFornitoreMovimento(m)) && (
                      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 8, margin: '5px 0 8px', fontSize: 11.5 }}>
                        <div style={{ minWidth: 0 }}>
                          <span style={{ color: '#64748b' }}>Fornitore</span>
                          <div style={{ fontWeight: 700, color: BLU, wordBreak: 'break-word' }}>
                            {nomeFornitoreMovimento(m) || '—'}
                          </div>
                        </div>
                        <div style={{ minWidth: 0 }}>
                          <span style={{ color: '#64748b' }}>N. fattura</span>
                          <div style={{ fontWeight: 700, color: BLU, wordBreak: 'break-all' }}>
                            {numeroFatturaMovimento(m) || '—'}
                          </div>
                        </div>
                      </div>
                    )}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 11.5, color: '#64748b' }}>
                        Saldo:{' '}
                        <b style={{ color: (saldoDi[m.id] ?? 0) >= 0 ? VERDE : ROSSO, fontFamily: 'ui-monospace, Menlo, monospace' }}>
                          {eur(saldoDi[m.id])}
                        </b>
                      </span>
                      <span style={{ display: 'flex', gap: 5, alignItems: 'center', flexWrap: 'wrap' }}>
                        {badgeDocumento(m)}
                        {badgeRiconciliazione(m)}
                        {bottoniRiga(m)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            );
          })}
          {ultimaPagina && rigaRiporto}
        </div>
      ) : (
        /* ------------------------ DESKTOP: tabella ----------------------- */
        <div style={{ background: 'white', borderRadius: 12, border: '1px solid #e2e8f0', overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e2e8f0' }}>
                {[
                  ['Data', 'left'], ['Fornitore', 'left'], ['N. fattura', 'left'],
                  ['Categoria', 'left'], ['Descrizione', 'left'], ['Dare', 'right'],
                  ['Avere', 'right'], ['Saldo', 'right'], ['Doc.', 'center'], ['Azioni', 'center'],
                ].map(([h, allineamento]) => (
                  <th
                    key={h}
                    style={{
                      padding: '9px 10px', fontSize: 11, color: '#64748b', textTransform: 'uppercase',
                      textAlign: allineamento,
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {righe.map((m, i) => (
                <tr
                  key={m.id}
                  data-testid={`movimento-row-${m.id}`}
                  style={{ borderBottom: '1px solid #f1f5f9', background: i % 2 ? '#f8fafc' : 'white' }}
                >
                  <td style={{ padding: '7px 10px', fontFamily: 'monospace', whiteSpace: 'nowrap' }}>{formatDateIT(m.data)}</td>
                  <td style={{ padding: '7px 10px', minWidth: 155, maxWidth: 230, fontWeight: 700, color: BLU, wordBreak: 'break-word' }}>
                    {nomeFornitoreMovimento(m) || '—'}
                  </td>
                  <td style={{ padding: '7px 10px', minWidth: 110, maxWidth: 180, fontFamily: 'ui-monospace, Menlo, monospace', wordBreak: 'break-all' }}>
                    {numeroFatturaMovimento(m) || '—'}
                  </td>
                  <td style={{ padding: '7px 10px' }}>
                    <BadgeCategoria categoria={m.categoria} />
                  </td>
                  <td style={{ padding: '7px 10px', minWidth: 210, maxWidth: 360, wordBreak: 'break-word' }}>
                    {m.descrizione || '—'}
                    {tipo === 'banca' && (m.numero_assegno || m.assegno_numero) && (
                      <div style={{ marginTop: 3, color: '#1d4ed8', fontWeight: 700, fontSize: 11 }}>
                        Assegno n. {m.numero_assegno || m.assegno_numero}
                      </div>
                    )}
                  </td>
                  <td style={{ padding: '7px 10px', textAlign: 'right', color: VERDE, fontWeight: m.tipo === 'entrata' ? 700 : 400, fontFamily: 'ui-monospace, Menlo, monospace', whiteSpace: 'nowrap' }}>
                    {m.tipo === 'entrata' ? eur(m.importo) : '—'}
                  </td>
                  <td style={{ padding: '7px 10px', textAlign: 'right', color: ROSSO, fontWeight: m.tipo === 'uscita' ? 700 : 400, fontFamily: 'ui-monospace, Menlo, monospace', whiteSpace: 'nowrap' }}>
                    {m.tipo === 'uscita' ? eur(m.importo) : '—'}
                  </td>
                  <td style={{ padding: '7px 10px', textAlign: 'right', fontWeight: 800, color: (saldoDi[m.id] ?? 0) >= 0 ? VERDE : ROSSO, fontFamily: 'ui-monospace, Menlo, monospace', whiteSpace: 'nowrap' }}>
                    {eur(saldoDi[m.id])}
                  </td>
                  <td style={{ padding: '7px 10px', textAlign: 'center' }}>
                    <span style={{ display: 'inline-flex', gap: 5, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'center' }}>
                      {badgeDocumento(m) || '—'}
                      {badgeRiconciliazione(m)}
                    </span>
                  </td>
                  <td style={{ padding: '7px 10px', textAlign: 'center' }}>{bottoniRiga(m)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {ultimaPagina && <div style={{ padding: '0 10px 10px' }}>{rigaRiporto}</div>}
        </div>
      )}

      {(nuovo || editing) && (
        <MovimentoModal
          tipo={tipo}
          movimento={editing}
          onClose={() => { setNuovo(false); setEditing(null); }}
          onSaved={() => { setNuovo(false); setEditing(null); onRicarica(); }}
        />
      )}
      {fatturaView && (
        <ModalFattura fatturaId={fatturaView.id} numero={fatturaView.numero} onClose={() => setFatturaView(null)} />
      )}
      {documentView && (
        <DocumentViewerModal
          title={documentView.title}
          subtitle={documentView.subtitle}
          src={documentView.src}
          fetchUrl={documentView.fetchUrl}
          documentType="documento_fiscale"
          onClose={() => setDocumentView(null)}
        />
      )}
    </div>
  );
}

/* ------------------------------ provvisori ------------------------------ */
export function Provvisori({ provvisori, attesaBanca = [], tutteFatture = [], completezza = null, onRicarica }) {
  const confirm = useConfirm();
  const [busy, setBusy] = useState(null);
  const [parziale, setParziale] = useState(null);
  const [importoCassa, setImportoCassa] = useState('');
  const [errore, setErrore] = useState('');
  const [erroreRiga, setErroreRiga] = useState(null);
  const [esito, setEsito] = useState('');
  const [fNumeroFattura, setFNumeroFattura] = useState('');
  const [fNumeroDdt, setFNumeroDdt] = useState('');
  const [fDataFattura, setFDataFattura] = useState('');
  const [fFornitore, setFFornitore] = useState('');
  // Richiesta utente 19/07/2026: da Provvisori non si poteva mai aprire la
  // fattura per controllarla prima di confermare cassa/banca — a differenza
  // del Registro (badgeDocumento), qui non c'era nessun modo di vederla.
  const [fatturaView, setFatturaView] = useState(null);
  const [associaFattura, setAssociaFattura] = useState(null);
  // Selezione multipla (richiesta utente 07/08/2026): confermare una
  // fattura alla volta ricaricava la pagina a ogni clic. Qui si spuntano
  // N fatture e si registra tutto con UNA chiamata e UNA ricarica.
  const [selezionate, setSelezionate] = useState(() => new Set());
  const [esitiMultipli, setEsitiMultipli] = useState(null);
  const [busyMultiplo, setBusyMultiplo] = useState(false);
  const [modalitaRapida, setModalitaRapida] = useState(false);
  const [vista, setVista] = useState('da_lavorare');
  const [paginaTutte, setPaginaTutte] = useState(1);
  const righePerPagina = 100;
  const filtriFattura = {
    numeroFattura: fNumeroFattura,
    numeroDdt: fNumeroDdt,
    data: fDataFattura,
    fornitore: fFornitore,
  };
  const provvisoriVisibili = useMemo(
    () => filtraFattureProvvisorie(provvisori, filtriFattura),
    [provvisori, fNumeroFattura, fNumeroDdt, fDataFattura, fFornitore],
  );
  const attesaBancaVisibili = useMemo(
    () => filtraFattureProvvisorie(attesaBanca, filtriFattura),
    [attesaBanca, fNumeroFattura, fNumeroDdt, fDataFattura, fFornitore],
  );
  const tutteFattureVisibili = useMemo(
    () => filtraFattureProvvisorie(tutteFatture, filtriFattura),
    [tutteFatture, fNumeroFattura, fNumeroDdt, fDataFattura, fFornitore],
  );
  const pagineTutte = Math.max(1, Math.ceil(tutteFattureVisibili.length / righePerPagina));
  const paginaTutteSicura = Math.min(paginaTutte, pagineTutte);
  const tutteFatturePagina = tutteFattureVisibili.slice(
    (paginaTutteSicura - 1) * righePerPagina,
    paginaTutteSicura * righePerPagina,
  );
  useEffect(() => {
    setPaginaTutte(1);
  }, [fNumeroFattura, fNumeroDdt, fDataFattura, fFornitore, tutteFatture.length]);

  const dettaglioDdt = p => {
    const riferimenti = p.dati_ddt || [];
    if (riferimenti.length === 0) return null;
    return (
      <div style={{ marginTop: 3, color: '#7c3aed', fontSize: 11.5, fontWeight: 700 }}>
        {riferimenti.map((ddt, indice) => {
          const distanza = Number.isFinite(ddt.giorni_prima_fattura)
            ? ` · ${ddt.giorni_prima_fattura} gg prima della fattura`
            : '';
          return (
            <span key={`${ddt.numero || 'ddt'}-${ddt.data || indice}`}>
              {indice > 0 && ' · '}
              DDT {ddt.numero || 'senza numero'} del {formatDateIT(ddt.data)}{distanza}
            </span>
          );
        })}
      </div>
    );
  };

  const dettaglioDdtCompleto = p => {
    const dettaglio = dettaglioDdt(p);
    if (dettaglio) return dettaglio;
    const testo = p.stato_ddt === 'non_indicato_nell_xml'
      ? 'DDT non indicato nella fattura XML'
      : 'DDT non disponibile: XML originale non presente nel record';
    return (
      <div style={{ marginTop: 3, color: '#64748b', fontSize: 11.5 }}>
        {testo}
      </div>
    );
  };

  const bottoneVedi = p => (
    <button
      onClick={() => setFatturaView({ id: p.fattura_id, numero: p.fattura_numero })}
      title="Vedi fattura"
      aria-label={`Vedi fattura ${p.fattura_numero || ''}`.trim()}
      style={{ minHeight: 40, display: 'inline-flex', alignItems: 'center', gap: 6, background: '#f1f5f9', color: '#334155', border: '1px solid #cbd5e1', borderRadius: 8, padding: '7px 10px', fontSize: 12.5, fontWeight: 700, cursor: 'pointer' }}
    >
      <Eye size={17} /> Vedi fattura
    </button>
  );

  const commuta = id => setSelezionate(prev => {
    const nuovo = new Set(prev);
    if (nuovo.has(id)) nuovo.delete(id); else nuovo.add(id);
    return nuovo;
  });

  const confermaMultipla = async metodo => {
    const ids = [...selezionate];
    if (ids.length === 0) return;
    const testo = metodo === 'cassa'
      ? `Registri in Prima Nota Cassa ${ids.length} fatture come pagate in contanti?`
      : `Sposti ${ids.length} fatture tra i pagamenti attesi in banca?`;
    const approvato = await confirm({
      title: metodo === 'cassa' ? 'Registrazione multipla in Cassa' : 'Attesa banca multipla',
      message: testo,
      confirmText: metodo === 'cassa' ? `Registra ${ids.length} in Cassa` : `Attendi banca (${ids.length})`,
      cancelText: 'Annulla',
      variant: 'warning',
    });
    if (!approvato) return;
    setBusyMultiplo(true);
    setEsitiMultipli(null);
    setErrore('');
    try {
      const { data } = await api.post('/api/prima-nota/provvisori/conferma-multipla', {
        fattura_ids: ids,
        metodo: metodo === 'cassa' ? 'cassa' : 'attendi_banca',
      });
      setEsitiMultipli(data);
      setSelezionate(new Set(
        (data.esiti || []).filter(e => !e.success).map(e => e.fattura_id)
      ));
      await onRicarica({ silent: true });
    } catch (e) {
      setErrore(e.response?.data?.detail || e.message);
    } finally {
      setBusyMultiplo(false);
    }
  };

  const conferma = async (p, metodo, opzioni = {}) => {
    setBusy(p.fattura_id);
    setErrore('');
    setErroreRiga(null);
    setEsito('');
    try {
      await api.post('/api/prima-nota/provvisori/conferma', {
        fattura_id: p.fattura_id,
        metodo,
        ...opzioni,
      });
      await onRicarica({ silent: true });
    } catch (e) {
      setErroreRiga({
        fatturaId: p.fattura_id,
        messaggio: e.response?.data?.detail || e.response?.data?.message || e.message,
      });
    } finally {
      setBusy(null);
    }
  };

  const confermaCassa = async p => {
    if (modalitaRapida) {
      await conferma(p, 'cassa', { approva_metodo_fattura: true });
      return;
    }
    const numero = p.fattura_numero || p.numero_fattura || p.invoice_number || 'senza numero';
    const fornitore = p.fornitore || p.supplier_name || 'Fornitore';
    const approvato = await confirm({
      title: 'Conferma pagamento in contanti',
      message: `Confermi che la fattura ${numero} di ${fornitore}, per ${eur(p.importo)}, e' stata pagata in contanti?\n\nVerra' registrata in Prima Nota Cassa. Il metodo predefinito del fornitore non verra' modificato.`,
      confirmText: 'Registra in Cassa',
      cancelText: 'Annulla',
      variant: 'warning',
    });
    if (!approvato) return;
    await conferma(p, 'cassa', { approva_metodo_fattura: true });
  };

  const attendiBanca = async p => {
    setBusy(p.fattura_id);
    setErrore('');
    setErroreRiga(null);
    setEsito('');
    try {
      const response = await api.post('/api/prima-nota/provvisori/attendi-banca', {
        fattura_id: p.fattura_id,
      });
      setEsito(response.data?.message || 'Fattura spostata tra i pagamenti attesi in banca.');
      await onRicarica({ silent: true });
    } catch (e) {
      setErroreRiga({
        fatturaId: p.fattura_id,
        messaggio: e.response?.data?.detail || e.response?.data?.message || e.message,
      });
    } finally {
      setBusy(null);
    }
  };

  const riportaDaDecidere = async p => {
    setBusy(p.fattura_id);
    setErrore('');
    setErroreRiga(null);
    setEsito('');
    try {
      const response = await api.post('/api/prima-nota/provvisori/da-decidere', {
        fattura_id: p.fattura_id,
      });
      const riferimento = response.data?.fattura || {};
      const numero = riferimento.numero || p.fattura_numero || p.numero_fattura || p.invoice_number || 'senza numero';
      const fornitore = riferimento.fornitore || p.fornitore || p.supplier_name || 'Fornitore non disponibile';
      const dataFattura = riferimento.data || p.fattura_data || p.data || p.invoice_date;
      const importo = riferimento.importo ?? p.importo;
      setEsito(response.data?.message || (
        `Fattura ${numero} di ${fornitore}, del ${formatDateIT(dataFattura)}, ${eur(importo)}, `
        + 'riportata in Da decidere. Ora puoi scegliere Cassa, Banca o Parziale.'
      ));
      await onRicarica({ silent: true });
    } catch (e) {
      setErroreRiga({
        fatturaId: p.fattura_id,
        messaggio: e.response?.data?.detail || e.response?.data?.message || e.message,
      });
    } finally {
      setBusy(null);
    }
  };

  const segnalaDubbio = async p => {
    const numero = p.fattura_numero || p.numero_fattura || p.invoice_number || 'senza numero';
    const fornitore = p.fornitore || p.supplier_name || 'Fornitore non disponibile';
    const approvato = await confirm({
      title: 'Segnala metodo di pagamento incerto',
      message: `Apri un'anomalia sulla fattura ${numero} di ${fornitore}? Non verra creato o cancellato alcun pagamento; la fattura tornera tra quelle da decidere.`,
      confirmText: 'Segnala dubbio',
      cancelText: 'Annulla',
      variant: 'warning',
    });
    if (!approvato) return;
    setBusy(p.fattura_id);
    setErrore('');
    setErroreRiga(null);
    setEsito('');
    try {
      const response = await api.post('/api/prima-nota/provvisori/segnala-dubbio', {
        fattura_id: p.fattura_id,
      });
      setEsito(response.data?.message || `Anomalia aperta sulla fattura ${numero}.`);
      await onRicarica({ silent: true });
    } catch (e) {
      setErroreRiga({
        fatturaId: p.fattura_id,
        messaggio: e.response?.data?.detail || e.response?.data?.message || e.message,
      });
    } finally {
      setBusy(null);
    }
  };

  const confermaParziale = async () => {
    const cassa = parseImportoIT(importoCassa);
    const totale = parziale?.importo || 0;
    if (cassa === null || cassa <= 0 || cassa >= totale) {
      setErrore(`L'importo cassa deve stare tra 0 e ${eur(totale)}.`);
      return;
    }
    setBusy(parziale.fattura_id);
    setErrore('');
    setEsito('');
    try {
      const response = await api.post('/api/prima-nota/provvisori/conferma-divisione', {
        fattura_id: parziale.fattura_id,
        importo_cassa: cassa,
        importo_banca: Number((totale - cassa).toFixed(2)),
      });
      setParziale(null);
      setImportoCassa('');
      setEsito(response.data?.message || 'Quota Cassa registrata; residuo in attesa della banca.');
      await onRicarica({ silent: true });
    } catch (e) {
      setErrore(e.response?.data?.detail || e.response?.data?.message || e.message);
    } finally {
      setBusy(null);
    }
  };

  const riprocessaEstratto = async () => {
    setBusy('riprocessa-estratto');
    setErrore('');
    setErroreRiga(null);
    setEsito('');
    try {
      const avvio = await api.post('/api/operazioni-da-confermare/smart/riconcilia-auto');
      const jobId = avvio.data?.job_id;
      setEsito(avvio.data?.status === 'running'
        ? 'Riconciliazione avviata in background. La pagina si aggiornera al termine.'
        : 'Riconciliazione accodata.');

      let stato = avvio.data || {};
      const scadenzaPolling = Date.now() + (15 * 60 * 1000);
      while (stato.status === 'running' && Date.now() < scadenzaPolling) {
        await new Promise(resolve => setTimeout(resolve, 2500));
        const response = await api.get('/api/operazioni-da-confermare/smart/riconcilia-auto/status');
        stato = response.data || {};
        if (jobId && stato.job_id && stato.job_id !== jobId) {
          throw new Error('E in corso una nuova riconciliazione: ricarica la pagina per seguirla.');
        }
      }

      if (stato.status === 'error') {
        throw new Error(stato.error || 'Riconciliazione non completata.');
      }
      if (stato.status === 'running') {
        setEsito('La riconciliazione continua in background. Puoi lasciare la pagina e tornare piu tardi.');
        return;
      }

      const risultato = stato.result || {};
      const riconciliati = Number(risultato.riconciliati || 0);
      const analizzati = Number(risultato.analizzati || 0);
      setEsito(`Estratto conto riprocessato: ${analizzati} movimenti esaminati, ${riconciliati} riconciliati.`);
      await onRicarica();
    } catch (e) {
      setErrore(e.response?.data?.detail || e.response?.data?.message || e.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 12 }}>
      {completezza && (
        <div
          data-testid="completezza-fatture-provvisorie"
          style={{ background: '#eff6ff', border: '1px solid #93c5fd', borderRadius: 11, padding: '10px 13px', color: '#1e3a5f', fontSize: 12.5, lineHeight: 1.55 }}
        >
          <b>Completezza fatture {completezza.anno}:</b>{' '}
          {completezza.fatture_attive_positive} fatture dell'anno con importo positivo ={' '}
          <b>{completezza.gia_registrate_pagamento_completo} gia registrate/pagate</b> +{' '}
          <b>{completezza.aperte_mostrate} aperte mostrate qui</b>
          {completezza.escluse_cassa_banca > 0 && (
            <> + <b>{completezza.escluse_cassa_banca} escluse dal flusso Cassa/Banca</b></>
          )}.
          <div style={{ color: '#475569', marginTop: 2 }}>
            Nessuna fattura viene nascosta: usa "Tutte le fatture" per vedere
            posizione contabile, residuo e riferimenti DDT di ogni documento.
          </div>
        </div>
      )}
      <div role="tablist" aria-label="Vista fatture Prima Nota" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button
          type="button"
          role="tab"
          aria-selected={vista === 'da_lavorare'}
          onClick={() => setVista('da_lavorare')}
          style={{ minHeight: 42, flex: '1 1 240px', border: `1px solid ${vista === 'da_lavorare' ? BLU : '#cbd5e1'}`, borderRadius: 9, background: vista === 'da_lavorare' ? BLU : 'white', color: vista === 'da_lavorare' ? 'white' : '#334155', fontWeight: 800, cursor: 'pointer' }}
        >
          Da lavorare ({provvisori.length + attesaBanca.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={vista === 'tutte'}
          onClick={() => setVista('tutte')}
          style={{ minHeight: 42, flex: '1 1 240px', border: `1px solid ${vista === 'tutte' ? BLU : '#cbd5e1'}`, borderRadius: 9, background: vista === 'tutte' ? BLU : 'white', color: vista === 'tutte' ? 'white' : '#334155', fontWeight: 800, cursor: 'pointer' }}
        >
          Tutte le fatture ({tutteFatture.length})
        </button>
      </div>
      {vista === 'da_lavorare' && <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button
          type="button"
          onClick={riprocessaEstratto}
          disabled={busy === 'riprocessa-estratto'}
          style={{ minHeight: 40, background: BLU, color: 'white', border: 0, borderRadius: 8, padding: '8px 13px', fontSize: 12.5, fontWeight: 800, cursor: busy === 'riprocessa-estratto' ? 'wait' : 'pointer' }}
        >
          {busy === 'riprocessa-estratto' ? 'Riprocessamento…' : 'Riprocessa estratto conto'}
        </button>
      </div>}
      <FiltriFattura
        numeroFattura={fNumeroFattura}
        numeroDdt={fNumeroDdt}
        data={fDataFattura}
        fornitore={fFornitore}
        onNumeroFattura={setFNumeroFattura}
        onNumeroDdt={setFNumeroDdt}
        onData={setFDataFattura}
        onFornitore={setFFornitore}
      />
      {vista === 'tutte' && (
        <div data-testid="registro-completo-fatture" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', flexWrap: 'wrap', color: '#475569', fontSize: 12.5 }}>
            <span>
              Mostrate <b>{tutteFattureVisibili.length}</b> fatture.
              {tutteFattureVisibili.length > 0 && (
                <> Righe {(paginaTutteSicura - 1) * righePerPagina + 1}-{Math.min(paginaTutteSicura * righePerPagina, tutteFattureVisibili.length)}.</>
              )}
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <button type="button" aria-label="Prima pagina fatture" onClick={() => setPaginaTutte(1)} disabled={paginaTutteSicura === 1} style={{ minWidth: 40, minHeight: 38, border: '1px solid #cbd5e1', borderRadius: 8, background: 'white', cursor: 'pointer' }}>&laquo;</button>
              <button type="button" aria-label="Pagina fatture precedente" onClick={() => setPaginaTutte(p => Math.max(1, p - 1))} disabled={paginaTutteSicura === 1} style={{ minWidth: 40, minHeight: 38, border: '1px solid #cbd5e1', borderRadius: 8, background: 'white', cursor: 'pointer' }}>&lsaquo;</button>
              <b>Pagina {paginaTutteSicura}/{pagineTutte}</b>
              <button type="button" aria-label="Pagina fatture successiva" onClick={() => setPaginaTutte(p => Math.min(pagineTutte, p + 1))} disabled={paginaTutteSicura === pagineTutte} style={{ minWidth: 40, minHeight: 38, border: '1px solid #cbd5e1', borderRadius: 8, background: 'white', cursor: 'pointer' }}>&rsaquo;</button>
              <button type="button" aria-label="Ultima pagina fatture" onClick={() => setPaginaTutte(pagineTutte)} disabled={paginaTutteSicura === pagineTutte} style={{ minWidth: 40, minHeight: 38, border: '1px solid #cbd5e1', borderRadius: 8, background: 'white', cursor: 'pointer' }}>&raquo;</button>
            </span>
          </div>
          {tutteFatturePagina.length === 0 && (
            <div style={{ padding: 28, textAlign: 'center', color: '#64748b', background: 'white', border: '1px solid #e2e8f0', borderRadius: 11 }}>
              Nessuna fattura corrisponde ai filtri.
            </div>
          )}
          {tutteFatturePagina.map(fattura => {
            const registrata = String(fattura.stato || '').startsWith('registrata_');
            const colore = registrata ? '#047857' : fattura.stato === 'in_attesa_banca' ? '#1d4ed8' : fattura.stato === 'anomalia_pagamento' ? '#b91c1c' : '#92400e';
            return (
              <div key={fattura.fattura_id} style={{ background: 'white', border: '1px solid #e2e8f0', borderLeft: `4px solid ${colore}`, borderRadius: 10, padding: '10px 12px', display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
                <div style={{ minWidth: 0, flex: '1 1 430px' }}>
                  <div style={{ color: BLU, fontSize: 13.5, fontWeight: 800 }}>{fattura.fornitore || 'Fornitore non indicato'}</div>
                  <div style={{ color: '#475569', fontSize: 12 }}>
                    Fatt. {fattura.fattura_numero || 'senza numero'} del {formatDateIT(fattura.fattura_data)}
                  </div>
                  {dettaglioDdtCompleto(fattura)}
                  {(fattura.movimenti_prima_nota || []).length > 0 && (
                    <div style={{ marginTop: 3, color: '#475569', fontSize: 11.5 }}>
                      {(fattura.movimenti_prima_nota || []).map((movimento, indice) => (
                        <span key={`${movimento.id || movimento.posizione}-${indice}`}>
                          {indice > 0 && ' · '}
                          {movimento.posizione === 'cassa' ? 'Cassa' : movimento.posizione === 'banca' ? 'Banca riconciliata' : 'Banca in attesa'}
                          {movimento.data ? ` ${formatDateIT(movimento.data)}` : ''}
                          {movimento.importo ? ` ${eur(movimento.importo)}` : ''}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ color: colore, background: `${colore}12`, border: `1px solid ${colore}55`, borderRadius: 999, padding: '5px 9px', fontSize: 11.5, fontWeight: 800 }}>
                    {fattura.stato_label || fattura.stato}
                  </span>
                  <span style={{ textAlign: 'right', fontSize: 12 }}>
                    <b style={{ display: 'block', color: BLU, fontFamily: 'ui-monospace, Menlo, monospace' }}>{eur(fattura.totale_fattura)}</b>
                    {Number(fattura.importo_residuo || 0) > 0 && <span style={{ color: '#b45309' }}>Residuo {eur(fattura.importo_residuo)}</span>}
                  </span>
                  {bottoneVedi(fattura)}
                  {fattura.richiede_azione && (
                    <button type="button" onClick={() => setVista('da_lavorare')} style={{ minHeight: 40, background: BLU, color: 'white', border: 0, borderRadius: 8, padding: '7px 11px', fontWeight: 800, cursor: 'pointer' }}>
                      Gestisci
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
      {vista === 'da_lavorare' && <>
      <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8, alignSelf: 'flex-start', color: '#334155', fontSize: 12.5, fontWeight: 700, cursor: 'pointer' }}>
        <input
          type="checkbox"
          checked={modalitaRapida}
          onChange={e => setModalitaRapida(e.target.checked)}
          aria-label="Attiva selezione veloce"
          style={{ width: 17, height: 17 }}
        />
        Selezione veloce: Cassa e Attendi banca con un clic, senza perdere filtri e selezioni
      </label>
      {errore && <div style={{ color: ROSSO, fontSize: 13 }}>{errore}</div>}
      {esito && (
        <div role="status" style={{ color: '#166534', background: '#f0fdf4', border: '1px solid #86efac', borderRadius: 8, padding: '9px 11px', fontSize: 13 }}>
          {esito}
        </div>
      )}
      {provvisoriVisibili.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', background: 'white', borderRadius: 11, border: '1px solid #e2e8f0', padding: '9px 13px' }} data-testid="barra-conferma-multipla">
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 12.5, fontWeight: 700, color: '#334155', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={selezionate.size > 0 && provvisoriVisibili.every(p => selezionate.has(p.fattura_id))}
              onChange={e => setSelezionate(e.target.checked
                ? new Set(provvisoriVisibili.map(p => p.fattura_id))
                : new Set())}
              aria-label="Seleziona tutte le fatture visibili"
              style={{ width: 17, height: 17 }}
            />
            Seleziona tutte ({provvisoriVisibili.length})
          </label>
          {selezionate.size > 0 && (
            <>
              <span style={{ fontSize: 12.5, color: '#64748b' }}>
                {selezionate.size} selezionate ·{' '}
                {eur(provvisoriVisibili.filter(p => selezionate.has(p.fattura_id))
                  .reduce((s, p) => s + Number(p.importo || 0), 0))}
              </span>
              <button
                onClick={() => confermaMultipla('cassa')} disabled={busyMultiplo}
                style={{ background: VERDE, color: 'white', border: 'none', borderRadius: 8, padding: '7px 13px', fontSize: 12.5, fontWeight: 700, cursor: 'pointer', opacity: busyMultiplo ? 0.5 : 1 }}
              >
                💵 Registra in Cassa ({selezionate.size})
              </button>
              <button
                onClick={() => confermaMultipla('banca')} disabled={busyMultiplo}
                title="Le sposta tra i pagamenti attesi; nessun pagamento viene registrato senza estratto conto"
                style={{ background: BLU, color: 'white', border: 'none', borderRadius: 8, padding: '7px 13px', fontSize: 12.5, fontWeight: 700, cursor: 'pointer', opacity: busyMultiplo ? 0.5 : 1 }}
              >
                🏦 Attendi banca ({selezionate.size})
              </button>
            </>
          )}
        </div>
      )}
      {esitiMultipli && (
        <div role="status" style={{ background: esitiMultipli.scartate ? '#fffbeb' : '#f0fdf4', border: `1px solid ${esitiMultipli.scartate ? '#fcd34d' : '#bbf7d0'}`, borderRadius: 10, padding: '9px 13px', fontSize: 12.5 }}>
          <b>{esitiMultipli.message}</b>
          {(esitiMultipli.esiti || []).filter(e => !e.success).slice(0, 10).map(e => (
            <div key={e.fattura_id} style={{ color: '#92400e', marginTop: 3 }}>· {e.detail}</div>
          ))}
        </div>
      )}
      {provvisoriVisibili.length === 0 && (
        <div style={{ padding: 26, textAlign: 'center', color: '#6b7280', background: 'white', borderRadius: 12, border: '1px solid #e2e8f0' }}>
          {provvisori.length === 0
            ? 'Nessuna fattura in attesa di divisione cassa/banca.'
            : 'Nessuna fattura provvisoria corrisponde ai filtri.'}
        </div>
      )}
      {provvisoriVisibili.map(p => (
        <div
          key={p.fattura_id || p.id}
          style={{
            background: p.anomalia_pagamento?.stato === 'aperta' ? '#fff7ed' : 'white',
            borderRadius: 11,
            border: `1px solid ${p.anomalia_pagamento?.stato === 'aperta' ? '#fb923c' : '#e2e8f0'}`,
            borderLeft: `4px solid ${p.anomalia_pagamento?.stato === 'aperta' ? '#dc2626' : '#d97706'}`,
            padding: '10px 13px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
            <div style={{ minWidth: 0, display: 'flex', gap: 9, alignItems: 'flex-start' }}>
              <input
                type="checkbox"
                checked={selezionate.has(p.fattura_id)}
                onChange={() => commuta(p.fattura_id)}
                aria-label={`Seleziona fattura ${p.fattura_numero || ''}`.trim()}
                style={{ width: 17, height: 17, marginTop: 2, flexShrink: 0 }}
              />
              <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 13.5, color: BLU }}>{p.fornitore || p.supplier_name || '—'}</div>
              <div style={{ fontSize: 12, color: '#64748b' }}>
                Fatt. {p.fattura_numero || p.numero_fattura || p.invoice_number || '—'} del {formatDateIT(p.fattura_data || p.data || p.invoice_date)}
                {p.suggerimento === 'sospesa' && ' — ⏸ sospesa'}
              </div>
              {dettaglioDdt(p)}
              {p.anomalia_pagamento?.stato === 'aperta' && (
                <div role="status" style={{ marginTop: 4, color: '#b91c1c', fontSize: 11.5, fontWeight: 800 }}>
                  ⚠ Metodo di pagamento da verificare
                </div>
              )}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontWeight: 800, fontFamily: 'ui-monospace, Menlo, monospace', color: BLU }}>{eur(p.importo)}</div>
              {(p.importo_pagato_confermato || 0) > 0 && (
                <div style={{ fontSize: 11.5, color: '#64748b', marginTop: 2 }}>
                  Totale {eur(p.totale_fattura)} · già pagato {eur(p.importo_pagato_confermato)} · residuo {eur(p.importo_residuo)}
                </div>
              )}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 6, marginTop: 9, flexWrap: 'wrap' }}>
            {bottoneVedi(p)}
            <button
              onClick={() => confermaCassa(p)} disabled={busy === p.fattura_id}
              style={{ background: VERDE, color: 'white', border: 'none', borderRadius: 8, padding: '7px 13px', fontSize: 12.5, fontWeight: 700, cursor: 'pointer', opacity: busy === p.fattura_id ? 0.5 : 1 }}
            >
              💵 Cassa
            </button>
            <button
              onClick={() => attendiBanca(p)} disabled={busy === p.fattura_id}
              title="Sposta tra i pagamenti attesi; non registra un pagamento senza estratto conto"
              style={{ background: BLU, color: 'white', border: 'none', borderRadius: 8, padding: '7px 13px', fontSize: 12.5, fontWeight: 700, cursor: 'pointer', opacity: busy === p.fattura_id ? 0.5 : 1 }}
            >
              🏦 Attendi banca
            </button>
            <button
              onClick={() => { setParziale(p); setImportoCassa(''); setErrore(''); }}
              style={{ background: '#f1f5f9', border: '1px solid #e2e8f0', borderRadius: 8, padding: '7px 13px', fontSize: 12.5, fontWeight: 700, cursor: 'pointer' }}
            >
              ✂️ Parziale
            </button>
            {p.suggerimento !== 'sospesa' && (
              <button
                onClick={() => conferma(p, 'sospesa')}
                style={{ background: '#fef3c7', border: '1px solid #d97706', borderRadius: 8, padding: '7px 13px', fontSize: 12.5, cursor: 'pointer' }}
              >
                ⏸ Sospendi
              </button>
            )}
            <button
              type="button"
              onClick={() => segnalaDubbio(p)}
              disabled={busy === p.fattura_id || p.anomalia_pagamento?.stato === 'aperta'}
              title="Evidenzia la fattura come anomalia senza creare o cancellare pagamenti"
              style={{ background: '#fff7ed', color: '#b91c1c', border: '1px solid #fb923c', borderRadius: 8, padding: '7px 13px', fontSize: 12.5, fontWeight: 800, cursor: 'pointer', opacity: p.anomalia_pagamento?.stato === 'aperta' ? 0.6 : 1 }}
            >
              ⚠ {p.anomalia_pagamento?.stato === 'aperta' ? 'Dubbio segnalato' : 'Dubbio sul pagamento'}
            </button>
          </div>
          {erroreRiga?.fatturaId === p.fattura_id && (
            <div role="alert" style={{ color: '#991b1b', background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 8, padding: '8px 10px', marginTop: 8, fontSize: 12.5 }}>
              {erroreRiga.messaggio}
            </div>
          )}
        </div>
      ))}

      {attesaBancaVisibili.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <div style={{ fontSize: 12.5, fontWeight: 700, color: '#64748b', margin: '4px 0 8px' }}>
            🏦 Pagamenti previsti in banca — in attesa dell'addebito in estratto conto ({attesaBanca.length}).
            Si registrano da sole quando l'addebito arriva. Puoi associare manualmente un movimento oppure correggere il metodo in qualsiasi momento.
          </div>
          {attesaBancaVisibili.map(p => (
            <div
              key={p.fattura_id}
              style={{
                background: p.anomalia_pagamento?.stato === 'aperta' ? '#fff7ed' : 'white',
                borderRadius: 10,
                border: `1px dashed ${p.anomalia_pagamento?.stato === 'aperta' ? '#fb923c' : '#93c5fd'}`,
                borderLeft: `4px solid ${p.anomalia_pagamento?.stato === 'aperta' ? '#dc2626' : '#2563eb'}`,
                padding: '8px 12px', marginBottom: 6, display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 12.5, flexWrap: 'wrap',
              }}
            >
              <div style={{ minWidth: 0, flex: '1 1 360px' }}>
                {p.fornitore || '—'} — Fatt. {p.fattura_numero || '—'} del {formatDateIT(p.fattura_data)}
                {p.fonte_metodo === 'assegno_compilato' && (
                  <span style={{ color: '#7c3aed', fontWeight: 700 }}>
                    {' '}· Assegno{p.assegno_numero ? ` n. ${p.assegno_numero}` : ''} già predisposto
                  </span>
                )}
                {p.strumento_bancario?.codice === 'riba' && (
                  <span style={{ color: '#0369a1', fontWeight: 800 }}>
                    {' '}· RiBa identificata nell'estratto conto
                  </span>
                )}
                {p.movimento_banca && (
                  <span style={{ color: '#047857', fontWeight: 700 }}>
                    {' '}· riscontro univoco del {formatDateIT(p.movimento_banca.data)} ({
                      p.evidenza_banca === 'sdd_fornitore_importo_data'
                        ? 'SDD + fornitore + importo + data'
                        : p.evidenza_banca === 'strumento_fornitore_importo_data'
                          ? `${p.strumento_bancario?.label || 'strumento bancario'} + fornitore + importo al centesimo`
                        : p.evidenza_banca?.tipo === 'pagamento_netto_dopo_rimborso_duplicato'
                          ? 'fattura esplicita + doppio pagamento neutralizzato dal rimborso'
                          : p.evidenza_banca?.tipo === 'assegno_cumulativo_lotto_fatture'
                            ? `assegno cumulativo = ${p.evidenza_banca.fatture_ids?.length || 0} fatture dello stesso lotto`
                            : p.evidenza_banca?.tipo === 'sequenza_assegni_fatture_stesso_fornitore_importo'
                              ? `sequenza univoca di ${p.evidenza_banca.cardinalita || 0} assegni e fatture dello stesso fornitore`
                            : 'fornitore + numero fattura + importo'
                    }), in elaborazione
                  </span>
                )}
                {(p.ritenuta_non_pagabile_fornitore || 0) > 0 && (
                  <span style={{ color: '#7c3aed', fontWeight: 700 }}>
                    {' '}· netto fornitore {eur(p.totale_pagabile_fornitore)} · ritenuta {eur(p.ritenuta_non_pagabile_fornitore)} separata su F24
                  </span>
                )}
                {(p.importo_pagato_confermato || 0) > 0 && (
                  <span style={{ color: '#475569' }}>
                    {' '}· totale {eur(p.totale_fattura)} · già pagato {eur(p.importo_pagato_confermato)} · residuo {eur(p.importo_residuo)}
                  </span>
                )}
                {dettaglioDdt(p)}
                {p.anomalia_pagamento?.stato === 'aperta' && (
                  <div role="status" style={{ marginTop: 4, color: '#b91c1c', fontSize: 11.5, fontWeight: 800 }}>
                    ⚠ Metodo di pagamento da verificare
                  </div>
                )}
                {p.motivo_sospensione && (
                  <div role="status" style={{ marginTop: 4, color: '#92400e', fontSize: 11.5, fontWeight: 800 }}>
                    {p.motivo_sospensione}
                  </div>
                )}
              </div>
              <span style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <b style={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>{eur(p.importo)}</b>
                <button
                  onClick={() => setFatturaView({ id: p.fattura_id, numero: p.fattura_numero })}
                  title="Vedi fattura"
                  aria-label={`Vedi fattura ${p.fattura_numero || ''}`.trim()}
                  style={{ width: 40, height: 40, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: '#f1f5f9', color: '#334155', border: '1px solid #cbd5e1', borderRadius: 8, padding: 0, cursor: 'pointer' }}
                >
                  <Eye size={18} />
                </button>
                <button
                  onClick={() => setAssociaFattura(p)}
                  title="Scegli il movimento reale quando piu documenti hanno lo stesso importo o l'identita non e univoca"
                  style={{ minHeight: 40, display: 'inline-flex', alignItems: 'center', background: '#eff6ff', border: '1px solid #93c5fd', color: '#1d4ed8', borderRadius: 7, padding: '4px 12px', fontSize: 11.5, fontWeight: 700, cursor: 'pointer' }}
                >
                  Associa a mano
                </button>
                {puoAssociareAssegno(p) && (
                  <AssociaAssegnoFattura
                    fattura={p}
                    onSuccess={async data => {
                      setEsito(data?.message || 'Assegno collegato alla fattura.');
                      await onRicarica({ silent: true });
                    }}
                  />
                )}
                <button
                  type="button"
                  onClick={() => confermaCassa(p)}
                  disabled={busy === p.fattura_id}
                  title="Correggi il metodo della fattura e registrala in Cassa"
                  style={{ minHeight: 40, background: VERDE, color: 'white', border: 0, borderRadius: 8, padding: '7px 11px', fontSize: 11.5, fontWeight: 800, cursor: 'pointer' }}
                >
                  💵 Sposta in Cassa
                </button>
                <button
                  type="button"
                  onClick={() => riportaDaDecidere(p)}
                  disabled={busy === p.fattura_id}
                  title="Rimuovi l'attesa automatica e scegli nuovamente il metodo"
                  style={{ minHeight: 40, background: '#fff7ed', color: '#9a3412', border: '1px solid #fdba74', borderRadius: 8, padding: '7px 11px', fontSize: 11.5, fontWeight: 800, cursor: 'pointer' }}
                >
                  ↩ Da decidere
                </button>
                <button
                  type="button"
                  onClick={() => segnalaDubbio(p)}
                  disabled={busy === p.fattura_id || p.anomalia_pagamento?.stato === 'aperta'}
                  title="Evidenzia la fattura come anomalia e riportala tra le decisioni"
                  style={{ minHeight: 40, background: '#fff7ed', color: '#b91c1c', border: '1px solid #fb923c', borderRadius: 8, padding: '7px 11px', fontSize: 11.5, fontWeight: 800, cursor: 'pointer', opacity: p.anomalia_pagamento?.stato === 'aperta' ? 0.6 : 1 }}
                >
                  ⚠ {p.anomalia_pagamento?.stato === 'aperta' ? 'Dubbio segnalato' : 'Dubbio'}
                </button>
                <span title={p.movimento_banca ? 'Il movimento ha prova univoca ed e in elaborazione' : (p.motivo_sospensione || 'Nessuna associazione automatica senza una prova univoca')} style={{ color: p.movimento_banca ? '#047857' : '#64748b', fontSize: 11.5, fontWeight: 700 }}>
                  {p.movimento_banca ? 'Riscontro univoco trovato' : (p.stato_match === 'ambiguo_importo_al_centesimo' ? 'Sospesa: piu fatture compatibili' : 'In attesa di riscontro univoco')}
                </span>
              </span>
              {erroreRiga?.fatturaId === p.fattura_id && (
                <div role="alert" style={{ width: '100%', color: '#991b1b', background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 8, padding: '8px 10px', fontSize: 12.5 }}>
                  {erroreRiga.messaggio}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      </>}

      {parziale && (
        <div
          onClick={() => setParziale(null)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(15,39,68,0.55)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 14 }}
        >
          <div onClick={e => e.stopPropagation()} style={{ background: 'white', borderRadius: 14, padding: 18, width: '100%', maxWidth: 400 }}>
            <h3 style={{ margin: '0 0 6px', fontSize: 15, color: BLU }}>✂️ Pagamento parziale</h3>
            <div style={{ fontSize: 13, color: '#475569', marginBottom: 10 }}>
              {parziale.fornitore || '—'} — totale <b>{eur(parziale.importo)}</b>
            </div>
            <input
              aria-label="Quota pagata in contanti"
              placeholder="Quota pagata in CONTANTI (es. 100,00)" inputMode="decimal" value={importoCassa}
              onChange={e => setImportoCassa(e.target.value)}
              style={{ width: '100%', padding: '9px 10px', border: '1px solid #d1d5db', borderRadius: 8, boxSizing: 'border-box', marginBottom: 8 }}
            />
            {parseImportoIT(importoCassa) !== null && (
              <div style={{ fontSize: 12.5, color: '#475569', marginBottom: 8 }}>
                💵 Cassa {eur(parseImportoIT(importoCassa))} + 🏦 Banca {eur((parziale.importo || 0) - parseImportoIT(importoCassa))}
              </div>
            )}
            <div style={{ fontSize: 12, color: '#64748b', marginBottom: 8 }}>
              La quota Cassa viene registrata ora. Il residuo Banca resta aperto finché non viene trovato e riconciliato il movimento reale dell'estratto conto.
            </div>
            {errore && <div style={{ color: ROSSO, fontSize: 13, marginBottom: 8 }}>{errore}</div>}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button onClick={() => setParziale(null)} style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid #d1d5db', background: 'white', cursor: 'pointer' }}>
                Annulla
              </button>
              <button onClick={confermaParziale} style={{ padding: '8px 16px', borderRadius: 8, border: 'none', background: BLU, color: 'white', fontWeight: 700, cursor: 'pointer' }}>
                Conferma
              </button>
            </div>
          </div>
        </div>
      )}

      {associaFattura && (
        <AssociaMovimentoBanca
          fattura={associaFattura}
          onChiudi={() => setAssociaFattura(null)}
          onAssociato={() => window.location.reload()}
        />
      )}

      {fatturaView && (
        <ModalFattura fatturaId={fatturaView.id} numero={fatturaView.numero} onClose={() => setFatturaView(null)} />
      )}
    </div>
  );
}

export function FattureAtteseNelRegistroBanca({ fatture = [], mese, onGestisci }) {
  const visibili = useMemo(() => {
    if (mese === null) return fatture;
    return fatture.filter(f => {
      const data = f.fattura_data || f.invoice_date || f.data || '';
      return Number(String(data).slice(5, 7)) === mese + 1;
    });
  }, [fatture, mese]);

  if (!visibili.length) return null;
  const totale = visibili.reduce((somma, f) => somma + Number(f.importo || 0), 0);
  return (
    <details open={mese !== null} style={{ margin: '12px 0 0', background: '#eff6ff', border: '1px solid #93c5fd', borderRadius: 10 }}>
      <summary style={{ cursor: 'pointer', padding: '10px 13px', color: BLU, fontWeight: 800, fontSize: 13 }}>
        Fatture attese in banca: {visibili.length} · {eur(totale)}
      </summary>
      <div style={{ padding: '0 10px 10px', display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ color: '#475569', fontSize: 12 }}>
          Sono visibili nel registro ma non entrano nel saldo finché non esiste un addebito reale riconciliato.
        </div>
        {visibili.map(f => (
          <div key={f.fattura_id || f.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', background: 'white', border: '1px dashed #60a5fa', borderRadius: 8, padding: '8px 10px', fontSize: 12.5 }}>
            <span>
              <b>{f.fornitore || f.supplier_name || 'Fornitore'}</b> · Fatt. {f.fattura_numero || f.invoice_number || '—'} del {formatDateIT(f.fattura_data || f.invoice_date || f.data)}
            </span>
            <b style={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>{eur(f.importo)}</b>
          </div>
        ))}
        <button type="button" onClick={onGestisci} style={{ alignSelf: 'flex-start', background: BLU, color: 'white', border: 0, borderRadius: 8, padding: '7px 11px', fontWeight: 700, cursor: 'pointer' }}>
          Gestisci associazioni
        </button>
      </div>
    </details>
  );
}

/* -------------------------------- pagina -------------------------------- */
export default function PrimaNota() {
  const { anno } = useAnnoGlobale();
  const [hs, setHs] = useHashState({ sezione: 'cassa', mese: '' });
  const sezione = hs.sezione || 'cassa';
  const mese = hs.mese === '' ? null : parseInt(hs.mese, 10);

  const [cassa, setCassa] = useState({ movimenti: [], loaded: false });
  const [banca, setBanca] = useState({ movimenti: [], loaded: false });
  const [provvisori, setProvvisori] = useState([]);
  const [attesaBanca, setAttesaBanca] = useState([]);
  const [tutteFatture, setTutteFatture] = useState([]);
  const [completezzaProvvisori, setCompletezzaProvvisori] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const richiestaRef = React.useRef(0);
  // Una lettura della Prima Nota e' interattiva: se Atlas non risponde, la UI
  // deve sbloccarsi rapidamente e permettere un nuovo tentativo. Il retry
  // globale di Axios (pensato per il cold start di Render) qui raddoppierebbe
  // inutilmente l'attesa.
  const richiestaInterattiva = { timeout: 10000, __noRetry: true };

  const carica = async ({ silent = false } = {}) => {
    const richiesta = ++richiestaRef.current;
    if (sezione === 'soci') {
      setLoading(false);
      setLoadError('');
      return;
    }
    if (!silent) setLoading(true);
    setLoadError('');
    try {
      const params = `anno=${anno}&limit=10000`;
      if (sezione === 'provvisori') {
        const p = await api.get(
          `/api/prima-nota/provvisori?anno=${anno}`,
          richiestaInterattiva,
        );
        if (richiesta !== richiestaRef.current) return;
        setProvvisori(p.data?.provvisori || []);
        setAttesaBanca(p.data?.in_attesa_banca || []);
        setTutteFatture(p.data?.tutte_fatture || []);
        setCompletezzaProvvisori(p.data?.completezza || null);
      } else {
        const endpoint = sezione === 'banca' ? 'banca' : 'cassa';
        const risposta = await api.get(
          `/api/prima-nota/${endpoint}?${params}`,
          richiestaInterattiva,
        );
        if (richiesta !== richiestaRef.current) return;
        const dati = { ...(risposta.data || { movimenti: [] }), loaded: true };
        if (endpoint === 'banca') setBanca(dati);
        else setCassa(dati);

        // Il registro opposto serve solo al confronto POS. Lo carichiamo in
        // background dopo aver gia' mostrato la pagina richiesta: non puo'
        // piu' bloccare Cassa o Banca e non rende falsi i totali visualizzati.
        const opposto = endpoint === 'banca' ? 'cassa' : 'banca';
        api.get(`/api/prima-nota/${opposto}?${params}`, richiestaInterattiva)
          .then((secondaria) => {
            if (richiesta !== richiestaRef.current) return;
            const altriDati = { ...(secondaria.data || { movimenti: [] }), loaded: true };
            if (opposto === 'banca') setBanca(altriDati);
            else setCassa(altriDati);
          })
          .catch((errore) => console.warn(`Prima nota ${opposto} (background):`, errore));
      }
    } catch (e) {
      if (richiesta !== richiestaRef.current) return;
      console.error('Prima nota:', e);
      const messaggio = e.code === 'ECONNABORTED'
        ? 'Il database non ha risposto entro 10 secondi. Nessun dato e stato modificato.'
        : (e.response?.data?.detail || e.response?.data?.message || e.message || 'Caricamento non riuscito');
      setLoadError(messaggio);
    } finally {
      if (!silent && richiesta === richiestaRef.current) setLoading(false);
    }
  };
  useEffect(() => {
    carica();
    return () => { richiestaRef.current += 1; };
  }, [anno, sezione]);

  // Modale dedicata (niente window.prompt: su telefono/PWA è inaffidabile)
  const [riportoModal, setRiportoModal] = useState(null); // {tipo}
  const [riportoInput, setRiportoInput] = useState('');
  const [riportoErr, setRiportoErr] = useState('');
  const [riportoSaving, setRiportoSaving] = useState(false);

  const modificaRiporto = tipo => {
    const attuale = (tipo === 'cassa' ? cassa : banca).saldo_precedente || 0;
    setRiportoInput(attuale ? String(attuale).replace('.', ',') : '');
    setRiportoErr('');
    setRiportoModal({ tipo });
  };

  const salvaRiporto = async () => {
    const importo = parseImportoIT(riportoInput);
    if (importo === null) {
      setRiportoErr('Scrivi un importo valido, es. 12.500,00');
      return;
    }
    setRiportoSaving(true);
    try {
      await api.put('/api/prima-nota/saldo-iniziale', { tipo: riportoModal.tipo, anno, importo });
      setRiportoModal(null);
      carica();
    } catch (e) {
      setRiportoErr(e.response?.data?.message || e.response?.data?.detail || e.message);
    } finally {
      setRiportoSaving(false);
    }
  };

  const datiAttivi = sezione === 'banca' ? banca : cassa;
  const saldoFinale = (datiAttivi.saldo_precedente || 0) +
    (datiAttivi.movimenti || []).reduce((s, m) => s + (m.tipo === 'entrata' ? 1 : -1) * Math.abs(m.importo || 0), 0);

  const tab = (chiave, etichetta) => (
    <button
      key={chiave}
      onClick={() => setHs('sezione', chiave)}
      style={{
        flex: 1, padding: '11px 8px', borderRadius: 10, fontSize: 13.5, fontWeight: 700, cursor: 'pointer',
        background: sezione === chiave ? BLU : 'white',
        color: sezione === chiave ? 'white' : '#64748b',
        border: `1px solid ${sezione === chiave ? BLU : '#e2e8f0'}`,
        whiteSpace: 'nowrap',
      }}
    >
      {etichetta}
    </button>
  );

  return (
    <div style={{ padding: '14px clamp(10px, 3vw, 28px)', maxWidth: 1280, margin: '0 auto' }}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
        {tab('cassa', `💵 Cassa ${anno}`)}
        {tab('banca', `🏦 Banca ${anno}`)}
        {tab('soci', '👥 Soci')}
        {tab('provvisori', etichettaTabProvvisori(provvisori, attesaBanca))}
      </div>

      {loading && sezione !== 'soci' && (
        <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>⏳ Caricamento…</div>
      )}

      {!loading && loadError && sezione !== 'soci' && (
        <div role="alert" style={{ padding: 14, marginBottom: 12, color: '#991b1b', background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 10 }}>
          <b>Prima Nota non caricata.</b> {loadError}{' '}
          <button onClick={carica} style={{ marginLeft: 8, border: '1px solid #991b1b', borderRadius: 6, background: 'white', color: '#991b1b', padding: '5px 9px', fontWeight: 700, cursor: 'pointer' }}>
            Riprova
          </button>
        </div>
      )}

      {!loading && !loadError && sezione === 'provvisori' && (
        <Provvisori
          provvisori={provvisori}
          attesaBanca={attesaBanca}
          tutteFatture={tutteFatture}
          completezza={completezzaProvvisori}
          onRicarica={carica}
        />
      )}

      {sezione === 'soci' && <FinanziamentoSoci />}

      {!loading && !loadError && sezione !== 'provvisori' && sezione !== 'soci' && (
        <>
          {/* 4 numeri, nessuna card doppia */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10 }}>
            <Card
              titolo="Riporto 01/01" valore={datiAttivi.saldo_precedente} colore="#6b7280"
              onEdit={() => modificaRiporto(sezione)} testId={`modifica-riporto-${sezione}`}
            />
            <Card titolo={`Entrate (Dare) ${anno}`} valore={datiAttivi.totale_entrate} colore={VERDE} />
            <Card titolo={`Uscite (Avere) ${anno}`} valore={datiAttivi.totale_uscite} colore={ROSSO} />
            <Card titolo="Saldo" valore={saldoFinale} colore={saldoFinale >= 0 ? BLU : ROSSO} />
          </div>

          <RipartoEntrate sezione={sezione} cassa={cassa} banca={banca} mese={mese} />
          {sezione === 'banca' && <InAttesaDocumento anno={anno} onRicarica={carica} />}
          {sezione === 'banca' && <CartaNexi anno={anno} />}

          {/* mese */}
          <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', margin: '12px 0 0' }}>
            <button
              onClick={() => setHs('mese', '')}
              style={{
                padding: '7px 12px', borderRadius: 7, border: 'none', cursor: 'pointer', fontSize: 12.5,
                background: mese === null ? BLU : '#f1f5f9', color: mese === null ? 'white' : '#374151',
                fontWeight: mese === null ? 700 : 400,
              }}
            >
              Tutti
            </button>
            {MESI.map((m, i) => (
              <button
                key={m}
                onClick={() => setHs('mese', String(i))}
                style={{
                  padding: '7px 10px', borderRadius: 7, border: 'none', cursor: 'pointer', fontSize: 12.5,
                  background: mese === i ? BLU : '#f1f5f9', color: mese === i ? 'white' : '#374151',
                  fontWeight: mese === i ? 700 : 400,
                }}
              >
                {m}
              </button>
            ))}
          </div>

          {sezione === 'banca' && (
            <FattureAtteseNelRegistroBanca
              fatture={attesaBanca}
              mese={mese}
              onGestisci={() => setHs('sezione', 'provvisori')}
            />
          )}

          <Registro
            tipo={sezione}
            dati={datiAttivi}
            mese={mese}
            onRicarica={carica}
            onModificaRiporto={() => modificaRiporto(sezione)}
          />
        </>
      )}

      {riportoModal && (
        <div
          onClick={() => setRiportoModal(null)}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(15,39,68,0.55)', zIndex: 1000,
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 14,
          }}
        >
          <div onClick={e => e.stopPropagation()} style={{ background: 'white', borderRadius: 14, padding: 18, width: '100%', maxWidth: 400 }}>
            <h3 style={{ margin: '0 0 6px', fontSize: 15, color: BLU }}>
              🏁 Saldo iniziale {riportoModal.tipo === 'cassa' ? 'Cassa' : 'Banca'} al 01/01/{anno}
            </h3>
            <div style={{ fontSize: 12.5, color: '#64748b', marginBottom: 10 }}>
              È il riporto dell'anno precedente: il saldo che avevi in {riportoModal.tipo} a fine {anno - 1}.
              Tutti i saldi progressivi ripartono da qui.
            </div>
            <input
              placeholder="es. 12.500,00" inputMode="decimal" value={riportoInput} autoFocus
              onChange={e => setRiportoInput(e.target.value)}
              style={{ width: '100%', padding: '11px 12px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 16, boxSizing: 'border-box', marginBottom: 8 }}
            />
            {riportoErr && <div style={{ color: ROSSO, fontSize: 13, marginBottom: 8 }}>{riportoErr}</div>}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button onClick={() => setRiportoModal(null)} style={{ padding: '9px 14px', borderRadius: 8, border: '1px solid #d1d5db', background: 'white', cursor: 'pointer' }}>
                Annulla
              </button>
              <button
                onClick={salvaRiporto} disabled={riportoSaving}
                style={{ padding: '9px 18px', borderRadius: 8, border: 'none', background: BLU, color: 'white', fontWeight: 700, cursor: 'pointer', opacity: riportoSaving ? 0.6 : 1 }}
              >
                {riportoSaving ? '⏳…' : '💾 Salva'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
