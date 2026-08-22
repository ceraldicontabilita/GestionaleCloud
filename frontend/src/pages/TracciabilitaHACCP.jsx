import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, BookOpen, ChefHat, ClipboardCheck,
  Layers, PackageCheck, RefreshCw, ScanLine, Settings, Thermometer,
} from 'lucide-react';
import { toast } from 'sonner';

import api from '../api';
import { Badge, Button, Card, Input, PageHeader, StatCard } from '../components/ds';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { useAuth } from '../contexts/AuthContext';
import { COLORS } from '../lib/utils';

const TODAY = new Date().toISOString().slice(0, 10);
const EMPTY_OVERVIEW = {
  purchase_lines: 0, requiring_review: 0, lots: 0, expired_lots: 0,
  register_entries: 0, non_compliant: 0, open_expectations: 0,
  recipes: 0, productions: 0, equipment: 0,
};
const TABS = [
  ['ricezioni', 'Ricezioni e lotti'],
  ['registri', 'Controlli HACCP'],
  ['ricette', 'Ricette'],
  ['produzioni', 'Produzioni'],
  ['attrezzature', 'Attrezzature'],
  ['manuale', 'Registro e manuale'],
];

function dateIt(value) {
  if (!value) return '—';
  const [year, month, day] = String(value).slice(0, 10).split('-');
  return year && month && day ? `${day}/${month}/${year}` : value;
}

function operationId(prefix) {
  return globalThis.crypto?.randomUUID?.() || `${prefix}-${Date.now()}-${Math.random()}`;
}

function errorMessage(error) {
  return error.response?.data?.detail || error.message || 'Errore inatteso';
}

const fieldStyle = { display: 'grid', gap: 5, fontSize: 13, color: COLORS.textMuted };
const gridStyle = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(185px, 1fr))', gap: 10 };
const selectStyle = { border: `1px solid ${COLORS.border}`, borderRadius: 7, padding: '8px 10px', minHeight: 36, background: '#fff' };
const textareaStyle = { ...selectStyle, width: '100%', resize: 'vertical', fontFamily: 'inherit' };

function LotForm({ line, onCreated }) {
  const [form, setForm] = useState({
    lot_number: line.document_lot_number || '',
    expiry_date: line.document_expiry_date || '',
    quantity_received: line.quantity_remaining || line.quantity || '1',
    received_date: TODAY,
  });
  const [saving, setSaving] = useState(false);
  const submit = async event => {
    event.preventDefault(); setSaving(true);
    try {
      const response = await api.post('/api/haccp/lots', { purchase_line_id: line.canonical_id, ...form });
      toast.success(response.data.created ? 'Lotto registrato' : 'Lotto già presente');
      await onCreated();
    } catch (error) { toast.error('Impossibile registrare il lotto', { description: errorMessage(error) }); }
    finally { setSaving(false); }
  };
  const set = (key, value) => setForm(current => ({ ...current, [key]: value }));
  return <form onSubmit={submit} style={{ ...gridStyle, marginTop: 12 }}>
    <Input aria-label={`Numero lotto ${line.description}`} placeholder="Numero lotto" required value={form.lot_number} onChange={event => set('lot_number', event.target.value)} />
    <Input aria-label={`Scadenza ${line.description}`} type="date" required value={form.expiry_date} onChange={event => set('expiry_date', event.target.value)} />
    <Input aria-label={`Quantità ${line.description}`} inputMode="decimal" required value={form.quantity_received} onChange={event => set('quantity_received', event.target.value)} />
    <Input aria-label={`Data ricezione ${line.description}`} type="date" required value={form.received_date} onChange={event => set('received_date', event.target.value)} />
    <Button type="submit" disabled={saving} iconLeft={<PackageCheck size={16} />}>{saving ? 'Registro…' : 'Registra lotto'}</Button>
  </form>;
}

