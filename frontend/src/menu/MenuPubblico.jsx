/**
 * Menu digitale pubblico di Ceraldi Caffè (QR al tavolo) — rotta /menu.
 *
 * Ex HomePage dell'app Menu: categorie -> sottocategorie -> prodotti, filtro
 * allergeni, lingua IT/EN, carrello con invio dell'ordine dal tavolo (sala,
 * coperto, metodo di pagamento). Nessuna sessione: usa solo
 * /api/menu/pubblico. Il carrello e l'ultimo ordine restano nel telefono
 * del cliente (localStorage).
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle, CheckCircle2, ChevronRight, Cookie, Facebook, Filter, Info, Instagram,
  Loader2, MapPin, Minus, Plus, ShoppingCart, Trash2,
} from 'lucide-react';
import { toast } from 'sonner';
import './menu.css';
import { caricaMenu, caricaSalePubbliche, inviaOrdine, messaggioErrore, prezzoNumero } from './api';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from './ui/sheet';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Checkbox } from './ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';

const CART_KEY = 'ceraldi_cart';
const LAST_ORDER_KEY = 'ceraldi_last_order_id';
const COOKIE_KEY = 'cookieAccepted';

const leggi = (k, fallback) => {
  try {
    const v = localStorage.getItem(k);
    return v ? JSON.parse(v) : fallback;
  } catch {
    return fallback;
  }
};

/* ------------------------------------------------------------------ carrello */
function useCarrello() {
  const [items, setItems] = useState(() => leggi(CART_KEY, []));
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    try { localStorage.setItem(CART_KEY, JSON.stringify(items)); } catch { /* storage assente */ }
  }, [items]);

  const addItem = useCallback((product) => {
    setItems((prev) => {
      const ex = prev.find((i) => i.product_id === product.id);
      if (ex) return prev.map((i) => (i.product_id === product.id ? { ...i, quantity: i.quantity + 1 } : i));
      return [...prev, { product_id: product.id, name: product.nameIT || product.name, price: product.price, quantity: 1, note: '' }];
    });
  }, []);
  const updateQuantity = useCallback((product_id, quantity) => {
    setItems((prev) => (quantity <= 0 ? prev.filter((i) => i.product_id !== product_id) : prev.map((i) => (i.product_id === product_id ? { ...i, quantity } : i))));
  }, []);
  const removeItem = useCallback((product_id) => setItems((prev) => prev.filter((i) => i.product_id !== product_id)), []);

  const itemCount = items.reduce((s, i) => s + i.quantity, 0);
  const total = items.reduce((s, i) => s + prezzoNumero(i.price) * i.quantity, 0);

  const submitOrder = useCallback(async ({ table, customerName, note, salaId, numeroCoperti, paymentMethod }) => {
    setSubmitting(true);
    try {
      const ordine = await inviaOrdine({
        items, table, customer_name: customerName, note, source: 'cliente',
        sala_id: salaId || null, numero_coperti: numeroCoperti || null, payment_method: paymentMethod || null,
      });
      try { localStorage.setItem(LAST_ORDER_KEY, ordine.id); } catch { /* ignora */ }
      setItems([]);
      return ordine;
    } finally {
      setSubmitting(false);
    }
  }, [items]);

  return { items, itemCount, total, addItem, updateQuantity, removeItem, submitOrder, submitting };
}

/* ------------------------------------------------------------------ componenti */
const CookieBanner = ({ onAccept, onDecline }) => (
  <div className="fixed top-0 left-0 right-0 z-50 bg-[#3d4d3d] text-white py-3 px-4 shadow-lg">
    <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <Cookie className="w-6 h-6 text-[#d4af37] flex-shrink-0" />
        <p className="text-sm">Usiamo solo i cookie necessari al funzionamento del sito. / We use only the cookies necessary for the website to work.</p>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <button onClick={onDecline} className="px-4 py-1.5 rounded-md bg-transparent border border-white text-white hover:bg-white/10 transition-colors text-sm">No</button>
        <button onClick={onAccept} className="px-4 py-1.5 rounded-md bg-[#d4af37] text-black font-medium hover:bg-[#c9a332] transition-colors text-sm">Ok</button>
      </div>
    </div>
  </div>
);

