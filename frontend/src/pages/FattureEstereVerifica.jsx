import React, { useState, useEffect, useCallback } from 'react';
import { COLORS, BORDER_RADIUS } from '../lib/utils';
import { Button, Badge, Card, PageHeader, Input } from '../components/ds';
import { toast } from 'sonner';
import { CheckCircle2, FileSearch, Eye } from 'lucide-react';
import DocumentViewerModal from '../components/DocumentViewerModal';
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

function formatEuro(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString('it-IT', { style: 'currency', currency: 'EUR' }) : '-';
}

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
      if (res.data.esito === 'corretta') {
        toast.success('Correzione salvata', {
          description: `Campi corretti: ${res.data.campi_corretti.join(', ')}`,
        });
      } else {
        toast.success('Lettura confermata corretta');
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

export default function FattureEstereVerifica() {
  const [fatture, setFatture] = useState([]);
  const [affidabilita, setAffidabilita] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pdfDoc, setPdfDoc] = useState(null);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const [daVerificare, rating] = await Promise.all([
        api.get('/api/fatture-estere/da-verificare'),
        api.get('/api/fatture-estere/affidabilita'),
      ]);
      setFatture(daVerificare.data.fatture || []);
      setAffidabilita(rating.data.fornitori || []);
    } catch (e) {
      toast.error('Errore caricamento fatture estere', { description: e.response?.data?.detail || e.message });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const ratingPer = piva => affidabilita.find(r => r.supplier_vat === piva);

  const onVerificata = id => setFatture(f => f.filter(x => x.id !== id));

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

      {pdfDoc && (
        <DocumentViewerModal
          title={`📄 ${pdfDoc.filename}`}
          fetchUrl={`/api/documenti/documento/${pdfDoc.documento_inbox_id}/download`}
          onClose={() => setPdfDoc(null)}
          maxWidth={1000}
        />
      )}
    </div>
  );
}