function LotCard({ lot, canWrite, onChanged }) {
  const [trace, setTrace] = useState(null);
  const [quantity, setQuantity] = useState('');
  const [movementType, setMovementType] = useState('CONSUMO');
  const [reason, setReason] = useState('');
  const loadTrace = async () => {
    try { const response = await api.get(`/api/haccp/lots/${encodeURIComponent(lot.canonical_id)}/trace`); setTrace(response.data); }
    catch (error) { toast.error('Storia lotto non disponibile', { description: errorMessage(error) }); }
  };
  const submit = async event => {
    event.preventDefault();
    try {
      await api.post(`/api/haccp/lots/${encodeURIComponent(lot.canonical_id)}/movements`, { movement_type: movementType, quantity, reason, client_operation_id: operationId('lot') });
      toast.success(movementType === 'SCARTO' ? 'Scarto registrato' : 'Consumo registrato');
      setQuantity(''); setReason(''); await onChanged(); await loadTrace();
    } catch (error) { toast.error('Movimento non registrato', { description: errorMessage(error) }); }
  };
  return <Card style={{ padding: 15 }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}><strong>{lot.product_description}</strong><Badge variant={lot.status === 'ATTIVO' ? 'success' : 'warning'}>{lot.status}</Badge></div>
    <div style={{ marginTop: 8, color: COLORS.textMuted, fontSize: 13 }}>Lotto <strong>{lot.lot_number}</strong> · scadenza {dateIt(lot.expiry_date)}</div>
    <div style={{ marginTop: 4, color: COLORS.textMuted, fontSize: 13 }}>{lot.quantity_available} {lot.unit} disponibili {lot.supplier_name ? `· ${lot.supplier_name}` : ''}</div>
    <Button variant="secondary" size="sm" style={{ marginTop: 10 }} onClick={trace ? () => setTrace(null) : loadTrace}>{trace ? 'Nascondi storia' : 'Vedi storia'}</Button>
    {trace && <div style={{ marginTop: 12, borderTop: `1px solid ${COLORS.border}`, paddingTop: 10 }}>
      {(trace.movements || []).map(item => <div key={item.canonical_id} style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 6 }}><strong>{item.movement_type}</strong> {item.quantity} {item.unit} · saldo {item.balance_after} {item.reason ? `· ${item.reason}` : ''}</div>)}
      {canWrite && lot.status === 'ATTIVO' && <form onSubmit={submit} style={{ ...gridStyle, marginTop: 10 }}><select aria-label={`Tipo movimento ${lot.lot_number}`} value={movementType} onChange={event => setMovementType(event.target.value)} style={selectStyle}><option value="CONSUMO">Consumo</option><option value="SCARTO">Scarto</option></select><Input aria-label={`Quantità scarico ${lot.lot_number}`} placeholder={`Quantità (${lot.unit || 'unità'})`} required value={quantity} onChange={event => setQuantity(event.target.value)} /><Input aria-label={`Motivo scarico ${lot.lot_number}`} placeholder="Motivo / produzione" value={reason} onChange={event => setReason(event.target.value)} /><Button type="submit" size="sm">Registra scarico</Button></form>}
    </div>}
  </Card>;
}

