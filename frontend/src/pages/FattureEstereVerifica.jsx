import React, { useState, useEffect, useCallback } from 'react';
import { COLORS, BORDER_RADIUS, formatDateIT } from '../lib/utils';
import { euroOppure } from '../lib/vista';
import { Button, Badge, Card, PageHeader, Input } from '../components/ds';
import { toast } from 'sonner';
import { CheckCircle2, FileSearch, Eye } from 'lucide-react';
import { VisoreOriginale } from '../components/ApriOriginale';
import { urlOriginale } from '../lib/vista';
import AssociaBonificoFattura from '../components/AssociaBonificoFattura';
import api from '../api';

const CAMPI = [
  { key: 'invoice_number', label: 'Numero fattura' },
  { key: 'invoice_date', label: 'Data (YYYY-MM-DD)' },
  { key: 'supplier_name', label: 'Fornitore' },
  { key: 'supplier_vat', label: 'P.IVA fornitore' },
  { key: 'imponibile', label: 'Imponibile', numero: true },
  { key: 'iva', label: 'IVA', numero: true },
  { key: 'total_amount', label: 'Totale', numero: true },
];

function RigaFattura({ fattura, rating, onVerificata, onVediPdf }) {
  const [form, setForm] = useState(() =>
    Object.fromEntries(CAMPI.map(c => [c.key, fattura[c.key] ?? '']))
  );
  const [salvando, setSalvando] = useState(false);

  const setCampo = (key, value) => setForm(f => ({ ...f, [key]: value }));

  const submit = async () => {
    setSalvando(true);
    try {
      const payload = {};
      for (const c of CAMPI) {
        payload[c.key] = c.numero ? parseFloat(String(form[c.key]).replace(',', '.')) || 0 : form[c.key];
      }
      const res = await api.post(`/api/fatture-estere/${fattura.id}/verifica`, payload);
      const pagamento = res.data.paypal?.collegata
        ? 'Pagamento PayPal trovato e collegato.'
        : 'Pagamento da collegare: lo trovi qui sotto, in «Confermate».';
      if (res.data.esito === 'corretta') {
        toast.success('Correzione salvata', {
          description: `Campi corretti: ${res.data.campi_corretti.join(', ')}. ${pagamento}`,
        });
      } else {
        toast.success('Lettura confermata', { description: pagamento });
      }
      onVerificata(fattura.id);
    } catch (e) {
      toast.error('Errore salvataggio verifica', { description: e.response?.data?.detail || e.message });
    } finally {
      setSalvando(false);
    }
  };

  return (
    <Card style={{ padding: 16, marginBottom: 14 }} data-testid={`fattura-estera-${fattura.id}`}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
        <div style={{ fontSize: 13, color: COLORS.textMuted }}>
          File: <strong>{fattura.filename}</strong>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {rating && (
            <Badge variant={rating.percentuale_corrette >= 80 ? 'success' : rating.percentuale_corrette >= 50 ? 'warning' : 'danger'}>
              Fornitore: {rating.corrette}/{rating.totale} letture corrette ({rating.percentuale_corrette}%)
            </Badge>
          )}
          {!rating && <Badge variant="info">Prima verifica per questo fornitore</Badge>}
          {fattura.documento_inbox_id && (
            <Button variant="secondary" size="sm" iconLeft={<Eye size={14} />} onClick={() => onVediPdf(fattura)}>
              Vedi PDF
            </Button>
          )}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}>
        {CAMPI.map(c => (
          <div key={c.key}>
            <label style={{ display: 'block', color: COLORS.textMuted, fontSize: 12, marginBottom: 4 }}>{c.label}</label>
            <Input
              value={form[c.key]}
              onChange={e => setCampo(c.key, e.target.value)}
              data-testid={`campo-${c.key}-${fattura.id}`}
            />
          </div>
        ))}
      </div>

      <div style={{ marginTop: 12, display: 'flex', justifyContent: 'flex-end' }}>
        <Button
          iconLeft={<CheckCircle2 size={16} />}
          onClick={submit}
          disabled={salvando}
          data-testid={`conferma-fattura-${fattura.id}`}
        >
          {salvando ? 'Salvo…' : 'Conferma / Correggi'}
        </Button>
      </div>
    </Card>
  );
}


const VARIANTE_PAGAMENTO = { da_collegare: 'warning', banca_dichiarata: 'warning' };

