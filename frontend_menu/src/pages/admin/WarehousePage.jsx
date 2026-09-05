import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import { Plus, ArrowUpCircle, ArrowDownCircle, Trash2, AlertTriangle, Loader2, Search } from 'lucide-react';
import AdminPageHeader from '../../components/admin/AdminPageHeader';
import { useAdminAuth } from '../../hooks/useAdminAuth';
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from '../../components/ui/table';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter
} from '../../components/ui/dialog';
import { toast } from '../../hooks/use-toast';

const BACKEND_URL = process.env.REACT_APP_MENU_BACKEND_URL;

const NewItemDialog = ({ onCreated, authHeader }) => {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [unit, setUnit] = useState('pz');
  const [quantity, setQuantity] = useState('0');
  const [minThreshold, setMinThreshold] = useState('');
  const [category, setCategory] = useState('');
  const [supplier, setSupplier] = useState('');

  const submit = async () => {
    if (!name.trim()) return;
    try {
      await axios.post(`${BACKEND_URL}/api/warehouse/items`, {
        name,
        unit,
        quantity: parseFloat(quantity) || 0,
        min_threshold: minThreshold ? parseFloat(minThreshold) : null,
        category: category || null,
        supplier: supplier || null
      }, { headers: authHeader });
      setOpen(false);
      setName(''); setUnit('pz'); setQuantity('0'); setMinThreshold(''); setCategory(''); setSupplier('');
      onCreated();
    } catch {
      toast({ title: 'Errore', description: 'Impossibile creare l\'articolo', variant: 'destructive' });
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button className="bg-[#4a5d4a] hover:bg-[#3d4d3d]">
          <Plus className="w-4 h-4 mr-2" /> Nuovo articolo
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nuovo articolo di magazzino</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>Nome</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="es. Caffè in grani Kimbo" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Unità di misura</Label>
              <Input value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="pz, kg, l..." />
            </div>
            <div>
              <Label>Quantità iniziale</Label>
              <Input type="number" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Soglia minima (opzionale)</Label>
              <Input type="number" value={minThreshold} onChange={(e) => setMinThreshold(e.target.value)} />
            </div>
            <div>
              <Label>Categoria (opzionale)</Label>
              <Input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="Bar, Cucina, Bevande..." />
            </div>
          </div>
          <div>
            <Label>Fornitore (opzionale)</Label>
            <Input value={supplier} onChange={(e) => setSupplier(e.target.value)} placeholder="es. Big Food Srl" />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={submit} className="bg-[#4a5d4a] hover:bg-[#3d4d3d]">Crea</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const MovementDialog = ({ item, type, onDone, authHeader }) => {
  const [open, setOpen] = useState(false);
  const [quantity, setQuantity] = useState('');
  const [note, setNote] = useState('');

  const label = type === 'carico' ? 'Carico' : 'Scarico';

  const submit = async () => {
    const qty = parseFloat(quantity);
    if (!qty || qty <= 0) return;
    try {
      await axios.post(`${BACKEND_URL}/api/warehouse/items/${item.id}/movement`, {
        type,
        quantity: qty,
        note: note || null
      }, { headers: authHeader });
      setOpen(false);
      setQuantity('');
      setNote('');
      onDone();
    } catch {
      toast({ title: 'Errore', description: 'Movimento non riuscito', variant: 'destructive' });
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="icon" variant="ghost" title={label}>
          {type === 'carico'
            ? <ArrowUpCircle className="w-5 h-5 text-emerald-600" />
            : <ArrowDownCircle className="w-5 h-5 text-amber-600" />}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{label} — {item.name}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>Quantità ({item.unit})</Label>
            <Input type="number" value={quantity} onChange={(e) => setQuantity(e.target.value)} autoFocus />
          </div>
          <div>
            <Label>Nota (opzionale)</Label>
            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="es. consegna fornitore, sfrido..." />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={submit} className="bg-[#4a5d4a] hover:bg-[#3d4d3d]">Conferma</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const WarehousePage = () => {
  const { checking, authorized, authHeader } = useAdminAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  const loadItems = useCallback(async () => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/warehouse/items`, { headers: authHeader });
      setItems(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [authHeader.Authorization]);

  useEffect(() => {
    if (authorized) loadItems();
  }, [authorized, loadItems]);

  const handleDelete = async (id, name) => {
    if (!window.confirm(`Eliminare "${name}"?\n\nQuesto magazzino è condiviso con Lotti: l'articolo verrà rimosso da entrambi i sistemi.`)) return;
    try {
      await axios.delete(`${BACKEND_URL}/api/warehouse/items/${id}`, { headers: authHeader });
      loadItems();
    } catch {
      toast({ title: 'Errore', description: 'Eliminazione non riuscita', variant: 'destructive' });
    }
  };

  const filteredItems = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter((i) =>
      (i.name || '').toLowerCase().includes(q) ||
      (i.category || '').toLowerCase().includes(q) ||
      (i.supplier || '').toLowerCase().includes(q)
    );
  }, [items, search]);

  if (checking) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-[#4a5d4a]" />
      </div>
    );
  }

  const lowStock = items.filter((i) => i.min_threshold != null && i.quantity <= i.min_threshold);

  return (
    <div className="min-h-screen bg-gray-50">
      <AdminPageHeader title="Magazzino" subtitle="Collegato al magazzino condiviso di Lotti" />
      <div className="max-w-7xl mx-auto px-4 py-6">
        {lowStock.length > 0 && (
          <div className="bg-amber-50 border border-amber-300 rounded-lg p-3 mb-4 flex items-center gap-2 text-amber-800 text-sm">
            <AlertTriangle className="w-4 h-4" />
            {lowStock.length} articoli sotto la soglia minima: {lowStock.map((i) => i.name).join(', ')}
          </div>
        )}
        <div className="bg-white rounded-lg shadow p-4">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-4">
            <h2 className="font-bold">Articoli ({filteredItems.length}{search ? ` di ${items.length}` : ''})</h2>
            <div className="flex items-center gap-2 w-full sm:w-auto">
              <div className="relative flex-1 sm:w-64">
                <Search className="w-4 h-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Cerca per nome, categoria, fornitore..."
                  className="pl-8"
                />
              </div>
              <NewItemDialog onCreated={loadItems} authHeader={authHeader} />
            </div>
          </div>
          {loading ? (
            <Loader2 className="w-6 h-6 animate-spin text-[#4a5d4a]" />
          ) : items.length === 0 ? (
            <p className="text-gray-400 text-sm py-6 text-center">Nessun articolo in magazzino. Aggiungine uno per iniziare.</p>
          ) : filteredItems.length === 0 ? (
            <p className="text-gray-400 text-sm py-6 text-center">Nessun articolo trovato per "{search}".</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Categoria</TableHead>
                  <TableHead>Fornitore</TableHead>
                  <TableHead>Giacenza</TableHead>
                  <TableHead>Soglia min.</TableHead>
                  <TableHead className="text-right">Azioni</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredItems.map((item) => {
                  const low = item.min_threshold != null && item.quantity <= item.min_threshold;
                  return (
                    <TableRow key={item.id} className={low ? 'bg-amber-50' : ''}>
                      <TableCell className="font-medium">{item.name}</TableCell>
                      <TableCell>{item.category || '—'}</TableCell>
                      <TableCell>{item.supplier || '—'}</TableCell>
                      <TableCell className={low ? 'text-amber-700 font-semibold' : ''}>
                        {item.quantity} {item.unit}
                      </TableCell>
                      <TableCell>{item.min_threshold != null ? `${item.min_threshold} ${item.unit}` : '—'}</TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end items-center gap-1">
                          <MovementDialog item={item} type="carico" onDone={loadItems} authHeader={authHeader} />
                          <MovementDialog item={item} type="scarico" onDone={loadItems} authHeader={authHeader} />
                          <Button size="icon" variant="ghost" onClick={() => handleDelete(item.id, item.name)}>
                            <Trash2 className="w-4 h-4 text-red-500" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </div>
      </div>
    </div>
  );
};

export default WarehousePage;