function ReceiptPanel({ anno, lines, lots, canWrite, isAdmin, reload }) {
  const [preview, setPreview] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const pending = lines.filter(line => line.status !== 'SODDISFATTO');
  const analyze = async () => {
    setSyncing(true);
    try { const response = await api.get('/api/haccp/sync-preview', { params: { anno } }); setPreview(response.data); }
    catch (error) { toast.error('Analisi non riuscita', { description: errorMessage(error) }); }
    finally { setSyncing(false); }
  };
  const synchronize = async () => {
    setSyncing(true);
    try { await api.post('/api/haccp/sync-invoices', { anno, dry_run: false }); setPreview(null); await reload(); toast.success('Fatture sincronizzate'); }
    catch (error) { toast.error('Sincronizzazione non riuscita', { description: errorMessage(error) }); }
    finally { setSyncing(false); }
  };
  return <>
    <Card style={{ padding: 18, marginBottom: 18 }}><div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}><div><h2 style={{ margin: 0, fontSize: 18 }}>Importa dalle fatture {anno}</h2><p style={{ color: COLORS.textMuted, fontSize: 13 }}>Anteprima senza scritture. Lotto e scadenza devono provenire dall’XML o dall’osservazione alla consegna.</p></div><Button onClick={analyze} disabled={syncing} iconLeft={<ScanLine size={16} />}>Analizza fatture</Button></div>
      {preview && <div data-testid="haccp-sync-preview" style={{ marginTop: 14, padding: 14, background: COLORS.bgAlt, borderRadius: 9 }}><strong>{preview.invoices} fatture · {preview.new_lines} righe nuove</strong><div style={{ color: COLORS.textMuted, fontSize: 13 }}>{preview.requiring_review} righe richiedono verifica</div>{isAdmin && preview.new_lines > 0 && <Button style={{ marginTop: 10 }} onClick={synchronize}>Importa righe</Button>}</div>}
    </Card>
    <h2 style={{ fontSize: 19 }}>Ricezioni da completare ({pending.length})</h2>
    {pending.length === 0 ? <Card style={{ padding: 20, color: COLORS.textMuted }}>Nessuna ricezione in attesa.</Card> : pending.map(line => <Card key={line.canonical_id} style={{ padding: 16, marginBottom: 12 }}><div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}><div><strong>{line.description}</strong><div style={{ color: COLORS.textMuted, fontSize: 13 }}>{line.supplier_name || 'Fornitore non indicato'} · fattura {line.invoice_number || '—'} del {dateIt(line.invoice_date)}</div></div><Badge variant="warning">{line.status}</Badge></div>{canWrite ? <LotForm line={line} onCreated={reload} /> : <p style={{ color: COLORS.textMuted }}>Profilo in sola lettura.</p>}</Card>)}
    <h2 style={{ fontSize: 19, marginTop: 26 }}>Lotti disponibili ({lots.length})</h2><div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(270px, 1fr))', gap: 12 }}>{lots.map(lot => <LotCard key={lot.canonical_id} lot={lot} canWrite={canWrite} onChanged={reload} />)}</div>
  </>;
}

function CorrectiveActionForm({ entry, reload }) {
  const [open, setOpen] = useState(false);
  const [action, setAction] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const submit = async event => {
    event.preventDefault(); setSaving(true);
    try {
      await api.post(`/api/haccp/registers/${encodeURIComponent(entry.canonical_id)}/resolve`, { corrective_action: action, verification_notes: notes });
      toast.success('Non conformità chiusa'); setOpen(false); await reload();
    } catch (error) { toast.error('Chiusura non riuscita', { description: errorMessage(error) }); }
    finally { setSaving(false); }
  };
  if (!open) return <Button size="sm" onClick={() => setOpen(true)}>Registra correzione</Button>;
  return <form onSubmit={submit} style={{ display: 'grid', gap: 6, minWidth: 260 }}><Input aria-label={`Azione correttiva ${entry.subject}`} required placeholder="Azione correttiva eseguita" value={action} onChange={event => setAction(event.target.value)} /><Input aria-label={`Verifica correzione ${entry.subject}`} placeholder="Verifica/evidenza" value={notes} onChange={event => setNotes(event.target.value)} /><div style={{ display: 'flex', gap: 6 }}><Button type="submit" size="sm" disabled={saving}>{saving ? 'Salvo…' : 'Conferma'}</Button><Button type="button" size="sm" variant="secondary" onClick={() => setOpen(false)}>Annulla</Button></div></form>;
}