const EVIDENZE = {
  partita_iva_o_cf: 'P.IVA', denominazione_fornitore: 'nome fornitore', email_fornitore: 'email',
  numero_fattura: 'numero fattura', importo: 'importo al centesimo', valuta: 'valuta',
  data_entro_120_giorni: 'data vicina',
};

function RigaConfermata({ fattura, onAggiornata, onVediPdf }) {
  const [collegando, setCollegando] = useState('');
  const pagamento = fattura.pagamento || {};

  const collegaPaypal = async candidato => {
    setCollegando(candidato.transaction_id);
    try {
      const res = await api.post(`/api/fatture-estere/${fattura.id}/collega-paypal`, {
        transaction_id: candidato.transaction_id,
      });
      toast.success('Pagamento PayPal collegato', { description: res.data.pagamento?.testo });
      await onAggiornata();
    } catch (e) {
      const d = e.response?.data?.detail;
      toast.error('Collegamento non riuscito', { description: d?.message || d || e.message });
    } finally {
      setCollegando('');
    }
  };

  return (
    <Card style={{ padding: 14, marginBottom: 10 }} data-testid={`fattura-confermata-${fattura.id}`}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <div style={{ minWidth: 0, flex: '1 1 260px' }}>
          <div style={{ fontWeight: 700, color: COLORS.text }}>
            {fattura.supplier_name} · {fattura.invoice_number}
          </div>
          <div style={{ fontSize: 12.5, color: COLORS.textMuted, marginTop: 3 }}>
            {formatDateIT(fattura.invoice_date)} · <b>{euroOppure(fattura.total_amount)}</b>
            {fattura.divisa && fattura.divisa !== 'EUR' ? ` (${fattura.divisa})` : ''}
            {' · '}{fattura.verifica_ai === 'corretta' ? 'corretta' : 'confermata'} il {formatDateIT(fattura.verifica_ai_at)}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <Badge variant={VARIANTE_PAGAMENTO[pagamento.codice] || 'success'}>{pagamento.testo}</Badge>
          {fattura.documento_inbox_id && (
            <Button variant="secondary" size="sm" iconLeft={<Eye size={14} />} onClick={() => onVediPdf(fattura)}>
              Vedi PDF
            </Button>
          )}
        </div>
      </div>

      {pagamento.codice === 'da_collegare' && (
        <div style={{ marginTop: 10, borderTop: `1px solid ${COLORS.border}`, paddingTop: 10 }}>
          {(fattura.candidati_paypal || []).length === 0 ? (
            <div style={{ fontSize: 13, color: COLORS.textMuted }}>
              Nessun pagamento PayPal con questo importo al centesimo.
            </div>
          ) : (
            <>
              <div style={{ fontSize: 12.5, fontWeight: 700, color: COLORS.textMuted, marginBottom: 6 }}>
                Pagamenti PayPal con lo stesso importo: scegli quello giusto
              </div>
              {fattura.candidati_paypal.map(c => (
                <div key={c.transaction_id} style={{
                  display: 'flex', gap: 10, justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap',
                  padding: 10, marginBottom: 6, border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.md,
                }}>
                  <div style={{ minWidth: 0, flex: '1 1 260px', fontSize: 13 }}>
                    <b>{formatDateIT(c.data)} · {euroOppure(c.importo)}{c.valuta && c.valuta !== 'EUR' ? ` ${c.valuta}` : ''}</b>
                    {' · '}{c.controparte || 'controparte non indicata'}
                    <div style={{ color: COLORS.textMuted, fontSize: 12, marginTop: 2, overflowWrap: 'anywhere' }}>
                      {c.email ? `${c.email} · ` : ''}{c.riferimento ? `rif. ${c.riferimento} · ` : ''}
                      {c.addebito_banca ? 'addebito in banca trovato' : 'addebito in banca non ancora trovato'}
                    </div>
                    <div style={{ color: c.associabile ? COLORS.success : COLORS.warning, fontSize: 12, fontWeight: 700, marginTop: 2 }}>
                      {c.associabile ? 'Coincide: ' : 'Da confermare tu · coincide: '}
                      {(c.evidenze || []).map(e => EVIDENZE[e] || e).join(', ') || 'solo importo'}
                    </div>
                  </div>
                  <Button size="sm" onClick={() => collegaPaypal(c)} disabled={!!collegando}
                    style={{ minHeight: 44 }} data-testid={`collega-paypal-${c.transaction_id}`}>
                    {collegando === c.transaction_id ? 'Collego…' : 'È questo'}
                  </Button>
                </div>
              ))}
            </>
          )}
          <div style={{ marginTop: 8 }}>
            <AssociaBonificoFattura fattura={fattura} onSuccess={onAggiornata}
              buttonLabel="Cerca il bonifico in banca" buttonStyle={{ minHeight: 44 }} />
          </div>
        </div>
      )}
    </Card>
  );
}