const SubcategoryModal = ({ isOpen, onClose, category, language, onSelectSubcategory }) => {
  if (!category) return null;
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="bg-[#4a5d4a] text-white border-[#5d7056] max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-2xl font-bold text-white">{language === 'it' ? category.nameIT : category.name}</DialogTitle>
        </DialogHeader>
        <div className="mt-6 space-y-3">
          {(category.subcategories || []).map((sub) => (
            <div key={sub.id} onClick={() => onSelectSubcategory(sub)} className="bg-[#3d4d3d] rounded-lg overflow-hidden hover:bg-[#354535] transition-all cursor-pointer group">
              <div className="flex items-center">
                {sub.image && (
                  <div className="w-24 h-24 flex-shrink-0">
                    <img src={sub.image} alt={language === 'it' ? sub.nameIT : sub.name} className="w-full h-full object-cover" />
                  </div>
                )}
                <div className="flex-1 p-4 flex items-center justify-between">
                  <div>
                    <h3 className="font-semibold text-lg">{language === 'it' ? sub.nameIT : sub.name}</h3>
                    <p className="text-sm text-white/60 mt-1">{(sub.items || []).length} {language === 'it' ? 'prodotti' : 'products'}</p>
                  </div>
                  <ChevronRight className="w-6 h-6 text-[#d4af37] group-hover:translate-x-1 transition-transform" />
                </div>
              </div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
};

const MenuModal = ({ isOpen, onClose, category, language, selectedAllergens, allergensList, onAdd }) => {
  if (!category) return null;
  const filteredItems = (category.items || []).filter((item) => (
    selectedAllergens.length === 0 || !(item.allergens || []).some((a) => selectedAllergens.includes(a))
  ));
  const info = (id) => allergensList.find((a) => a.id === id);
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="bg-[#4a5d4a] text-white border-[#5d7056] max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-2xl font-bold text-white">{language === 'it' ? category.nameIT : category.name}</DialogTitle>
        </DialogHeader>
        <div className="mt-6">
          {filteredItems.length === 0 ? (
            <div className="text-center py-12 text-white/70">
              <AlertCircle className="w-12 h-12 mx-auto mb-3 text-[#d4af37]" />
              <p className="text-lg font-medium mb-2">{language === 'it' ? 'Nessun prodotto disponibile' : 'No products available'}</p>
              <p className="text-sm">{language === 'it' ? 'Tutti i prodotti in questa categoria contengono allergeni filtrati.' : 'All products in this category contain filtered allergens.'}</p>
            </div>
          ) : (
            <div className="space-y-4">
              {filteredItems.map((item) => (
                <div key={item.id} className="bg-[#3d4d3d] rounded-lg overflow-hidden hover:bg-[#354535] transition-colors">
                  {item.image && (
                    <div className="w-full h-48 overflow-hidden">
                      <img src={item.image} alt={language === 'it' ? item.nameIT : item.name} className="w-full h-full object-cover" />
                    </div>
                  )}
                  <div className="p-4">
                    <div className="flex justify-between items-start mb-2">
                      <div className="flex-1">
                        <h3 className="font-semibold text-lg">{language === 'it' ? item.nameIT : item.name}</h3>
                        {(item.description || item.descriptionIT) && (
                          <p className="text-sm text-white/70 mt-1">{language === 'it' ? item.descriptionIT || item.description : item.description || item.descriptionIT}</p>
                        )}
                      </div>
                      <span className="text-[#d4af37] font-bold text-lg ml-4">{item.price}</span>
                    </div>
                    <button onClick={() => onAdd(item)} className="mt-3 w-full flex items-center justify-center gap-2 bg-[#d4af37] hover:bg-[#c9a332] text-black font-semibold rounded-lg py-2 transition-colors">
                      <Plus className="w-4 h-4" />
                      {language === 'it' ? 'Aggiungi al carrello' : 'Add to cart'}
                    </button>
                    {(item.allergens || []).length > 0 && (
                      <div className="mt-3 pt-3 border-t border-white/10">
                        <p className="text-xs text-white/60 mb-2">{language === 'it' ? 'Contiene allergeni:' : 'Contains allergens:'}</p>
                        <div className="flex flex-wrap gap-2">
                          {item.allergens.map((id) => {
                            const a = info(id);
                            return a ? (
                              <span key={id} className="inline-flex items-center gap-1 bg-[#d4af37]/20 text-[#d4af37] px-2 py-1 rounded-full text-xs font-medium">
                                {a.icon} {language === 'it' ? a.nameIT : a.name}
                              </span>
                            ) : null;
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

const AllergensModal = ({ isOpen, onClose, selectedAllergens, onApply, language, allergensList }) => {
  const [tempSelected, setTempSelected] = useState(selectedAllergens);
  useEffect(() => { if (isOpen) setTempSelected(selectedAllergens); }, [isOpen, selectedAllergens]);
  const toggle = (id) => setTempSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="bg-[#4a5d4a] text-white border-[#5d7056] max-w-md max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-2xl font-bold text-white">{language === 'it' ? 'Filtro Allergeni' : 'Allergens Filter'}</DialogTitle>
        </DialogHeader>
        <div className="mt-6 space-y-4">
          <div className="bg-[#3d4d3d] rounded-lg p-3 flex items-start gap-2">
            <Info className="w-5 h-5 text-[#d4af37] flex-shrink-0 mt-0.5" />
            <p className="text-xs text-white/80">
              {language === 'it'
                ? 'Seleziona gli allergeni che vuoi escludere dal menu. I prodotti che li contengono non saranno mostrati.'
                : 'Select allergens to exclude from the menu. Products containing them will not be shown.'}
            </p>
          </div>
          <div className="flex justify-between items-center pt-2">
            <p className="text-sm font-medium text-white/90">{language === 'it' ? 'Allergeni disponibili:' : 'Available allergens:'}</p>
            {tempSelected.length > 0 && (
              <button onClick={() => setTempSelected([])} className="text-xs text-[#d4af37] hover:text-[#c9a332] transition-colors">
                {language === 'it' ? 'Deseleziona tutto' : 'Clear all'}
              </button>
            )}
          </div>
          <div className="space-y-3 max-h-[300px] overflow-y-auto pr-2">
            {allergensList.map((a) => (
              <div key={a.id} className="flex items-center space-x-3 bg-[#3d4d3d] rounded-lg p-3 hover:bg-[#354535] transition-colors">
                <Checkbox id={`all-${a.id}`} checked={tempSelected.includes(a.id)} onCheckedChange={() => toggle(a.id)} className="border-white data-[state=checked]:bg-[#d4af37] data-[state=checked]:border-[#d4af37]" />
                <label htmlFor={`all-${a.id}`} className="flex items-center gap-2 flex-1 text-sm font-medium leading-none cursor-pointer">
                  <span className="text-lg">{a.icon}</span>
                  <span>{language === 'it' ? a.nameIT : a.name}</span>
                </label>
              </div>
            ))}
          </div>
          <div className="flex gap-3 mt-6 pt-4 border-t border-white/10">
            <Button onClick={onClose} variant="outline" className="flex-1 bg-transparent border-white text-white hover:bg-white/10">
              {language === 'it' ? 'Annulla' : 'Cancel'}
            </Button>
            <Button onClick={() => { onApply(tempSelected); onClose(); }} className="flex-1 bg-[#d4af37] text-black hover:bg-[#c9a332] font-semibold">
              {language === 'it' ? 'Applica' : 'Apply'}{tempSelected.length > 0 && ` (${tempSelected.length})`}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

const CartDrawer = ({ language, carrello }) => {
  const { items, itemCount, total, updateQuantity, removeItem, submitOrder, submitting } = carrello;
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
    caricaSalePubbliche().then((s) => setSale((s || []).filter((x) => x.ordini_abilitati))).catch(() => {});
  }, []);

  const salaSelezionata = sale.find((s) => s.id === salaId);
  const contantiBloccati = !!salaSelezionata?.disabilita_contanti_qr;
  useEffect(() => { if (contantiBloccati && paymentMethod === 'contanti') setPaymentMethod('pos'); }, [contantiBloccati, paymentMethod]);
  const copertoTotal = salaSelezionata?.coperto_attivo
    ? Math.round((parseFloat(salaSelezionata.coperto_importo) || 0) * (parseInt(numeroCoperti, 10) || 1) * 100) / 100
    : 0;
  const totalWithCoperto = total + copertoTotal;

  const handleSubmit = async () => {
    try {
      const order = await submitOrder({
        table, customerName, note, salaId: salaId || null,
        numeroCoperti: salaSelezionata?.coperto_attivo ? (parseInt(numeroCoperti, 10) || 1) : null,
        paymentMethod,
      });
      setConfirmedOrder(order);
      toast.success(t('Ordine inviato!', 'Order sent!'), { description: t('Il tuo ordine è stato ricevuto dal locale.', 'Your order has been received.') });
    } catch (err) {
      toast.error(t('Errore', 'Error'), { description: messaggioErrore(err, t("Non è stato possibile inviare l'ordine. Riprova.", 'Could not send the order. Try again.')) });
    }
  };

  const pillola = (attivo, disabled) =>
    `flex-1 rounded-lg py-2 text-sm font-medium border transition-colors ${attivo ? 'bg-[#d4af37] text-black border-[#d4af37]' : 'bg-white/10 text-white border-white/30'} ${disabled ? 'opacity-40 cursor-not-allowed' : ''}`;

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <button className="fixed bottom-6 right-6 z-40 bg-[#d4af37] hover:bg-[#c9a332] text-black rounded-full shadow-lg w-16 h-16 flex items-center justify-center transition-transform hover:scale-105" aria-label={t('Carrello', 'Cart')}>
          <ShoppingCart className="w-6 h-6" />
          {itemCount > 0 && (
            <span className="absolute -top-1 -right-1 bg-[#4a5d4a] text-white text-xs font-bold rounded-full w-6 h-6 flex items-center justify-center border-2 border-white">{itemCount}</span>
          )}
        </button>
      </SheetTrigger>
      <SheetContent side="bottom" className="bg-[#4a5d4a] text-white border-t-[#5d7056] max-h-[85vh] overflow-y-auto">
        {confirmedOrder ? (
          <div className="py-10 text-center">
            <CheckCircle2 className="w-16 h-16 text-[#d4af37] mx-auto mb-4" />
            <h2 className="text-2xl font-bold mb-2">{t('Ordine inviato', 'Order sent')}</h2>
            <p className="text-white/80 mb-1">{t('Numero ordine', 'Order number')}: <span className="font-mono">{confirmedOrder.id}</span></p>
            <p className="text-white/80 mb-6">{t('Totale', 'Total')}: <span className="text-[#d4af37] font-bold">€ {Number(confirmedOrder.total || 0).toFixed(2)}</span></p>
            <Button onClick={() => { setOpen(false); setConfirmedOrder(null); }} className="bg-[#d4af37] text-black hover:bg-[#c9a332]">{t('Chiudi', 'Close')}</Button>
          </div>
        ) : (
          <>
            <SheetHeader><SheetTitle className="text-white text-xl">{t('Il tuo ordine', 'Your order')}</SheetTitle></SheetHeader>
            {items.length === 0 ? (
              <p className="text-white/70 text-center py-10">{t('Il carrello è vuoto. Aggiungi qualcosa dal menu!', 'Your cart is empty. Add something from the menu!')}</p>
            ) : (
              <div className="mt-4 space-y-3">
                {items.map((item) => (
                  <div key={item.product_id} className="bg-[#3d4d3d] rounded-lg p-3 flex items-center justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <p className="font-medium truncate">{item.name}</p>
                      <p className="text-[#d4af37] text-sm">{item.price}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={() => updateQuantity(item.product_id, item.quantity - 1)} className="w-8 h-8 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center"><Minus className="w-4 h-4" /></button>
                      <span className="w-6 text-center">{item.quantity}</span>
                      <button onClick={() => updateQuantity(item.product_id, item.quantity + 1)} className="w-8 h-8 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center"><Plus className="w-4 h-4" /></button>
                      <button onClick={() => removeItem(item.product_id)} className="w-8 h-8 rounded-full bg-white/10 hover:bg-[#d35f4e]/60 flex items-center justify-center ml-1"><Trash2 className="w-4 h-4" /></button>
                    </div>
                  </div>
                ))}
                {copertoTotal > 0 && (
                  <div className="flex justify-between items-center text-sm text-white/70">
                    <span>{t('Coperto', 'Cover charge')} ({numeroCoperti}x)</span><span>€ {copertoTotal.toFixed(2)}</span>
                  </div>
                )}
                <div className="flex justify-between items-center pt-3 border-t border-white/20 text-lg font-bold">
                  <span>{t('Totale', 'Total')}</span><span className="text-[#d4af37]">€ {totalWithCoperto.toFixed(2)}</span>
                </div>
                <div className="space-y-3 pt-4">
                  <div>
                    <Label htmlFor="table" className="text-white/80">{t('Numero tavolo', 'Table number')}</Label>
                    <Input id="table" value={table} onChange={(e) => setTable(e.target.value)} placeholder={t('es. 5', 'e.g. 5')} className="bg-white text-black mt-1" />
                  </div>
                  {sale.length > 0 && (
                    <div>
                      <Label className="text-white/80">{t('Sala (opzionale)', 'Room (optional)')}</Label>
                      <Select value={salaId} onValueChange={setSalaId}>
                        <SelectTrigger className="bg-white text-black mt-1"><SelectValue placeholder={t('Seleziona sala', 'Select room')} /></SelectTrigger>
                        <SelectContent>{sale.map((s) => <SelectItem key={s.id} value={s.id}>{s.nome}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                  )}
                  {salaSelezionata?.coperto_attivo && (
                    <div>
                      <Label htmlFor="numeroCoperti" className="text-white/80">{t('Numero coperti', 'Number of covers')}</Label>
                      <Input id="numeroCoperti" type="number" min="1" value={numeroCoperti} onChange={(e) => setNumeroCoperti(e.target.value)} className="bg-white text-black mt-1" />
                    </div>
                  )}
                  <div>
                    <Label className="text-white/80">{t('Come vuoi pagare?', 'How would you like to pay?')}</Label>
                    <div className="flex gap-2 mt-1">
                      <button type="button" disabled={contantiBloccati} onClick={() => setPaymentMethod('contanti')} className={pillola(paymentMethod === 'contanti', contantiBloccati)}>{t('Contanti', 'Cash')}</button>
                      <button type="button" onClick={() => setPaymentMethod('pos')} className={pillola(paymentMethod === 'pos', false)}>{t('Carta / POS', 'Card / POS')}</button>
                    </div>
                    {contantiBloccati && <p className="text-xs text-white/60 mt-1">{t('Il pagamento in contanti non è disponibile per questa sala.', 'Cash payment is not available for this room.')}</p>}
                  </div>
                  <div>
                    <Label htmlFor="customerName" className="text-white/80">{t('Nome (opzionale)', 'Name (optional)')}</Label>
                    <Input id="customerName" value={customerName} onChange={(e) => setCustomerName(e.target.value)} className="bg-white text-black mt-1" />
                  </div>
                  <div>
                    <Label htmlFor="note" className="text-white/80">{t('Note (opzionale)', 'Notes (optional)')}</Label>
                    <Textarea id="note" value={note} onChange={(e) => setNote(e.target.value)} className="bg-white text-black mt-1" />
                  </div>
                </div>
                <Button onClick={handleSubmit} disabled={submitting} className="w-full bg-[#d4af37] text-black hover:bg-[#c9a332] font-semibold mt-2">
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

/* ------------------------------------------------------------------ pagina */
export default function MenuPubblico() {
  const [menuCategories, setMenuCategories] = useState([]);
  const [allergensList, setAllergensList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCookieBanner, setShowCookieBanner] = useState(() => !leggi(COOKIE_KEY, false));
  const [language, setLanguage] = useState('it');
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [selectedSubcategory, setSelectedSubcategory] = useState(null);
  const [showSubcategoryModal, setShowSubcategoryModal] = useState(false);
  const [showMenuModal, setShowMenuModal] = useState(false);
  const [showAllergensModal, setShowAllergensModal] = useState(false);
  const [selectedAllergens, setSelectedAllergens] = useState([]);
  const carrello = useCarrello();

  useEffect(() => {
    document.title = 'Ceraldi Caffè — Menu';
    let attivo = true;
    caricaMenu()
      .then((d) => { if (attivo) { setMenuCategories(d.categories || []); setAllergensList(d.allergens || []); } })
      .catch(() => { if (attivo) setError(true); })
      .finally(() => { if (attivo) setLoading(false); });
    return () => { attivo = false; };
  }, []);

  const t = useMemo(() => (it, en) => (language === 'it' ? it : en), [language]);
  const aggiungi = (item) => {
    carrello.addItem(item);
    toast.success(t('Aggiunto al carrello', 'Added to cart'), { description: language === 'it' ? item.nameIT : item.name });
  };

  return (
    <div className="menu-root min-h-screen bg-[#4a5d4a]">
      {showCookieBanner && (
        <CookieBanner
          onAccept={() => { try { localStorage.setItem(COOKIE_KEY, 'true'); } catch { /* ignora */ } setShowCookieBanner(false); }}
          onDecline={() => setShowCookieBanner(false)}
        />
      )}
      <div className={showCookieBanner ? 'pt-16' : ''}>
        <div className="relative w-full h-48 overflow-hidden">
          <img src="/menu/banner.jpg" alt="Ceraldi Caffè" className="w-full h-full object-cover" />
        </div>
        <div className="max-w-4xl mx-auto px-4 py-8">
          <div className="flex justify-center mb-6">
            <div className="w-24 h-24 rounded-full overflow-hidden border-4 border-white shadow-lg">
              <img src="/menu/logo.jpg" alt="Logo" className="w-full h-full object-cover" />
            </div>
          </div>
          <div className="text-center mb-6">
            <h1 className="text-3xl font-bold text-white mb-3">Ceraldi Caffè</h1>
            <p className="text-white/90 text-sm mb-2">
              {t("Artigiani per passione dal 1973. Dalla colazione all'aperitivo nel cuore di Napoli. #ceraldicaffe #ceraldipassion",
                'Artisans with passion since 1973. From breakfast to aperitif in the heart of Naples. #ceraldicaffe #ceraldipassion')}
            </p>
            <a href="https://maps.google.com/?q=Piazza+Carità,+14,+80134+Napoli+NA,+Italia" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 text-white/80 hover:text-white transition-colors text-sm">
              <MapPin className="w-4 h-4" /> Piazza Carità 14, Napoli (NA)
            </a>
          </div>

          <div className="mb-8">
            <button onClick={() => setShowAllergensModal(true)} className="w-full bg-[#3d4d3d] text-white rounded-lg py-3 px-4 flex items-center justify-between hover:bg-[#354535] transition-colors">
              <span>{t('Filtro Allergeni', 'Allergens filter')}</span>
              <div className="flex items-center gap-2">
                {selectedAllergens.length > 0 && <span className="bg-[#d4af37] text-black text-xs px-2 py-1 rounded-full font-medium">{selectedAllergens.length}</span>}
                <Filter className="w-5 h-5 text-[#d4af37]" />
              </div>
            </button>
          </div>

          {loading && (
            <div className="flex flex-col items-center justify-center py-12">
              <Loader2 className="w-8 h-8 text-[#d4af37] animate-spin mb-4" />
              <p className="text-white/80">{t('Caricamento menu...', 'Loading menu...')}</p>
            </div>
          )}
          {error && !loading && (
            <div className="text-center py-12">
              <p className="text-white/80 mb-4">{t('Errore nel caricamento del menu', 'Error loading menu')}</p>
              <button onClick={() => window.location.reload()} className="bg-[#d4af37] text-black rounded-lg px-4 py-2 font-medium">{t('Riprova', 'Retry')}</button>
            </div>
          )}
          {!loading && !error && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
              {menuCategories.map((category) => (
                <div key={category.id} onClick={() => { setSelectedCategory(category); setShowSubcategoryModal(true); }} className="relative h-48 rounded-lg overflow-hidden cursor-pointer group transform transition-transform hover:scale-105 bg-[#3d4d3d]" data-testid={`category-${category.id}`}>
                  {category.image && <img src={category.image} alt={category.name} className="w-full h-full object-cover" />}
                  <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent" />
                  <div className="absolute bottom-0 left-0 right-0 p-4">
                    <div className="bg-[#d4af37]/90 rounded-lg py-2 px-4 text-center group-hover:bg-[#d4af37] transition-colors">
                      <h3 className="font-semibold text-black">{language === 'it' ? category.nameIT : category.name}</h3>
                    </div>
                  </div>
                </div>
              ))}
              {menuCategories.length === 0 && <p className="text-white/70 text-center col-span-full py-8">{t('Il menu non è ancora stato pubblicato.', 'The menu has not been published yet.')}</p>}
            </div>
          )}

          <div className="mb-6">
            <button onClick={() => setLanguage((p) => (p === 'en' ? 'it' : 'en'))} className="w-full bg-[#3d4d3d] text-white rounded-lg py-3 px-4 flex items-center justify-between hover:bg-[#354535] transition-colors">
              <span>{t('Cambia Lingua', 'Change Language')}</span>
              <span className="text-sm">{language === 'it' ? 'IT → EN' : 'EN → IT'}</span>
            </button>
          </div>
          <div className="flex justify-center gap-4 mb-8">
            <a href="#" aria-label="Facebook" className="w-12 h-12 rounded-full bg-[#d4af37] flex items-center justify-center hover:bg-[#c9a332] transition-colors"><Facebook className="w-6 h-6 text-black" /></a>
            <a href="#" aria-label="Instagram" className="w-12 h-12 rounded-full bg-[#d4af37] flex items-center justify-center hover:bg-[#c9a332] transition-colors"><Instagram className="w-6 h-6 text-black" /></a>
          </div>
          <div className="text-center space-y-3 pb-8">
            <div className="flex justify-center gap-6 text-sm">
              <a href="/privacy" className="text-white/70 hover:text-white transition-colors">{t('Informativa sulla Privacy', 'Privacy Policy')}</a>
            </div>
          </div>
        </div>
      </div>

      <SubcategoryModal isOpen={showSubcategoryModal} onClose={() => setShowSubcategoryModal(false)} category={selectedCategory} language={language}
        onSelectSubcategory={(sub) => { setSelectedSubcategory(sub); setShowSubcategoryModal(false); setShowMenuModal(true); }} />
      <MenuModal isOpen={showMenuModal} onClose={() => setShowMenuModal(false)} category={selectedSubcategory} language={language} selectedAllergens={selectedAllergens} allergensList={allergensList} onAdd={aggiungi} />
      <AllergensModal isOpen={showAllergensModal} onClose={() => setShowAllergensModal(false)} selectedAllergens={selectedAllergens} onApply={setSelectedAllergens} language={language} allergensList={allergensList} />
      <CartDrawer language={language} carrello={carrello} />
    </div>
  );
}