function RegisterPanel({ types, entries, expectations, equipment, canWrite, reload }) {
  const [form, setForm] = useState({ register_type: 'TEMPERATURA_POSITIVA', event_date: TODAY, subject: '', operator: '', value: '', unit: '', equipment_id: '', compliant: '', corrective_action: '', notes: '' });
  const [saving, setSaving] = useState(false);
  const selected = types.find(item => item.id === form.register_type);
  const set = (key, value) => setForm(current => ({ ...current, [key]: value }));
  const submit = async event => {
    event.preventDefault(); setSaving(true);
    try { await api.post('/api/haccp/registers', { ...form, value: form.value || null, compliant: form.compliant === '' ? null : form.compliant === 'true', client_operation_id: operationId('control') }); toast.success('Controllo HACCP registrato'); setForm(current => ({ ...current, subject: '', value: '', corrective_action: '', notes: '' })); await reload(); }
    catch (error) { toast.error('Controllo non registrato', { description: errorMessage(error) }); }
    finally { setSaving(false); }
  };
  return <>
    {canWrite && <Card style={{ padding: 18, marginBottom: 18 }}><h2 style={{ marginTop: 0 }}>Nuovo controllo</h2><form onSubmit={submit} style={gridStyle}>
      <label style={fieldStyle}>Registro<select value={form.register_type} onChange={event => set('register_type', event.target.value)} style={selectStyle}>{types.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label><label style={fieldStyle}>Data<Input type="date" required value={form.event_date} onChange={event => set('event_date', event.target.value)} /></label><label style={fieldStyle}>Oggetto<Input required placeholder="Frigo 1, laboratorio, consegna…" value={form.subject} onChange={event => set('subject', event.target.value)} /></label><label style={fieldStyle}>Attrezzatura<select value={form.equipment_id} onChange={event => set('equipment_id', event.target.value)} style={selectStyle}><option value="">Nessuna / non applicabile</option>{equipment.map(item => <option key={item.canonical_id} value={item.canonical_id}>{item.name}</option>)}</select></label><label style={fieldStyle}>Valore {selected?.unit ? `(${selected.unit})` : ''}<Input inputMode="decimal" value={form.value} onChange={event => set('value', event.target.value)} /></label><label style={fieldStyle}>Esito dichiarato<select value={form.compliant} onChange={event => set('compliant', event.target.value)} style={selectStyle}><option value="">Calcola da soglie</option><option value="true">Conforme</option><option value="false">Non conforme</option></select></label><label style={fieldStyle}>Operatore<Input value={form.operator} onChange={event => set('operator', event.target.value)} /></label><label style={fieldStyle}>Azione correttiva<Input value={form.corrective_action} onChange={event => set('corrective_action', event.target.value)} /></label><label style={{ ...fieldStyle, gridColumn: '1 / -1' }}>Note<textarea rows="3" style={textareaStyle} value={form.notes} onChange={event => set('notes', event.target.value)} /></label><Button type="submit" disabled={saving} iconLeft={<ClipboardCheck size={16} />}>{saving ? 'Salvataggio…' : 'Registra controllo'}</Button>
    </form></Card>}
    <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 10 }}><h2 style={{ margin: 0, fontSize: 19 }}>Registro ({entries.length})</h2>{expectations.length > 0 && <Badge variant="warning">{expectations.length} azioni aperte</Badge>}</div>
    {entries.length === 0 ? <Card style={{ padding: 20, color: COLORS.textMuted }}>Nessun controllo registrato per l’anno.</Card> : entries.map(entry => <Card key={entry.canonical_id} style={{ padding: 14, marginBottom: 9 }}><div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}><div><strong>{entry.register_label}: {entry.subject}</strong><div style={{ color: COLORS.textMuted, fontSize: 13 }}>{dateIt(entry.event_date)} · {entry.operator} {entry.value ? `· ${entry.value} ${entry.unit}` : ''}</div>{entry.non_conformity_reasons?.length > 0 && <div style={{ color: COLORS.danger, fontSize: 13 }}>{entry.non_conformity_reasons.join('; ')}</div>}</div><div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}><Badge variant={entry.compliant ? 'success' : 'warning'}>{entry.compliant ? 'CONFORME' : 'NON CONFORME'}</Badge>{canWrite && entry.status !== 'SODDISFATTO' && <CorrectiveActionForm entry={entry} reload={reload} />}</div></div></Card>)}
  </>;
}