export default function FattureEstereVerifica() {
  const [fatture, setFatture] = useState([]);
  const [affidabilita, setAffidabilita] = useState([]);
  const [confermate, setConfermate] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pdfDoc, setPdfDoc] = useState(null);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const [daVerificare, rating, verificate] = await Promise.all([
        api.get('/api/fatture-estere/da-verificare'),
        api.get('/api/fatture-estere/affidabilita'),
        api.get('/api/fatture-estere/verificate'),
      ]);
      setFatture(daVerificare.data.fatture || []);
      setAffidabilita(rating.data.fornitori || []);
      setConfermate(verificate.data.fatture || []);
    } catch (e) {
      toast.error('Errore caricamento fatture estere', { description: e.response?.data?.detail || e.message });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const ratingPer = piva => affidabilita.find(r => r.supplier_vat === piva);

  const ricaricaConfermate = useCallback(async () => {
    try {
      const { data } = await api.get('/api/fatture-estere/verificate');
      setConfermate(data.fatture || []);
    } catch (e) {
      toast.error('Errore caricamento fatture confermate', { description: e.response?.data?.detail || e.message });
    }
  }, []);

  // La fattura confermata non sparisce: passa in «Confermate», col suo pagamento.
  const onVerificata = id => {
    setFatture(f => f.filter(x => x.id !== id));
    ricaricaConfermate();
  };

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '16px 0' }}>
      <PageHeader
        icon={<FileSearch size={20} />}
        title="Fatture estere da verificare"
        subtitle="Dati letti dall'intelligenza artificiale dal PDF: conferma o correggi prima che vengano usati per la riconciliazione"
      />

      <div style={{
        background: COLORS.infoLight, border: `1px solid ${COLORS.info}`, borderRadius: BORDER_RADIUS.md,
        padding: '10px 14px', fontSize: 13, color: COLORS.text, marginBottom: 16,
      }}>
        Ogni fattura estera arrivata via email viene letta automaticamente dall'AI.
        Controlla numero, data, fornitore e importi confrontandoli col PDF originale:
        se sono giusti premi "Conferma / Correggi" senza modificare nulla, se sono
        sbagliati correggili prima di confermare. Ogni verifica costruisce lo
        storico di affidabilità del fornitore mostrato qui sopra ogni riga.
      </div>

      {loading ? (
        <div style={{ color: COLORS.textMuted, padding: 24 }}>Caricamento…</div>
      ) : fatture.length === 0 ? (
        <div style={{ color: COLORS.textMuted, padding: 24, textAlign: 'center' }}>
          Nessuna fattura estera in attesa di verifica.
        </div>
      ) : (
        fatture.map(f => (
          <RigaFattura
            key={f.id}
            fattura={f}
            rating={ratingPer(f.supplier_vat)}
            onVerificata={onVerificata}
            onVediPdf={setPdfDoc}
          />
        ))
      )}

      {!loading && confermate.length > 0 && (
        <div style={{ marginTop: 28 }} data-testid="fatture-estere-confermate">
          <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: '0.04em', textTransform: 'uppercase', color: COLORS.textMuted, marginBottom: 10 }}>
            Confermate ({confermate.length}) · come sono state pagate
          </div>
          {confermate.map(f => (
            <RigaConfermata key={f.id} fattura={f} onAggiornata={ricaricaConfermate} onVediPdf={setPdfDoc} />
          ))}
        </div>
      )}

      {pdfDoc && (
        <VisoreOriginale
          title={`${pdfDoc.filename}`}
          url={urlOriginale({ tipo: 'documento', id: pdfDoc.documento_inbox_id })}
          onClose={() => setPdfDoc(null)}
          maxWidth={1000}
        />
      )}
    </div>
  );
}
