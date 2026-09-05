import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import { Search, Plus, Minus, Trash2, Euro, Loader2, Banknote, CreditCard } from 'lucide-react';
import AdminPageHeader from '../../components/admin/AdminPageHeader';
import { useAdminAuth } from '../../hooks/useAdminAuth';
import { useMenu } from '../../context/MenuContext';
import { Input } from '../../components/ui/input';
import { Button } from '../../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { toast } from '../../hooks/use-toast';

const BACKEND_URL = process.env.REACT_APP_MENU_BACKEND_URL;

const priceToNumber = (price) => parseFloat(String(price).replace('€', '').trim().replace(',', '.')) || 0;

const CounterPage = () => {
  const { checking, authorized, authHeader } = useAdminAuth();
  const { menuCategories } = useMenu();
  const [search, setSearch] = useState('');
  const [cart, setCart] = useState([]);
  const [table, setTable] = useState('');
  const [unpaid, setUnpaid] = useState([]);
  const [loadingUnpaid, setLoadingUnpaid] = useState(true);
  const [sale, setSale] = useState([]);
  const [salaId, setSalaId] = useState('');
  const [numeroCoperti, setNumeroCoperti] = useState('1');

  useEffect(() => {
    axios.get(`${BACKEND_URL}/api/sale/`, { headers: authHeader })
      .then((res) => setSale(res.data))
      .catch(() => {});
  }, [authHeader.Authorization]);

  const salaSelezionata = sale.find((s) => s.id === salaId);
  const copertoTotal = salaSelezionata?.coperto_attivo
    ? Math.round((parseFloat(salaSelezionata.coperto_importo) || 0) * (parseInt(numeroCoperti, 10) || 1) * 100) / 100
    : 0;

  const allProducts = useMemo(() => {
    const list = [];
    for (const cat of menuCategories) {
      for (const sub of cat.subcategories || []) {
        for (const item of sub.items || []) {
          list.push(item);
        }
      }
    }
    return list;
  }, [menuCategories]);

  const filtered = useMemo(() => {
    if (!search.trim()) return allProducts.slice(0, 30);
    const q = search.toLowerCase();
    return allProducts.filter((p) => (p.nameIT || p.name || '').toLowerCase().includes(q));
  }, [allProducts, search]);

  const addToCart = (product) => {
    setCart((prev) => {
      const existing = prev.find((i) => i.product_id === product.id);
      if (existing) {
        return prev.map((i) => (i.product_id === product.id ? { ...i, quantity: i.quantity + 1 } : i));
      }
      return [...prev, { product_id: product.id, name: product.nameIT || product.name, price: product.price, quantity: 1 }];
    });
  };

  const updateQty = (product_id, quantity) => {
    setCart((prev) => (quantity <= 0
      ? prev.filter((i) => i.product_id !== product_id)
      : prev.map((i) => (i.product_id === product_id ? { ...i, quantity } : i))));
  };

  const productsTotal = cart.reduce((sum, i) => sum + priceToNumber(i.price) * i.quantity, 0);
  const total = productsTotal + copertoTotal;

  const loadUnpaid = useCallback(async () => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/orders/`, { headers: authHeader });
      setUnpaid(res.data.filter((o) => !o.paid && o.status !== 'annullato'));
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingUnpaid(false);
    }
  }, [authHeader.Authorization]);

  useEffect(() => {
    if (!authorized) return;
    loadUnpaid();
    const interval = setInterval(loadUnpaid, 8000);
    return () => clearInterval(interval);
  }, [authorized, loadUnpaid]);

  const submitCounterOrder = async (paymentMethod) => {
    if (cart.length === 0) return;
    try {
      await axios.post(`${BACKEND_URL}/api/orders/`, {
        items: cart,
        table,
        source: 'cassa',
        paid: true,
        payment_method: paymentMethod,
        sala_id: salaId || null,
        numero_coperti: salaSelezionata?.coperto_attivo ? (parseInt(numeroCoperti, 10) || 1) : null,
      }, { headers: authHeader });
      toast({ title: 'Ordine registrato', description: `Totale € ${total.toFixed(2)}` });
      setCart([]);
      setTable('');
      loadUnpaid();
    } catch {
      toast({ title: 'Errore', description: 'Impossibile registrare l\'ordine', variant: 'destructive' });
    }
  };

  const markPaid = async (order, paymentMethod) => {
    try {
      await axios.patch(`${BACKEND_URL}/api/orders/${order.id}/payment`, { paid: true, payment_method: paymentMethod }, { headers: authHeader });
      loadUnpaid();
    } catch {
      toast({ title: 'Errore', description: 'Impossibile segnare come pagato', variant: 'destructive' });
    }
  };

  if (checking) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-[#4a5d4a]" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <AdminPageHeader title="Cassa" subtitle="Ordini al banco e incassi" />
      <div className="max-w-7xl mx-auto px-4 py-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Product picker */}
        <div className="lg:col-span-2">
          <div className="bg-white rounded-lg shadow p-4 mb-4">
            <div className="relative mb-3">
              <Search className="w-4 h-4 absolute left-3 top-3 text-gray-400" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Cerca prodotto..."
                className="pl-9"
              />
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-h-[420px] overflow-y-auto">
              {filtered.map((p) => (
                <button
                  key={p.id}
                  onClick={() => addToCart(p)}
                  className="text-left border rounded-lg p-2 hover:bg-[#4a5d4a]/10 hover:border-[#4a5d4a] transition-colors"
                >
                  <p className="text-sm font-medium truncate">{p.nameIT || p.name}</p>
                  <p className="text-xs text-gray-500">{p.price}</p>
                </button>
              ))}
              {filtered.length === 0 && (
                <p className="col-span-full text-center text-gray-400 py-6">Nessun prodotto trovato</p>
              )}
            </div>
          </div>

          {/* Unpaid orders */}
          <div className="bg-white rounded-lg shadow p-4">
            <h2 className="font-bold mb-3">Da incassare</h2>
            {loadingUnpaid ? (
              <Loader2 className="w-6 h-6 animate-spin text-[#4a5d4a]" />
            ) : unpaid.length === 0 ? (
              <p className="text-gray-400 text-sm">Nessun ordine da incassare</p>
            ) : (
              <div className="space-y-2">
                {unpaid.map((o) => (
                  <div key={o.id} className="flex items-center justify-between border rounded-lg p-3">
                    <div>
                      <p className="text-sm font-medium">
                        {o.table ? `Tavolo ${o.table}` : o.id}{o.sala_nome ? ` — ${o.sala_nome}` : ''}
                      </p>
                      <p className="text-xs text-gray-500">
                        {o.items.length} prodotti{o.totale_coperto > 0 ? ` + coperto € ${o.totale_coperto.toFixed(2)}` : ''} — € {o.total?.toFixed(2)}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <Button size="sm" variant="outline" onClick={() => markPaid(o, 'contanti')}>
                        <Banknote className="w-4 h-4 mr-1" /> Contanti
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => markPaid(o, 'pos')}>
                        <CreditCard className="w-4 h-4 mr-1" /> POS
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Cart */}
        <div>
          <div className="bg-white rounded-lg shadow p-4 sticky top-6">
            <h2 className="font-bold mb-3">Ordine corrente</h2>
            <Input
              value={table}
              onChange={(e) => setTable(e.target.value)}
              placeholder="Tavolo / banco"
              className="mb-3"
            />
            {sale.length > 0 && (
              <div className="mb-3">
                <Select value={salaId} onValueChange={setSalaId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Sala (opzionale)" />
                  </SelectTrigger>
                  <SelectContent>
                    {sale.filter((s) => s.ordini_abilitati).map((s) => (
                      <SelectItem key={s.id} value={s.id}>{s.nome}{s.coperto_attivo ? ` — coperto € ${Number(s.coperto_importo).toFixed(2)}` : ''}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {salaSelezionata?.coperto_attivo && (
              <div className="mb-3">
                <label className="text-xs text-gray-500">Numero coperti</label>
                <Input
                  type="number"
                  min="1"
                  value={numeroCoperti}
                  onChange={(e) => setNumeroCoperti(e.target.value)}
                />
              </div>
            )}
            {cart.length === 0 ? (
              <p className="text-gray-400 text-sm py-6 text-center">Seleziona prodotti dall'elenco</p>
            ) : (
              <div className="space-y-2 mb-4">
                {cart.map((item) => (
                  <div key={item.product_id} className="flex items-center justify-between text-sm">
                    <span className="flex-1 truncate">{item.name}</span>
                    <div className="flex items-center gap-1">
                      <button onClick={() => updateQty(item.product_id, item.quantity - 1)} className="w-6 h-6 rounded bg-gray-100 flex items-center justify-center">
                        <Minus className="w-3 h-3" />
                      </button>
                      <span className="w-5 text-center">{item.quantity}</span>
                      <button onClick={() => updateQty(item.product_id, item.quantity + 1)} className="w-6 h-6 rounded bg-gray-100 flex items-center justify-center">
                        <Plus className="w-3 h-3" />
                      </button>
                      <button onClick={() => updateQty(item.product_id, 0)} className="w-6 h-6 rounded bg-gray-100 flex items-center justify-center text-red-500 ml-1">
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="border-t pt-3 mb-4">
              {copertoTotal > 0 && (
                <div className="flex justify-between items-center text-sm text-gray-500 mb-1">
                  <span>Coperto ({numeroCoperti}x)</span>
                  <span>€ {copertoTotal.toFixed(2)}</span>
                </div>
              )}
              <div className="flex justify-between items-center font-bold text-lg">
                <span>Totale</span>
                <span className="flex items-center gap-1"><Euro className="w-4 h-4" /> {total.toFixed(2)}</span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Button disabled={cart.length === 0} onClick={() => submitCounterOrder('contanti')} className="bg-[#4a5d4a] hover:bg-[#3d4d3d]">
                <Banknote className="w-4 h-4 mr-1" /> Contanti
              </Button>
              <Button disabled={cart.length === 0} onClick={() => submitCounterOrder('pos')} variant="outline">
                <CreditCard className="w-4 h-4 mr-1" /> POS
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CounterPage;
