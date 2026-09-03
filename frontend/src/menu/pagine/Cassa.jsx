import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Banknote, CreditCard, Euro, Loader2, Minus, Plus, Search, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { aggiornaPagamentoOrdine, caricaMenu, elencoOrdini, elencoSale, euro, messaggioErrore, ordineCassa, prezzoNumero } from '../api';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';

export default function Cassa() {
  const [categorie, setCategorie] = useState([]);
  const [search, setSearch] = useState('');
  const [cart, setCart] = useState([]);
  const [table, setTable] = useState('');
  const [unpaid, setUnpaid] = useState([]);
  const [loadingUnpaid, setLoadingUnpaid] = useState(true);
  const [sale, setSale] = useState([]);
  const [salaId, setSalaId] = useState('');
  const [numeroCoperti, setNumeroCoperti] = useState('1');

  useEffect(() => {
    caricaMenu().then((d) => setCategorie(d.categories || [])).catch(() => toast.error('Errore', { description: 'Menu non caricato' }));
    elencoSale().then(setSale).catch(() => {});
  }, []);

  const salaSelezionata = sale.find((s) => s.id === salaId);
  const copertoTotal = salaSelezionata?.coperto_attivo
    ? Math.round((parseFloat(salaSelezionata.coperto_importo) || 0) * (parseInt(numeroCoperti, 10) || 1) * 100) / 100
    : 0;

  const allProducts = useMemo(() => categorie.flatMap((c) => (c.subcategories || []).flatMap((s) => s.items || [])), [categorie]);
  const filtered = useMemo(() => {
    if (!search.trim()) return allProducts.slice(0, 30);
    const q = search.toLowerCase();
    return allProducts.filter((p) => (p.nameIT || p.name || '').toLowerCase().includes(q));
  }, [allProducts, search]);

  const addToCart = (p) => setCart((prev) => {
    const ex = prev.find((i) => i.product_id === p.id);
    if (ex) return prev.map((i) => (i.product_id === p.id ? { ...i, quantity: i.quantity + 1 } : i));
    return [...prev, { product_id: p.id, name: p.nameIT || p.name, price: p.price, quantity: 1 }];
  });
  const updateQty = (product_id, quantity) => setCart((prev) => (quantity <= 0 ? prev.filter((i) => i.product_id !== product_id) : prev.map((i) => (i.product_id === product_id ? { ...i, quantity } : i))));
  const total = cart.reduce((s, i) => s + prezzoNumero(i.price) * i.quantity, 0) + copertoTotal;

  const loadUnpaid = useCallback(async () => {
    try { setUnpaid((await elencoOrdini()).filter((o) => !o.paid && o.status !== 'annullato')); } catch (err) { console.error(err); } finally { setLoadingUnpaid(false); }
  }, []);
  useEffect(() => {
    loadUnpaid();
    const iv = setInterval(loadUnpaid, 8000);
    return () => clearInterval(iv);
  }, [loadUnpaid]);

  const submit = async (paymentMethod) => {
    if (cart.length === 0) return;
    try {
      await ordineCassa({
        items: cart, table, source: 'cassa', paid: true, payment_method: paymentMethod,
        sala_id: salaId || null, numero_coperti: salaSelezionata?.coperto_attivo ? (parseInt(numeroCoperti, 10) || 1) : null,
      });
      toast.success('Ordine registrato', { description: `Totale ${euro(total)}` });
      setCart([]); setTable(''); loadUnpaid();
    } catch (err) { toast.error('Errore', { description: messaggioErrore(err, "Impossibile registrare l'ordine") }); }
  };
  const markPaid = async (order, paymentMethod) => {
    try { await aggiornaPagamentoOrdine(order.id, true, paymentMethod); loadUnpaid(); } catch (err) { toast.error('Errore', { description: messaggioErrore(err, 'Impossibile segnare come pagato') }); }
  };

  return (
    <div>
      <h2 className="text-xl font-bold text-[#2a3329] mb-1">Cassa</h2>
      <p className="text-sm text-gray-500 mb-4">Ordini al banco e incassi</p>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <div className="bg-white rounded-lg shadow p-4 mb-4 border border-[#e6e0d4]">
            <div className="relative mb-3">
              <Search className="w-4 h-4 absolute left-3 top-3 text-gray-400" />
              <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cerca prodotto..." className="pl-9" />
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-h-[420px] overflow-y-auto">
              {filtered.map((p) => (
                <button key={p.id} onClick={() => addToCart(p)} className="text-left border border-[#e6e0d4] rounded-lg p-2 hover:bg-[#e8efe9] hover:border-[#5b7a6b] transition-colors">
                  <p className="text-sm font-medium truncate">{p.nameIT || p.name}</p>
                  <p className="text-xs text-gray-500">{p.price}</p>
                </button>
              ))}
              {filtered.length === 0 && <p className="col-span-full text-center text-gray-400 py-6">Nessun prodotto trovato</p>}
            </div>
          </div>
          <div className="bg-white rounded-lg shadow p-4 border border-[#e6e0d4]">
            <h3 className="font-bold mb-3">Da incassare</h3>
            {loadingUnpaid ? <Loader2 className="w-6 h-6 animate-spin text-[#5b7a6b]" /> : unpaid.length === 0 ? (
              <p className="text-gray-400 text-sm">Nessun ordine da incassare</p>
            ) : (
              <div className="space-y-2">
                {unpaid.map((o) => (
                  <div key={o.id} className="flex items-center justify-between border border-[#e6e0d4] rounded-lg p-3 gap-2 flex-wrap">
                    <div>
                      <p className="text-sm font-medium">{o.table ? `Tavolo ${o.table}` : o.id}{o.sala_nome ? ` — ${o.sala_nome}` : ''}</p>
                      <p className="text-xs text-gray-500">{o.items.length} prodotti{o.totale_coperto > 0 ? ` + coperto ${euro(o.totale_coperto)}` : ''} — {euro(o.total)}</p>
                    </div>
                    <div className="flex gap-2">
                      <Button size="sm" variant="outline" onClick={() => markPaid(o, 'contanti')}><Banknote className="w-4 h-4 mr-1" /> Contanti</Button>
                      <Button size="sm" variant="outline" onClick={() => markPaid(o, 'pos')}><CreditCard className="w-4 h-4 mr-1" /> POS</Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        <div>
          <div className="bg-white rounded-lg shadow p-4 sticky top-6 border border-[#e6e0d4]">
            <h3 className="font-bold mb-3">Ordine corrente</h3>
            <Input value={table} onChange={(e) => setTable(e.target.value)} placeholder="Tavolo / banco" className="mb-3" />
            {sale.length > 0 && (
              <div className="mb-3">
                <Select value={salaId} onValueChange={setSalaId}>
                  <SelectTrigger><SelectValue placeholder="Sala (opzionale)" /></SelectTrigger>
                  <SelectContent>
                    {sale.filter((s) => s.ordini_abilitati).map((s) => <SelectItem key={s.id} value={s.id}>{s.nome}{s.coperto_attivo ? ` — coperto ${euro(s.coperto_importo)}` : ''}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            )}
            {salaSelezionata?.coperto_attivo && (
              <div className="mb-3">
                <label className="text-xs text-gray-500">Numero coperti</label>
                <Input type="number" min="1" value={numeroCoperti} onChange={(e) => setNumeroCoperti(e.target.value)} />
              </div>
            )}
            {cart.length === 0 ? <p className="text-gray-400 text-sm py-6 text-center">Seleziona prodotti dall'elenco</p> : (
              <div className="space-y-2 mb-4">
                {cart.map((item) => (
                  <div key={item.product_id} className="flex items-center justify-between text-sm">
                    <span className="flex-1 truncate">{item.name}</span>
                    <div className="flex items-center gap-1">
                      <button onClick={() => updateQty(item.product_id, item.quantity - 1)} className="w-6 h-6 rounded bg-gray-100 flex items-center justify-center"><Minus className="w-3 h-3" /></button>
                      <span className="w-5 text-center">{item.quantity}</span>
                      <button onClick={() => updateQty(item.product_id, item.quantity + 1)} className="w-6 h-6 rounded bg-gray-100 flex items-center justify-center"><Plus className="w-3 h-3" /></button>
                      <button onClick={() => updateQty(item.product_id, 0)} className="w-6 h-6 rounded bg-gray-100 flex items-center justify-center text-[#d35f4e] ml-1"><Trash2 className="w-3 h-3" /></button>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="border-t border-[#e6e0d4] pt-3 mb-4">
              {copertoTotal > 0 && <div className="flex justify-between items-center text-sm text-gray-500 mb-1"><span>Coperto ({numeroCoperti}x)</span><span>{euro(copertoTotal)}</span></div>}
              <div className="flex justify-between items-center font-bold text-lg"><span>Totale</span><span className="flex items-center gap-1"><Euro className="w-4 h-4" /> {total.toFixed(2)}</span></div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Button disabled={cart.length === 0} onClick={() => submit('contanti')} className="bg-[#5b7a6b] hover:bg-[#3f5a4e] text-white"><Banknote className="w-4 h-4 mr-1" /> Contanti</Button>
              <Button disabled={cart.length === 0} onClick={() => submit('pos')} variant="outline"><CreditCard className="w-4 h-4 mr-1" /> POS</Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