function RecipePanel({ recipes, canWrite, reload }) {
  const [form, setForm] = useState({ name: '', department: 'PASTICCERIA', yield_quantity: '1', yield_unit: 'pezzi', ingredients: '', instructions: '', allergens: '', shelf_life_days: '', storage: '' });
  const set = (key, value) => setForm(current => ({ ...current, [key]: value }));
  const parseIngredients = () => form.ingredients.split('\n').map(line => line.trim()).filter(Boolean).map(line => { const [name, quantity, unit, allergens = ''] = line.split('|').map(value => value.trim()); return { name, quantity, unit: unit || 'g', allergens: allergens.split(',').map(value => value.trim()).filter(Boolean) }; });
  const submit = async event => {
    event.preventDefault();
    try { await api.post('/api/haccp/recipes', { ...form, ingredients: parseIngredients(), allergens: form.allergens.split(',').map(value => value.trim()).filter(Boolean), shelf_life_days: form.shelf_life_days === '' ? null : Number(form.shelf_life_days), client_operation_id: operationId('recipe') }); toast.success('Ricetta salvata'); setForm(current => ({ ...current, name: '', ingredients: '', instructions: '' })); await reload(); }
    catch (error) { toast.error('Ricetta non salvata', { description: errorMessage(error) }); }
  };
  return <>
    {canWrite && <Card style={{ padding: 18, marginBottom: 18 }}><h2 style={{ marginTop: 0 }}>Nuova ricetta</h2><form onSubmit={submit} style={gridStyle}>
      <label style={fieldStyle}>Nome<Input required value={form.name} onChange={event => set('name', event.target.value)} /></label><label style={fieldStyle}>Reparto<Input value={form.department} onChange={event => set('department', event.target.value)} /></label><label style={fieldStyle}>Resa<Input required inputMode="decimal" value={form.yield_quantity} onChange={event => set('yield_quantity', event.target.value)} /></label><label style={fieldStyle}>Unità resa<Input value={form.yield_unit} onChange={event => set('yield_unit', event.target.value)} /></label><label style={fieldStyle}>Shelf life (giorni)<Input type="number" min="0" value={form.shelf_life_days} onChange={event => set('shelf_life_days', event.target.value)} /></label><label style={fieldStyle}>Conservazione<Input value={form.storage} onChange={event => set('storage', event.target.value)} /></label><label style={{ ...fieldStyle, gridColumn: '1 / -1' }}>Ingredienti — una riga: nome | quantità | unità | allergeni<textarea aria-label="Ingredienti ricetta" required rows="5" style={textareaStyle} placeholder="Farina 00 | 1 | kg | glutine" value={form.ingredients} onChange={event => set('ingredients', event.target.value)} /></label><label style={fieldStyle}>Allergeni aggiuntivi<Input placeholder="latte, uova" value={form.allergens} onChange={event => set('allergens', event.target.value)} /></label><label style={{ ...fieldStyle, gridColumn: '1 / -1' }}>Procedimento<textarea rows="4" style={textareaStyle} value={form.instructions} onChange={event => set('instructions', event.target.value)} /></label><Button type="submit" iconLeft={<BookOpen size={16} />}>Salva ricetta</Button>
    </form></Card>}
    <h2 style={{ fontSize: 19 }}>Ricettario ({recipes.length})</h2><div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(270px, 1fr))', gap: 12 }}>{recipes.map(recipe => <Card key={recipe.canonical_id} style={{ padding: 15 }}><div style={{ display: 'flex', justifyContent: 'space-between' }}><strong>{recipe.name}</strong><Badge variant="info">v{recipe.version}</Badge></div><div style={{ color: COLORS.textMuted, fontSize: 13, marginTop: 6 }}>{recipe.department} · resa {recipe.yield_quantity} {recipe.yield_unit}</div><div style={{ fontSize: 13, marginTop: 7 }}>{recipe.ingredients.map(item => `${item.name} ${item.quantity}${item.unit}`).join(' · ')}</div><div style={{ color: COLORS.textMuted, fontSize: 12, marginTop: 7 }}>Allergeni: {recipe.allergens?.join(', ') || 'da verificare'} · shelf life {recipe.shelf_life_days ?? 'da verificare'} giorni</div></Card>)}</div>
  </>;
}

