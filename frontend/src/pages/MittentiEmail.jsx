import React, { useState, useEffect, useCallback } from 'react';
import { COLORS, BORDER_RADIUS } from '../lib/utils';
import { Button, Badge, Card, PageHeader, Input, Select, TableWrap, Table, Th, Td, RowActions, RowActionButton } from '../components/ds';
import { toast } from 'sonner';
import { useConfirm } from '../components/ui/ConfirmDialog';
import { Plus, Trash2, RefreshCw, Mail, Power, FileSearch } from 'lucide-react';
import { Link } from 'react-router-dom';
import api from '../api';

const TIPI_DOCUMENTO = [
  { value: 'fattura_estera_pdf', label: 'Fattura estera (PDF) — fornitori UE/extra-UE, niente SDI' },
  { value: 'cedolino', label: 'Cedolino / busta paga' },
  { value: 'pagopa', label: 'PagoPA' },
  { value: 'inps', label: 'INPS' },
  { value: 'inail', label: 'INAIL' },
  { value: 'paypal', label: 'PayPal' },
  { value: 'cartella_esattoriale', label: 'Cartella esattoriale' },
  { value: 'generico', label: 'Generico (solo archivio)' },
];

const labelTipo = v => (TIPI_DOCUMENTO.find(t => t.value === v) || {}).label || v;

