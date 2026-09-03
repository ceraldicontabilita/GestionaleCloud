import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { toast } from '../../hooks/use-toast';
import { Edit, Save, X, Search, RefreshCw } from 'lucide-react';
import axios from 'axios';
import { menuCategories, allergensList } from '../../mockData';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const ProductManager = () => {
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [selectedSubcategory, setSelectedSubcategory] = useState(null);
  const [editingProduct, setEditingProduct] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [syncingQromo, setSyncingQromo] = useState(false);

  // Aggiunta GestionaleCloud: replica il menu pubblicato su Qromo nelle tabelle menu_*
  const handleSyncQromo = async () => {
    setSyncingQromo(true);
    try {
      const token = localStorage.getItem('admin_token');
      const response = await axios.post(
        `${BACKEND_URL}/api/admin/sync-qromo`,
        { dry_run: false },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      const d = response.data;
      toast({
        title: 'Sincronizzazione da Qromo completata',
        description: `${d.categories} categorie, ${d.subcategories} sottocategorie, ${d.products} prodotti`
      });
    } catch (error) {
      toast({
        title: 'Errore',
        description: error.response?.data?.detail || 'Sincronizzazione da Qromo non riuscita',
        variant: 'destructive'
      });
    } finally {
      setSyncingQromo(false);
    }
  };

  const getAllProducts = () => {
    const products = [];
    menuCategories.forEach(category => {
      category.subcategories?.forEach(subcategory => {
        subcategory.items?.forEach(item => {
          products.push({
            ...item,
            categoryName: category.nameIT,
            subcategoryName: subcategory.nameIT,
            category_id: category.id,
            subcategory_id: subcategory.id
          });
        });
      });
    });
    return products;
  };

  const filteredProducts = getAllProducts().filter(product => {
    const search = searchTerm.toLowerCase();
    return (
      product.nameIT.toLowerCase().includes(search) ||
      product.name.toLowerCase().includes(search) ||
      product.price.toLowerCase().includes(search)
    );
  });

  const handleEdit = (product) => {
    setEditingProduct({ ...product });
  };

  const handleSave = () => {
    // In a real implementation, this would update MongoDB or backend
    toast({
      title: 'Info',
      description: 'Per salvare le modifiche, aggiorna manualmente mockData.js o implementa MongoDB',
      variant: 'default'
    });
    
    console.log('Product to save:', editingProduct);
    setEditingProduct(null);
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
        </CardContent>
      </Card>

      {/* Products List */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between gap-4">
            <span>Tutti i Prodotti ({filteredProducts.length})</span>
            <Button size="sm" variant="outline" onClick={handleSyncQromo} disabled={syncingQromo}>
              <RefreshCw className={`w-4 h-4 mr-2 ${syncingQromo ? 'animate-spin' : ''}`} />
              {syncingQromo ? 'Sincronizzazione...' : 'Sincronizza da Qromo'}
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2 max-h-[600px] overflow-y-auto">
            {filteredProducts.map((product) => (
              <div
                key={product.id}
                className="flex items-center justify-between p-4 border rounded-lg hover:bg-gray-50 transition-colors"
              >
                <div className="flex-1">
                  <div className="flex items-start gap-4">
                    {product.image && (
                      <img
                        src={product.image}
                        alt={product.nameIT}
                        className="w-16 h-16 object-cover rounded"
                      />
                    )}
                    <div className="flex-1">
                      <h4 className="font-semibold text-gray-900">{product.nameIT}</h4>
                      <p className="text-sm text-gray-500">{product.name}</p>
                      <div className="flex items-center gap-4 mt-1">
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
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleEdit(product)}
                >
                  <Edit className="w-4 h-4" />
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
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Nome Italiano</Label>
                  <Input
                    value={editingProduct.nameIT}
                    onChange={(e) => setEditingProduct({...editingProduct, nameIT: e.target.value})}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Nome Inglese</Label>
                  <Input
                    value={editingProduct.name}
                    onChange={(e) => setEditingProduct({...editingProduct, name: e.target.value})}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label>Prezzo</Label>
                <Input
                  value={editingProduct.price}
                  onChange={(e) => setEditingProduct({...editingProduct, price: e.target.value})}
                />
              </div>

              <div className="space-y-2">
                <Label>Descrizione Italiana</Label>
                <Textarea
                  value={editingProduct.descriptionIT || ''}
                  onChange={(e) => setEditingProduct({...editingProduct, descriptionIT: e.target.value})}
                  rows={2}
                />
              </div>

              <div className="space-y-2">
                <Label>Descrizione Inglese</Label>
                <Textarea
                  value={editingProduct.description || ''}
                  onChange={(e) => setEditingProduct({...editingProduct, description: e.target.value})}
                  rows={2}
                />
              </div>

              <div className="space-y-2">
                <Label>URL Immagine</Label>
                <Input
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

              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                <p className="text-sm text-yellow-800">
                  <strong>Nota:</strong> Le modifiche verranno mostrate qui ma non salvate automaticamente.
                  Per applicare le modifiche, aggiorna il file <code className="bg-yellow-100 px-1 rounded">mockData.js</code> con i nuovi valori
                  o implementa un database MongoDB per la persistenza automatica.
                </p>
              </div>

              <div className="flex gap-2 pt-4">
                <Button onClick={handleSave} className="flex-1">
                  <Save className="w-4 h-4 mr-2" />
                  Salva (Log Console)
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