function ProductionPanel({ recipes, lots, productions, canWrite, reload }) {
  const [form, setForm] = useState({ recipe_id: '', production_date: TODAY, quantity: '', unit: 'pezzi', lot_number: '', lot_id: '', lot_quantity: '', production_kind: 'STANDARD', operator: '', notes: '' });
  const set = (key, value) => setForm(current => ({ ...current, [key]: value }));
  const submit = async event => {
    event.preventDefault(); const ingredient_lots = form.lot_id && form.lot_quantity ? [{ lot_id: form.lot_id, quantity: form.lot_quantity }] : [];
    try { await api.post('/api/haccp/productions', { recipe_id: form.recipe_id, production_date: form.production_date, quantity: form.quantity, unit: form.unit, lot_number: form.lot_number, ingredient_lots, operator: form.operator, notes: form.notes, production_kind: form.production_kind, recovery_from_id: '', client_operation_id: operationId('production') }); toast.success('Produzione e lotto registrati'); setForm(current => ({ ...current, quantity: '', lot_number: '', lot_quantity: '' })); await reload(); }
    catch (error) { toast.error('Produzione non registrata', { description: errorMessage(error) }); }
  };
  return <>
    {canWrite && <Card style={{ padding: 18, marginBottom: 18 }}><h2 style={{ marginTop: 0 }}>Registra produzione</h2><form onSubmit={submit} style={gridStyle}>
      <label style={fieldStyle}>Ricetta<select required value={form.recipe_id} onChange={event => set('recipe_id', event.target.value)} style={selectStyle}><option value="">Seleziona ricetta</option>{recipes.map(item => <option key={item.canonical_id} value={item.canonical_id}>{item.name}</option>)}</select></label><label style={fieldStyle}>Data<Input type="date" required value={form.production_date} onChange={event => set('production_date', event.target.value)} /></label><label style={fieldStyle}>Quantità prodotta<Input required inputMode="decimal" value={form.quantity} onChange={event => set('quantity', event.target.value)} /></label><label style={fieldStyle}>Unità<Input value={form.unit} onChange={event => set('unit', event.target.value)} /></label><label style={fieldStyle}>Lotto prodotto<Input placeholder="automatico se vuoto" value={form.lot_number} onChange={event => set('lot_number', event.target.value)} /></label><label style={fieldStyle}>Tipo<select value={form.production_kind} onChange={event => set('production_kind', event.target.value)} style={selectStyle}><option value="STANDARD">Standard</option><option value="GELATO">Gelato</option><option value="SEMILAVORATO">Semilavorato</option><option value="RECUPERO">Recupero controllato</option></select></label><label style={fieldStyle}>Lotto ingrediente<select required value={form.lot_id} onChange={event => set('lot_id', event.target.value)} style={selectStyle}><option value="">Seleziona il lotto consumato</option>{lots.filter(item => item.status === 'ATTIVO').map(item => <option key={item.canonical_id} value={item.canonical_id}>{item.product_description} · {item.lot_number} · {item.quantity_available}{item.unit}</option>)}</select></label><label style={fieldStyle}>Quantità ingrediente<Input required inputMode="decimal" value={form.lot_quantity} onChange={event => set('lot_quantity', event.target.value)} /></label><label style={fieldStyle}>Operatore<Input value={form.operator} onChange={event => set('operator', event.target.value)} /></label><label style={{ ...fieldStyle, gridColumn: '1 / -1' }}>Note<textarea rows="3" style={textareaStyle} value={form.notes} onChange={event => set('notes', event.target.value)} /></label><Button type="submit" iconLeft={<ChefHat size={16} />}>Registra produzione</Button>
    </form></Card>}
    <h2 style={{ fontSize: 19 }}>Storico produzioni ({productions.length})</h2>{productions.map(item => <Card key={item.canonical_id} style={{ padding: 14, marginBottom: 9 }}><div style={{ display: 'flex', justifyContent: 'space-between' }}><strong>{item.recipe_name}</strong><Badge variant="success">{item.status}</Badge></div><div style={{ color: COLORS.textMuted, fontSize: 13 }}>{dateIt(item.production_date)} · lotto {item.lot_number} · {item.quantity} {item.unit} · {item.production_kind}</div></Card>)}
  </>;
}