export default function MittentiEmail() {
  const confirm = useConfirm();
  const [mittenti, setMittenti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ pattern: '', canale: 'gmail', tipo_documento: 'fattura_estera_pdf', descrizione: '' });
  const [salvando, setSalvando] = useState(false);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/email-download/mittenti');
      setMittenti(res.data.mittenti || []);
    } catch (e) {
      toast.error('Errore caricamento mittenti', { description: e.response?.data?.detail || e.message });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const aggiungi = async e => {
    e.preventDefault();
    if (!form.pattern.trim()) {
      toast.warning('Inserisci l\'indirizzo email o il dominio del mittente');
      return;
    }
    setSalvando(true);
    try {
      await api.post('/api/email-download/mittenti', form);
      toast.success(`Mittente "${form.pattern}" aggiunto`, {
        description: `Sarà processato ogni ora come "${labelTipo(form.tipo_documento)}"`,
      });
      setForm({ pattern: '', canale: 'gmail', tipo_documento: 'fattura_estera_pdf', descrizione: '' });
      carica();
    } catch (e2) {
      toast.error('Errore aggiunta mittente', { description: e2.response?.data?.detail || e2.message });
    } finally {
      setSalvando(false);
    }
  };

  const toggleAttivo = async m => {
    try {
      await api.put(`/api/email-download/mittenti/${m.id}`, { attivo: !m.attivo });
      toast.success(m.attivo ? 'Mittente disattivato' : 'Mittente riattivato');
      carica();
    } catch (e) {
      toast.error('Errore aggiornamento', { description: e.response?.data?.detail || e.message });
    }
  };

  const elimina = async m => {
    if (!(await confirm({
      title: 'Elimina mittente',
      message: `Eliminare "${m.pattern}"? Le email già scaricate non vengono toccate.`,
      variant: 'danger',
    }))) return;
    try {
      await api.delete(`/api/email-download/mittenti/${m.id}`);
      toast.success('Mittente eliminato');
      carica();
    } catch (e) {
      toast.error('Errore eliminazione', { description: e.response?.data?.detail || e.message });
    }
  };

  return (
    <div style={{ maxWidth: 980, margin: '0 auto', padding: '16px 0' }}>
      <PageHeader
        icon={<Mail size={20} />}
        title="Mittenti Email"
        subtitle="Indirizzi da cui il sistema scarica ed elabora documenti automaticamente, ogni ora"
      />

      <div style={{
        background: COLORS.infoLight, border: `1px solid ${COLORS.info}`, borderRadius: BORDER_RADIUS.md,
        padding: '10px 14px', fontSize: 13, color: COLORS.text, marginBottom: 12,
      }}>
        Le fatture <strong>italiane</strong> arrivano sempre via SDI/Aruba/Drive in formato XML
        (FatturaPA), mai da qui. I fornitori <strong>esteri</strong> non passano dallo SDI
        (sistema tutto italiano) e mandano un semplice <strong>PDF</strong> in allegato via
        email: aggiungili qui man mano che li scopri (dopo aver ricevuto la prima fattura),
        scegliendo il tipo <strong>"Fattura estera (PDF)"</strong> — il PDF verrà scaricato
        automaticamente entro un'ora, letto dall'intelligenza artificiale e registrato come
        fattura vera, in attesa che tu confermi o corregga i dati letti.
      </div>

      <Link to="/fatture-estere-verifica" style={{ textDecoration: 'none' }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: COLORS.warningLight, border: `1px solid ${COLORS.warning}`,
          borderRadius: BORDER_RADIUS.md, padding: '10px 14px', fontSize: 13,
          color: COLORS.text, marginBottom: 16, cursor: 'pointer',
        }}>
          <FileSearch size={16} />
          Vai alla coda di verifica delle fatture estere lette dall'AI →
        </div>
      </Link>

      <Card style={{ marginBottom: 20, padding: 16 }}>
        <form onSubmit={aggiungi} style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div style={{ flex: '1 1 240px' }}>
            <label style={lbl}>Mittente (email o dominio)</label>
            <Input
              value={form.pattern}
              onChange={e => setForm(f => ({ ...f, pattern: e.target.value }))}
              placeholder="es. fatture@fornitore-estero.com"
              data-testid="mittente-pattern-input"
            />
          </div>
          <div style={{ flex: '1 1 220px' }}>
            <label style={lbl}>Tipo documento</label>
            <Select
              value={form.tipo_documento}
              onChange={e => setForm(f => ({ ...f, tipo_documento: e.target.value }))}
              data-testid="mittente-tipo-select"
            >
              {TIPI_DOCUMENTO.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </Select>
          </div>
          <div style={{ flex: '1 1 200px' }}>
            <label style={lbl}>Descrizione (facoltativa)</label>
            <Input
              value={form.descrizione}
              onChange={e => setForm(f => ({ ...f, descrizione: e.target.value }))}
              placeholder="es. nome fornitore"
            />
          </div>
          <Button type="submit" iconLeft={<Plus size={16} />} disabled={salvando} data-testid="aggiungi-mittente-btn">
            {salvando ? 'Aggiungo…' : 'Aggiungi mittente'}
          </Button>
        </form>
      </Card>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <h3 style={{ margin: 0, fontSize: 15, color: COLORS.text }}>Mittenti configurati ({mittenti.length})</h3>
        <Button variant="secondary" size="sm" iconLeft={<RefreshCw size={14} />} onClick={carica}>
          Aggiorna
        </Button>
      </div>

      {loading ? (
        <div style={{ color: COLORS.textMuted, padding: 24 }}>Caricamento…</div>
      ) : mittenti.length === 0 ? (
        <div style={{ color: COLORS.textMuted, padding: 24, textAlign: 'center' }}>
          Nessun mittente configurato. Aggiungine uno quando ricevi la prima fattura estera.
        </div>
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Mittente</Th>
                <Th>Canale</Th>
                <Th>Tipo documento</Th>
                <Th>Descrizione</Th>
                <Th>Stato</Th>
                <Th></Th>
              </tr>
            </thead>
            <tbody>
              {mittenti.map(m => (
                <tr key={m.id || m.pattern} style={{ opacity: m.attivo ? 1 : 0.5 }} data-testid={`mittente-row-${m.pattern}`}>
                  <Td>{m.pattern}</Td>
                  <Td>{m.canale?.toUpperCase()}</Td>
                  <Td>
                    <Badge variant={m.tipo_documento === 'fattura_estera_pdf' ? 'primary' : 'neutral'}>
                      {labelTipo(m.tipo_documento)}
                    </Badge>
                  </Td>
                  <Td>{m.descrizione || '—'}</Td>
                  <Td>
                    <Badge variant={m.attivo ? 'success' : 'neutral'}>
                      {m.attivo ? 'Attivo' : 'Disattivo'}
                    </Badge>
                    {m.builtin && <Badge variant="info" style={{ marginLeft: 6 }}>predefinito</Badge>}
                  </Td>
                  <Td>
                    <RowActions>
                      <RowActionButton
                        variant={m.attivo ? 'neutral' : 'success'}
                        onClick={() => toggleAttivo(m)}
                        title={m.attivo ? 'Disattiva' : 'Riattiva'}
                      >
                        <Power size={14} />
                      </RowActionButton>
                      {!m.builtin && (
                        <RowActionButton variant="danger" onClick={() => elimina(m)} title="Elimina">
                          <Trash2 size={14} />
                        </RowActionButton>
                      )}
                    </RowActions>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </TableWrap>
      )}
    </div>
  );
}

const lbl = { display: 'block', color: COLORS.textMuted, fontSize: 12, marginBottom: 4 };
