import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { toast } from '../../hooks/use-toast';
import { Edit, Save, X, Search, ExternalLink } from 'lucide-react';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_MENU_BACKEND_URL;

const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem('admin_token')}` });

// Prodotti e allergeni vengono dal database (Supabase) e si salvano li'.
// Prima questa pagina leggeva mockData.js e il «Salva» scriveva solo nella
// console del browser: le modifiche non arrivavano mai al menu.
const ProductManager = () => {
  const [products, setProducts] = useState([]);
  const [allergensList, setAllergensList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [soloDoppioni, setSoloDoppioni] = useState(false);
  const [mostraNascosti, setMostraNascosti] = useState(false);
  const [visibilitaInCorso, setVisibilitaInCorso] = useState(null);

  const loadProducts = useCallback(async () => {
    setLoading(true);
    try {
      const [prodRes, allRes] = await Promise.all([
        axios.get(`${BACKEND_URL}/api/menu/admin/products/all`, { headers: authHeaders() }),
        axios.get(`${BACKEND_URL}/api/menu/allergens`),
      ]);
      setProducts(prodRes.data.products || []);
      setAllergensList(allRes.data || []);
    } catch (error) {
      toast({
        title: 'Errore',
        description: error.response?.data?.detail || 'Impossibile caricare i prodotti',
        variant: 'destructive'
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadProducts(); }, [loadProducts]);

  const nomeConfronto = p => (p.nameIT || p.name || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim().replace(/\s+/g, ' ');
  const nomi = products.filter(p => p.visible !== false).reduce((m, p) => {
    const nome = nomeConfronto(p); if (nome) m[nome] = (m[nome] || 0) + 1; return m;
  }, {});
  const cambiaVisibilita = async product => {
    const visible = product.visible === false;
    if (!window.confirm(`${visible ? 'Ripristinare' : 'Nascondere'} «${product.nameIT}» nel Menu pubblico? La ricetta e la tracciabilità non vengono cancellate.`)) return;
    setVisibilitaInCorso(product.id);
    try {
      const { data } = await axios.put(`${BACKEND_URL}/api/menu/admin/products/${product.id}/visibilita`, { visible }, { headers: authHeaders() });
      if (!data.success || (data.menu_sync && !['pubblicato', 'aggiornato'].includes(data.menu_sync.esito))) throw new Error('Scelta salvata in Lotti, ma Menu non aggiornato: riprova.');
      setProducts(p => p.map(r => r.id === product.id ? { ...r, visible } : r));
      toast({ title: visible ? 'Prodotto ripristinato' : 'Prodotto nascosto', description: 'Scelta salvata: nessuna ricetta eliminata.' });
    } catch (e) {
      toast({ title: 'Visibilità non aggiornata', description: e.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setVisibilitaInCorso(null); }
  };
  const filteredProducts = products.filter(product => {
    const search = searchTerm.toLowerCase();
    return (mostraNascosti || product.visible !== false) && (!soloDoppioni || nomi[nomeConfronto(product)] > 1) && (
      (product.nameIT || '').toLowerCase().includes(search) ||
      (product.name || '').toLowerCase().includes(search) ||
      (product.codice_prodotto || '').toLowerCase().includes(search) ||
      (product.price || '').toLowerCase().includes(search)
    );
  }).sort((a, b) => nomeConfronto(a).localeCompare(nomeConfronto(b), 'it'));

  const handleEdit = (product) => {
    if (product?.origine === 'lotti') {
      const ref = String(product.lotti_ref || '');
      window.location.assign(`/lotti/#ricette${ref.startsWith('ricetta:') ? '/' + encodeURIComponent(ref.slice(8)) : ''}`);
      return;
    }
    setEditingProduct({ ...product });
  };

  const daLotti = (product) => product?.origine === 'lotti';

  const handleSave = async () => {
    if (!editingProduct || daLotti(editingProduct)) return;
    setSaving(true);
    try {
      const { id, name, nameIT, price, description, descriptionIT, allergens, image, visible } = editingProduct;
      await axios.put(
        `${BACKEND_URL}/api/menu/admin/products/${id}`,
        { name, nameIT, price, description, descriptionIT, allergens: allergens || [], image, visible },
        { headers: authHeaders() }
      );
      toast({ title: 'Salvato', description: `${nameIT} aggiornato nel menu` });
      setEditingProduct(null);
      loadProducts();
    } catch (error) {
      toast({
        title: 'Non salvato',
        description: error.response?.data?.detail || 'Salvataggio non riuscito',
        variant: 'destructive'
      });
    } finally {
      setSaving(false);
    }
  };

  const toggleAllergen = (allergenId) => {
    if (!editingProduct) return;
    
    const allergens = editingProduct.allergens || [];
    const index = allergens.indexOf(allergenId);
    
    if (index > -1) {
      setEditingProduct({
        ...editingProduct,
        allergens: allergens.filter(a => a !== allergenId)
      });
    } else {
      setEditingProduct({
        ...editingProduct,
        allergens: [...allergens, allergenId]
      });
    }
  };

  return (
    <div className="space-y-6">
      {/* Search Bar */}
      <Card>
        <CardContent className="pt-6">
          <div className="relative">
            <Search className="absolute left-3 top-3 h-4 w-4 text-gray-400" />
            <Input
              placeholder="Cerca prodotto per nome o prezzo..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>
          <div className="flex flex-wrap gap-4 mt-3">
            <label className="flex items-center gap-2 min-h-[44px]"><input type="checkbox" checked={soloDoppioni} onChange={e => setSoloDoppioni(e.target.checked)} />Possibili doppioni (stesso nome)</label>
            <label className="flex items-center gap-2 min-h-[44px]"><input type="checkbox" checked={mostraNascosti} onChange={e => setMostraNascosti(e.target.checked)} />Mostra anche nascosti</label>
          </div>
          <p className="text-sm mt-2 text-gray-600">Confronta foto, prezzo e provenienza prima di usare la X. Il nome uguale non prova che porzioni o varianti siano identiche. La X nasconde dal Menu, non elimina la ricetta; puoi ripristinare la voce.</p>
        </CardContent>
      </Card>

      {/* Products List */}
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center justify-between gap-4">
            <span>Tutti i Prodotti ({loading ? '…' : filteredProducts.length})</span>
          </CardTitle>
          <p className="text-sm text-gray-600">
            Il menu è questo: prezzi, allergeni e visibilità si modificano qui. Le ricette di Lotti restano gestite in Lotti.
          </p>
        </CardHeader>
        <CardContent>
          <div className="space-y-2 max-h-[600px] overflow-y-auto">
            {filteredProducts.map((product) => (
              <div
                key={product.id}
                className="flex items-center justify-between p-4 border rounded-lg hover:bg-gray-50 transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-start gap-4 min-w-0">
                    {product.image && (
                      <img
                        src={product.image}
                        alt={product.nameIT}
                        className="w-16 h-16 object-cover rounded"
                      />
                    )}
                    <div className="flex-1 min-w-0 break-words">
                      <h4 className="font-semibold text-gray-900">{product.nameIT}</h4>
                      {product.codice_prodotto && (
                        <p className="text-xs font-bold tracking-wide text-gray-500 tabular-nums" data-testid="codice-prodotto">{product.codice_prodotto}</p>
                      )}
                      {daLotti(product) && (
                        <p className="text-xs text-gray-600" data-testid="vendita-prodotto">
                          {[product.vendita_sala === false ? 'Non in sala' : 'Sala', product.vendita_delivery === false ? 'non in delivery' : 'delivery',
                            product.disponibile === false ? 'ESAURITO' : null,
                            (product.aggiunte || []).length ? `${product.aggiunte.length} aggiunte` : null,
                            (product.rimozioni || []).length ? `${product.rimozioni.length} da togliere` : null].filter(Boolean).join(' · ')}
                        </p>
                      )}
                      <p className="text-xs text-gray-600">
                        {product.visible === false ? 'Nascosto ai clienti'
                          : product.pubblicabile === false ? (daLotti(product) ? 'Nella carta: Prezzo da definire' : 'Nascosto: prezzo da completare') : 'Visibile ai clienti'}
                        {daLotti(product) ? ' · Gestito in Lotti' : ''}
                      </p>
                      <p className="text-sm text-gray-500">{product.name}</p>
                      <div className="flex flex-wrap items-center gap-2 mt-1">
                        <span className="text-sm font-medium text-[#d4af37]">{product.price}</span>
                        <span className="text-xs text-gray-400">
                          {product.categoryName} → {product.subcategoryName}
                        </span>
                      </div>
                      {product.allergens && product.allergens.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {product.allergens.map(allergenId => {
                            const allergen = allergensList.find(a => a.id === allergenId);
                            return allergen ? (
                              <span
                                key={allergenId}
                                className="text-xs bg-orange-100 text-orange-800 px-2 py-0.5 rounded"
                              >
                                {allergen.icon} {allergen.nameIT}
                              </span>
                            ) : null;
                          })}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
                {!daLotti(product) && <Button size="sm" variant="outline" disabled={visibilitaInCorso !== null}
                  aria-label={`${product.visible === false ? 'Ripristina' : 'Nascondi'} ${product.nameIT}`}
                  onClick={() => cambiaVisibilita(product)} className="min-w-[44px] min-h-[44px] ml-2">
                  {product.visible === false ? 'Ripristina' : <X className="w-4 h-4" />}
                </Button>}
                <Button
                  size="sm"
                  variant="outline"
                  aria-label={`Modifica ${product.nameIT}`}
                  onClick={() => handleEdit(product)}
                >
                  {daLotti(product) ? <><ExternalLink className="w-4 h-4 mr-1" /> Ricetta</> : <Edit className="w-4 h-4" />}
                </Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Edit Dialog */}
      <Dialog open={!!editingProduct} onOpenChange={() => setEditingProduct(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Modifica Prodotto</DialogTitle>
          </DialogHeader>
          {editingProduct && (
            <div className="space-y-4 mt-4">
              <fieldset disabled={saving || daLotti(editingProduct)} className="space-y-4 min-w-0">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="prodotto-nome-it">Nome Italiano</Label>
                  <Input
                    id="prodotto-nome-it"
                    value={editingProduct.nameIT}
                    onChange={(e) => setEditingProduct({...editingProduct, nameIT: e.target.value})}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="prodotto-nome-en">Nome Inglese</Label>
                  <Input
                    id="prodotto-nome-en"
                    value={editingProduct.name}
                    onChange={(e) => setEditingProduct({...editingProduct, name: e.target.value})}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="prodotto-prezzo">Prezzo</Label>
                <Input
                    id="prodotto-prezzo"
                  value={editingProduct.price}
                  onChange={(e) => setEditingProduct({...editingProduct, price: e.target.value})}
                />
                <p className="text-xs text-gray-600">Un prodotto senza un prezzo positivo al centesimo resta nascosto ai clienti.</p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="prodotto-visibile">Pubblicazione nel menu clienti</Label>
                <button id="prodotto-visibile" type="button" role="switch"
                  aria-checked={editingProduct.visible !== false}
                  onClick={() => setEditingProduct({ ...editingProduct, visible: editingProduct.visible === false })}
                  className="flex items-center gap-2 min-h-[44px] rounded-lg border px-4 text-sm font-medium">
                  {editingProduct.visible === false ? 'Nascosto ai clienti' : 'Visibile ai clienti'}
                </button>
              </div>

              <div className="space-y-2">
                <Label htmlFor="prodotto-descrizione-it">Descrizione Italiana</Label>
                <Textarea
                  id="prodotto-descrizione-it"
                  value={editingProduct.descriptionIT || ''}
                  onChange={(e) => setEditingProduct({...editingProduct, descriptionIT: e.target.value})}
                  rows={2}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="prodotto-descrizione-en">Descrizione Inglese</Label>
                <Textarea
                  id="prodotto-descrizione-en"
                  value={editingProduct.description || ''}
                  onChange={(e) => setEditingProduct({...editingProduct, description: e.target.value})}
                  rows={2}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="prodotto-immagine">URL Immagine</Label>
                <Input
                  id="prodotto-immagine"
                  value={editingProduct.image || ''}
                  onChange={(e) => setEditingProduct({...editingProduct, image: e.target.value})}
                  placeholder="/uploads/nome-immagine.jpg"
                />
              </div>

              <div className="space-y-2">
                <Label>Allergeni</Label>
                <div className="flex flex-wrap gap-2 p-4 border rounded-lg">
                  {allergensList.map(allergen => (
                    <button
                      key={allergen.id}
                      onClick={() => toggleAllergen(allergen.id)}
                      className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                        editingProduct.allergens?.includes(allergen.id)
                          ? 'bg-[#d4af37] text-black'
                          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >
                      {allergen.icon} {allergen.nameIT}
                    </button>
                  ))}
                </div>
              </div>
              </fieldset>

              {daLotti(editingProduct) && (
                <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                  <p className="text-sm text-yellow-800">
                    Questo prodotto viene da una ricetta di Lotti: si modifica nella ricetta, che lo
                    ripubblica qui a ogni salvataggio.
                  </p>
                  <a href="/lotti/" className="inline-flex items-center gap-2 min-h-[44px] text-sm font-semibold">
                    <ExternalLink className="w-4 h-4" aria-hidden="true" /> Apri Lotti
                  </a>
                </div>
              )}

              <div className="flex gap-2 pt-4">
                <Button onClick={handleSave} className="flex-1" disabled={saving || daLotti(editingProduct)}>
                  <Save className="w-4 h-4 mr-2" />
                  {saving ? 'Salvataggio…' : 'Salva'}
                </Button>
                <Button onClick={() => setEditingProduct(null)} variant="outline">
                  <X className="w-4 h-4 mr-2" />
                  Annulla
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ProductManager;