function EquipmentPanel({ equipment, isAdmin, reload }) {
  const [form, setForm] = useState({ name: '', equipment_type: 'FRIGO', threshold_min: '', threshold_max: '', location: '' });
  const set = (key, value) => setForm(current => ({ ...current, [key]: value }));
  const submit = async event => {
    event.preventDefault();
    try { await api.post('/api/haccp/equipment', { ...form, client_operation_id: operationId('equipment') }); toast.success('Attrezzatura salvata'); setForm(current => ({ ...current, name: '' })); await reload(); }
    catch (error) { toast.error('Attrezzatura non salvata', { description: errorMessage(error) }); }
  };
  return <>{isAdmin && <Card style={{ padding: 18, marginBottom: 18 }}><h2 style={{ marginTop: 0 }}>Nuova attrezzatura</h2><form onSubmit={submit} style={gridStyle}><label style={fieldStyle}>Nome<Input required value={form.name} onChange={event => set('name', event.target.value)} /></label><label style={fieldStyle}>Tipo<Input required value={form.equipment_type} onChange={event => set('equipment_type', event.target.value)} /></label><label style={fieldStyle}>Soglia minima<Input inputMode="decimal" value={form.threshold_min} onChange={event => set('threshold_min', event.target.value)} /></label><label style={fieldStyle}>Soglia massima<Input inputMode="decimal" value={form.threshold_max} onChange={event => set('threshold_max', event.target.value)} /></label><label style={fieldStyle}>Posizione<Input value={form.location} onChange={event => set('location', event.target.value)} /></label><Button type="submit" iconLeft={<Settings size={16} />}>Salva</Button></form></Card>}<h2 style={{ fontSize: 19 }}>Attrezzature ({equipment.length})</h2><div style={gridStyle}>{equipment.map(item => <Card key={item.canonical_id} style={{ padding: 14 }}><strong>{item.name}</strong><div style={{ color: COLORS.textMuted, fontSize: 13 }}>{item.equipment_type} · {item.location || 'posizione non indicata'}</div><div style={{ fontSize: 13 }}>Soglie: {item.threshold_min || '—'} / {item.threshold_max || '—'}</div></Card>)}</div></>;
}

function ManualPanel({ anno, entries, recipes, productions, expectations }) {
  return <Card style={{ padding: 20 }}><h2 style={{ marginTop: 0 }}>Registro HACCP integrato {anno}</h2><p>Questa area sostituisce il vecchio progetto Lotti senza riattivare MongoDB. Conserva ricezioni, tracciabilità, temperature positive e negative, temperature di cottura, sanificazioni, disinfestazioni, olio di frittura, anomalie, allergeni, schede tecniche, formazione, manutenzioni e collaudi.</p><p>Ricette, gelati e semilavorati confluiscono nel ricettario versionato e nello storico produzioni. Fatture, fornitori, corrispettivi e ordini restano nei moduli canonici del gestionale.</p><div style={{ ...gridStyle, marginTop: 18 }}><StatCard label="Controlli" value={entries.length} icon={<ClipboardCheck size={17} />} /><StatCard label="Ricette" value={recipes.length} icon={<BookOpen size={17} />} /><StatCard label="Produzioni" value={productions.length} icon={<ChefHat size={17} />} /><StatCard label="Azioni aperte" value={expectations.length} accent={expectations.length ? 'warning' : 'success'} icon={<AlertTriangle size={17} />} /></div><Button variant="secondary" style={{ marginTop: 18 }} onClick={() => globalThis.print?.()}>Stampa registro corrente</Button></Card>;
}

