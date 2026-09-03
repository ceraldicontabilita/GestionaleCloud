import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ArrowDownCircle, ArrowUpCircle, Loader2, Plus, Search, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { articoliMagazzino, creaArticolo, eliminaArticolo, messaggioErrore, movimentoArticolo, soloLettura } from '../api';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '../ui/dialog';

const NewItemDialog = ({ onCreated }) => {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: '', unit: 'pz', quantity: '0', min_threshold: '', category: '', supplier: '' });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async () => {
    if (!form.name.trim()) return;
    try {
      await creaArticolo({
        name: form.name, unit: form.unit || 'pz', quantity: parseFloat(form.quantity) || 0,
        min_threshold: form.min_threshold ? parseFloat(form.min_threshold) : null,
        category: form.category || null, supplier: form.supplier || null,
      });
      setOpen(false); setForm({ name: '', unit: 'pz', quantity: '0', min_threshold: '', category: '', supplier: '' }); onCreated();
    } catch (err) { toast.error('Errore', { description: messaggioErrore(err, "Impossibile creare l'articolo") }); }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button className="bg-[#5b7a6b] hover:bg-[#3f5a4e] text-white"><Plus className="w-4 h-4 mr-2" /> Nuovo articolo</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Nuovo articolo di magazzino</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><Label>Nome</Label><Input value={form.name} onChange={set('name')} placeholder="es. Caffè in grani" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Unità di misura</Label><Input value={form.unit} onChange={set('unit')} placeholder="pz, cartone, kg..." /></div>
            <div><Label>Quantità iniziale</Label><Input type="number" value={form.quantity} onChange={set('quantity')} /></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Soglia minima (opzionale)</Label><Input type="number" value={form.min_threshold} onChange={set('min_threshold')} /></div>
            <div><Label>Categoria (opzionale)</Label><Input value={form.category} onChange={set('category')} placeholder="Bar, Bevande..." /></div>
          </div>
          <div><Label>Fornitore (opzionale)</Label><Input value={form.supplier} onChange={set('supplier')} /></div>
          <p className="text-xs text-gray-500">Le bevande e gli alcolici si gestiscono a cartone/bottiglia, mai a kg o litro.</p>
        </div>
        <DialogFooter><Button onClick={submit} className="bg-[#5b7a6b] hover:bg-[#3f5a4e] text-white">Crea</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const MovementDialog = ({ item, type, onDone }) => {
  const [open, setOpen] = useState(false);
  const [quantity, setQuantity] = useState('');
  const [note, setNote] = useState('');
  const label = type === 'carico' ? 'Carico' : 'Scarico';
  const submit = async () => {
    const qty = parseFloat(quantity);
    if (!qty || qty <= 0) return;
    try { await movimentoArticolo(item.id, { type, quantity: qty, note: note || null }); setOpen(false); setQuantity(''); setNote(''); onDone(); }
    catch (err) { toast.error('Errore', { description: messaggioErrore(err, 'Movimento non riuscito') }); }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="icon" variant="ghost" title={label}>
          {type === 'carico' ? <ArrowUpCircle className="w-5 h-5 text-emerald-600" /> : <ArrowDownCircle className="w-5 h-5 text-amber-600" />}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>{label} — {item.name}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><Label>Quantità ({item.unit})</Label><Input type="number" value={quantity} onChange={(e) => setQuantity(e.target.value)} autoFocus /></div>
          <div><Label>Nota (opzionale)</Label><Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="es. consegna fornitore, sfrido..." /></div>
        </div>
        <DialogFooter><Button onClick={submit} className="bg-[#5b7a6b] hover:bg-[#3f5a4e] text-white">Conferma</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default function Magazzino({ ruolo }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const lettura = soloLettura(ruolo);

  const load = useCallback(async () => {
    try { setItems(await articoliMagazzino()); } catch (err) { console.error(err); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const handleDelete = async (id, name) => {
    if (!window.confirm(`Eliminare "${name}"?\n\nQuesto magazzino è condiviso con Lotti: l'articolo verrà rimosso da entrambi i sistemi.`)) return;
    try { await eliminaArticolo(id); load(); } catch (err) { toast.error('Errore', { description: messaggioErrore(err, 'Eliminazione non riuscita') }); }
  };

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter((i) => [i.name, i.category, i.supplier].some((v) => (v || '').toLowerCase().includes(q)));
  }, [items, search]);
  const lowStock = items.filter((i) => i.min_threshold != null && i.quantity <= i.min_threshold);

  return (
    <div>
      <h2 className="text-xl font-bold text-[#2a3329] mb-1">Magazzino bar</h2>
      <p className="text-sm text-gray-500 mb-4">Collegato al magazzino condiviso di Lotti (collezione unica)</p>
      {lowStock.length > 0 && (
        <div className="bg-amber-50 border border-amber-300 rounded-lg p-3 mb-4 flex items-center gap-2 text-amber-800 text-sm">
          <AlertTriangle className="w-4 h-4" /> {lowStock.length} articoli sotto la soglia minima: {lowStock.map((i) => i.name).join(', ')}
        </div>
      )}
      <div className="bg-white rounded-lg shadow p-4 border border-[#e6e0d4]">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-4">
          <h3 className="font-bold">Articoli ({filtered.length}{search ? ` di ${items.length}` : ''})</h3>
          <div className="flex items-center gap-2 w-full sm:w-auto">
            <div className="relative flex-1 sm:w-64">
              <Search className="w-4 h-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
              <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cerca per nome, categoria, fornitore..." className="pl-8" />
            </div>
            {!lettura && <NewItemDialog onCreated={load} />}
          </div>
        </div>
        {loading ? <Loader2 className="w-6 h-6 animate-spin text-[#5b7a6b]" /> : items.length === 0 ? (
          <p className="text-gray-400 text-sm py-6 text-center">Nessun articolo in magazzino. Aggiungine uno per iniziare.</p>
        ) : filtered.length === 0 ? (
          <p className="text-gray-400 text-sm py-6 text-center">Nessun articolo trovato per "{search}".</p>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow><TableHead>Nome</TableHead><TableHead>Categoria</TableHead><TableHead>Fornitore</TableHead><TableHead>Giacenza</TableHead><TableHead>Soglia min.</TableHead><TableHead className="text-right">Azioni</TableHead></TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((item) => {
                  const low = item.min_threshold != null && item.quantity <= item.min_threshold;
                  return (
                    <TableRow key={item.id} className={low ? 'bg-amber-50' : ''}>
                      <TableCell className="font-medium">{item.name}</TableCell>
                      <TableCell>{item.category || '—'}</TableCell>
                      <TableCell>{item.supplier || '—'}</TableCell>
                      <TableCell className={low ? 'text-amber-700 font-semibold' : ''}>{item.quantity} {item.unit}</TableCell>
                      <TableCell>{item.min_threshold != null ? `${item.min_threshold} ${item.unit}` : '—'}</TableCell>
                      <TableCell className="text-right">
                        {!lettura && (
                          <div className="flex justify-end items-center gap-1">
                            <MovementDialog item={item} type="carico" onDone={load} />
                            <MovementDialog item={item} type="scarico" onDone={load} />
                            <Button size="icon" variant="ghost" onClick={() => handleDelete(item.id, item.name)}><Trash2 className="w-4 h-4 text-[#d35f4e]" /></Button>
                          </div>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
  );
}
