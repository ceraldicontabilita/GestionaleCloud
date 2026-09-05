import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { ShoppingCart, Minus, Plus, Trash2, CheckCircle2 } from 'lucide-react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from './ui/sheet';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { useCart } from '../context/CartContext';
import { toast } from '../hooks/use-toast';

const BACKEND_URL = process.env.REACT_APP_MENU_BACKEND_URL;

const CartDrawer = ({ language = 'it' }) => {
  const { items, itemCount, total, updateQuantity, removeItem, submitOrder, submitting } = useCart();
  const [open, setOpen] = useState(false);
  const [table, setTable] = useState('');
  const [customerName, setCustomerName] = useState('');
  const [note, setNote] = useState('');
  const [confirmedOrder, setConfirmedOrder] = useState(null);
  const [sale, setSale] = useState([]);
  const [salaId, setSalaId] = useState('');
  const [numeroCoperti, setNumeroCoperti] = useState('1');
  const [paymentMethod, setPaymentMethod] = useState('contanti');

  const t = (it, en) => (language === 'it' ? it : en);

  useEffect(() => {
    axios.get(`${BACKEND_URL}/api/sale/`)
      .then((res) => setSale((res.data || []).filter((s) => s.ordini_abilitati)))
      .catch(() => {});
  }, []);

  const salaSelezionata = sale.find((s) => s.id === salaId);
  const contantiBloccati = !!salaSelezionata?.disabilita_contanti_qr;

  useEffect(() => {
    // Se la sala selezionata blocca i contanti e stiamo pagando in contanti, passa automaticamente a carta/POS
    if (contantiBloccati && paymentMethod === 'contanti') {
      setPaymentMethod('pos');
    }
  }, [contantiBloccati, paymentMethod]);

  const copertoTotal = salaSelezionata?.coperto_attivo
    ? Math.round((parseFloat(salaSelezionata.coperto_importo) || 0) * (parseInt(numeroCoperti, 10) || 1) * 100) / 100
    : 0;
  const totalWithCoperto = total + copertoTotal;

  const handleSubmit = async () => {
    try {
      const order = await submitOrder({
        table,
        customerName,
        note,
        salaId: salaId || null,
        numeroCoperti: salaSelezionata?.coperto_attivo ? (parseInt(numeroCoperti, 10) || 1) : null,
        paymentMethod
      });
      setConfirmedOrder(order);
      toast({
        title: t('Ordine inviato!', 'Order sent!'),
        description: t('Il tuo ordine è stato ricevuto dal locale.', 'Your order has been received.')
      });
    } catch (err) {
      const serverDetail = err?.response?.data?.detail;
      toast({
        title: t('Errore', 'Error'),
        description: typeof serverDetail === 'string'
          ? serverDetail
          : t('Non è stato possibile inviare l\'ordine. Riprova.', 'Could not send the order. Try again.'),
        variant: 'destructive'
      });
    }
  };

  const closeAndReset = () => {
    setOpen(false);
    setConfirmedOrder(null);
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <button
          className="fixed bottom-6 right-6 z-40 bg-[#d4af37] hover:bg-[#c9a332] text-black rounded-full shadow-lg w-16 h-16 flex items-center justify-center transition-transform hover:scale-105"
          aria-label={t('Carrello', 'Cart')}
        >
          <ShoppingCart className="w-6 h-6" />
          {itemCount > 0 && (
            <span className="absolute -top-1 -right-1 bg-[#4a5d4a] text-white text-xs font-bold rounded-full w-6 h-6 flex items-center justify-center border-2 border-white">
              {itemCount}
            </span>
          )}
        </button>
      </SheetTrigger>
      <SheetContent side="bottom" className="bg-[#4a5d4a] text-white border-t-[#5d7056] max-h-[85vh] overflow-y-auto">
        {confirmedOrder ? (
          <div className="py-10 text-center">
            <CheckCircle2 className="w-16 h-16 text-[#d4af37] mx-auto mb-4" />
            <h2 className="text-2xl font-bold mb-2">{t('Ordine inviato', 'Order sent')}</h2>
            <p className="text-white/80 mb-1">
              {t('Numero ordine', 'Order number')}: <span className="font-mono">{confirmedOrder.id}</span>
            </p>
            <p className="text-white/80 mb-6">
              {t('Totale', 'Total')}: <span className="text-[#d4af37] font-bold">€ {confirmedOrder.total?.toFixed(2)}</span>
            </p>
            <Button onClick={closeAndReset} className="bg-[#d4af37] text-black hover:bg-[#c9a332]">
              {t('Chiudi', 'Close')}
            </Button>
          </div>
        ) : (
          <>
            <SheetHeader>
              <SheetTitle className="text-white text-xl">{t('Il tuo ordine', 'Your order')}</SheetTitle>
            </SheetHeader>

            {items.length === 0 ? (
              <p className="text-white/70 text-center py-10">
                {t('Il carrello è vuoto. Aggiungi qualcosa dal menu!', 'Your cart is empty. Add something from the menu!')}
              </p>
            ) : (
              <div className="mt-4 space-y-3">
                {items.map((item) => (
                  <div key={item.product_id} className="bg-[#3d4d3d] rounded-lg p-3 flex items-center justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <p className="font-medium truncate">{item.name}</p>
                      <p className="text-[#d4af37] text-sm">{item.price}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => updateQuantity(item.product_id, item.quantity - 1)}
                        className="w-8 h-8 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center"
                      >
                        <Minus className="w-4 h-4" />
                      </button>
                      <span className="w-6 text-center">{item.quantity}</span>
                      <button
                        onClick={() => updateQuantity(item.product_id, item.quantity + 1)}
                        className="w-8 h-8 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center"
                      >
                        <Plus className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => removeItem(item.product_id)}
                        className="w-8 h-8 rounded-full bg-white/10 hover:bg-red-500/60 flex items-center justify-center ml-1"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}

                {copertoTotal > 0 && (
                  <div className="flex justify-between items-center text-sm text-white/70">
                    <span>{t('Coperto', 'Cover charge')} ({numeroCoperti}x)</span>
                    <span>€ {copertoTotal.toFixed(2)}</span>
                  </div>
                )}
                <div className="flex justify-between items-center pt-3 border-t border-white/20 text-lg font-bold">
                  <span>{t('Totale', 'Total')}</span>
                  <span className="text-[#d4af37]">€ {totalWithCoperto.toFixed(2)}</span>
                </div>

                <div className="space-y-3 pt-4">
                  <div>
                    <Label htmlFor="table" className="text-white/80">{t('Numero tavolo', 'Table number')}</Label>
                    <Input
                      id="table"
                      value={table}
                      onChange={(e) => setTable(e.target.value)}
                      placeholder={t('es. 5', 'e.g. 5')}
                      className="bg-white text-black mt-1"
                    />
                  </div>
                  {sale.length > 0 && (
                    <div>
                      <Label className="text-white/80">{t('Sala (opzionale)', 'Room (optional)')}</Label>
                      <Select value={salaId} onValueChange={setSalaId}>
                        <SelectTrigger className="bg-white text-black mt-1">
                          <SelectValue placeholder={t('Seleziona sala', 'Select room')} />
                        </SelectTrigger>
                        <SelectContent>
                          {sale.map((s) => (
                            <SelectItem key={s.id} value={s.id}>{s.nome}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  )}
                  {salaSelezionata?.coperto_attivo && (
                    <div>
                      <Label htmlFor="numeroCoperti" className="text-white/80">{t('Numero coperti', 'Number of covers')}</Label>
                      <Input
                        id="numeroCoperti"
                        type="number"
                        min="1"
                        value={numeroCoperti}
                        onChange={(e) => setNumeroCoperti(e.target.value)}
                        className="bg-white text-black mt-1"
                      />
                    </div>
                  )}
                  <div>
                    <Label className="text-white/80">{t('Come vuoi pagare?', 'How would you like to pay?')}</Label>
                    <div className="flex gap-2 mt-1">
                      <button
                        type="button"
                        disabled={contantiBloccati}
                        onClick={() => setPaymentMethod('contanti')}
                        className={`flex-1 rounded-lg py-2 text-sm font-medium border transition-colors ${
                          paymentMethod === 'contanti'
                            ? 'bg-[#d4af37] text-black border-[#d4af37]'
                            : 'bg-white/10 text-white border-white/30'
                        } ${contantiBloccati ? 'opacity-40 cursor-not-allowed' : ''}`}
                      >
                        {t('Contanti', 'Cash')}
                      </button>
                      <button
                        type="button"
                        onClick={() => setPaymentMethod('pos')}
                        className={`flex-1 rounded-lg py-2 text-sm font-medium border transition-colors ${
                          paymentMethod === 'pos'
                            ? 'bg-[#d4af37] text-black border-[#d4af37]'
                            : 'bg-white/10 text-white border-white/30'
                        }`}
                      >
                        {t('Carta / POS', 'Card / POS')}
                      </button>
                    </div>
                    {contantiBloccati && (
                      <p className="text-xs text-white/60 mt-1">
                        {t('Il pagamento in contanti non è disponibile per questa sala.', 'Cash payment is not available for this room.')}
                      </p>
                    )}
                  </div>
                  <div>
                    <Label htmlFor="customerName" className="text-white/80">{t('Nome (opzionale)', 'Name (optional)')}</Label>
                    <Input
                      id="customerName"
                      value={customerName}
                      onChange={(e) => setCustomerName(e.target.value)}
                      className="bg-white text-black mt-1"
                    />
                  </div>
                  <div>
                    <Label htmlFor="note" className="text-white/80">{t('Note (opzionale)', 'Notes (optional)')}</Label>
                    <Textarea
                      id="note"
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      className="bg-white text-black mt-1"
                    />
                  </div>
                </div>

                <Button
                  onClick={handleSubmit}
                  disabled={submitting}
                  className="w-full bg-[#d4af37] text-black hover:bg-[#c9a332] font-semibold mt-2"
                >
                  {submitting ? t('Invio in corso...', 'Sending...') : t('Invia ordine', 'Send order')}
                </Button>
              </div>
            )}
          </>
        )}
      </SheetContent>
    </Sheet>
  );
};

export default CartDrawer;