export default function TracciabilitaHACCP() {
  const { anno } = useAnnoGlobale();
  const { isAdmin, canWrite } = useAuth();
  const [active, setActive] = useState('ricezioni');
  const [data, setData] = useState({ overview: EMPTY_OVERVIEW, lines: [], lots: [], types: [], entries: [], expectations: [], equipment: [], recipes: [], productions: [] });
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [overview, lines, lots, types, entries, expectations, equipment, recipes, productions] = await Promise.all([
        api.get('/api/haccp/overview', { params: { anno } }), api.get('/api/haccp/purchase-lines', { params: { anno, limit: 500 } }), api.get('/api/haccp/lots', { params: { anno, limit: 500 } }), api.get('/api/haccp/register-types'), api.get('/api/haccp/registers', { params: { anno, limit: 1000 } }), api.get('/api/haccp/expectations', { params: { anno, aperte: true } }), api.get('/api/haccp/equipment'), api.get('/api/haccp/recipes'), api.get('/api/haccp/productions', { params: { anno } }),
      ]);
      setData({ overview: overview.data, lines: lines.data.items || [], lots: lots.data.items || [], types: types.data.items || [], entries: entries.data.items || [], expectations: expectations.data.items || [], equipment: equipment.data.items || [], recipes: recipes.data.items || [], productions: productions.data.items || [] });
    } catch (error) { toast.error('Errore nel caricamento HACCP', { description: errorMessage(error) }); }
    finally { setLoading(false); }
  }, [anno]);
  useEffect(() => { load(); }, [load]);
  const content = useMemo(() => {
    if (loading) return <Card style={{ padding: 24, color: COLORS.textMuted }}>Caricamento registri HACCP…</Card>;
    if (active === 'ricezioni') return <ReceiptPanel anno={anno} lines={data.lines} lots={data.lots} canWrite={canWrite} isAdmin={isAdmin} reload={load} />;
    if (active === 'registri') return <RegisterPanel types={data.types} entries={data.entries} expectations={data.expectations} equipment={data.equipment} canWrite={canWrite} reload={load} />;
    if (active === 'ricette') return <RecipePanel recipes={data.recipes} canWrite={canWrite} reload={load} />;
    if (active === 'produzioni') return <ProductionPanel recipes={data.recipes} lots={data.lots} productions={data.productions} canWrite={canWrite} reload={load} />;
    if (active === 'attrezzature') return <EquipmentPanel equipment={data.equipment} isAdmin={isAdmin} reload={load} />;
    return <ManualPanel anno={anno} entries={data.entries} recipes={data.recipes} productions={data.productions} expectations={data.expectations} />;
  }, [active, anno, canWrite, data, isAdmin, load, loading]);
  return <div style={{ maxWidth: 1220, margin: '0 auto', padding: '16px 0 40px' }}>
    <PageHeader icon={<Layers size={21} />} title="Tracciabilità e HACCP" subtitle={`Registri, ricette, produzioni e lotti ${anno} nell’archivio unico Drive/Sheets`} actions={<Button variant="secondary" onClick={load} disabled={loading} iconLeft={<RefreshCw size={16} />}>Aggiorna</Button>} />
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(145px, 1fr))', gap: 10, marginBottom: 16 }}><StatCard label="Righe merce" value={data.overview.purchase_lines} icon={<ScanLine size={17} />} /><StatCard label="Lotti" value={data.overview.lots} icon={<PackageCheck size={17} />} /><StatCard label="Controlli" value={data.overview.register_entries} icon={<Thermometer size={17} />} /><StatCard label="Azioni aperte" value={data.overview.open_expectations} accent={data.overview.open_expectations ? 'warning' : 'success'} icon={<AlertTriangle size={17} />} /><StatCard label="Ricette" value={data.overview.recipes} icon={<BookOpen size={17} />} /><StatCard label="Produzioni" value={data.overview.productions} icon={<ChefHat size={17} />} /></div>
    <nav aria-label="Sezioni HACCP" style={{ display: 'flex', gap: 7, flexWrap: 'wrap', marginBottom: 18 }}>{TABS.map(([id, label]) => <Button key={id} variant={active === id ? 'default' : 'secondary'} size="sm" onClick={() => setActive(id)}>{label}</Button>)}</nav>
    {content}
  </div>;
}
