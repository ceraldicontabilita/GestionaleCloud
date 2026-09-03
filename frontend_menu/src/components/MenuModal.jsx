import React from 'react';
import { X, AlertCircle, Plus } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { useCart } from '../context/CartContext';
import { toast } from '../hooks/use-toast';

const MenuModal = ({ isOpen, onClose, category, language, selectedAllergens, allergensList = [] }) => {
  const { addItem } = useCart();

  if (!category) return null;

  const handleAdd = (item) => {
    addItem(item);
    toast({
      title: language === 'it' ? 'Aggiunto al carrello' : 'Added to cart',
      description: language === 'it' ? item.nameIT : item.name
    });
  };

  const filteredItems = (category.items || []).filter(item => {
    if (selectedAllergens.length === 0) return true;
    return !(item.allergens || []).some(allergen => selectedAllergens.includes(allergen));
  });

  const getAllergenInfo = (allergenId) => {
    return allergensList.find(a => a.id === allergenId);
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="bg-[#4a5d4a] text-white border-[#5d7056] max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-2xl font-bold text-white">
            {language === 'it' ? category.nameIT : category.name}
          </DialogTitle>
        </DialogHeader>
        <div className="mt-6">
          {filteredItems.length === 0 ? (
            <div className="text-center py-12 text-white/70">
              <AlertCircle className="w-12 h-12 mx-auto mb-3 text-[#d4af37]" />
              <p className="text-lg font-medium mb-2">
                {language === 'it' ? 'Nessun prodotto disponibile' : 'No products available'}
              </p>
              <p className="text-sm">
                {language === 'it' 
                  ? 'Tutti i prodotti in questa categoria contengono allergeni filtrati.' 
                  : 'All products in this category contain filtered allergens.'}
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {filteredItems.map(item => (
                <div
                  key={item.id}
                  className="bg-[#3d4d3d] rounded-lg overflow-hidden hover:bg-[#354535] transition-colors"
                >
                  {item.image && (
                    <div className="w-full h-48 overflow-hidden">
                      <img 
                        src={item.image} 
                        alt={language === 'it' ? item.nameIT : item.name}
                        className="w-full h-full object-cover"
                      />
                    </div>
                  )}
                  <div className="p-4">
                    <div className="flex justify-between items-start mb-2">
                      <div className="flex-1">
                        <h3 className="font-semibold text-lg">
                          {language === 'it' ? item.nameIT : item.name}
                        </h3>
                        {item.description && (
                          <p className="text-sm text-white/70 mt-1">
                            {language === 'it' ? item.descriptionIT || item.description : item.description}
                          </p>
                        )}
                      </div>
                      <span className="text-[#d4af37] font-bold text-lg ml-4">{item.price}</span>
                    </div>
                    <button
                      onClick={() => handleAdd(item)}
                      className="mt-3 w-full flex items-center justify-center gap-2 bg-[#d4af37] hover:bg-[#c9a332] text-black font-semibold rounded-lg py-2 transition-colors"
                    >
                      <Plus className="w-4 h-4" />
                      {language === 'it' ? 'Aggiungi al carrello' : 'Add to cart'}
                    </button>
                    {(item.allergens || []).length > 0 && (
                      <div className="mt-3 pt-3 border-t border-white/10">
                        <p className="text-xs text-white/60 mb-2">
                          {language === 'it' ? 'Contiene allergeni:' : 'Contains allergens:'}
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {(item.allergens || []).map(allergenId => {
                            const allergen = getAllergenInfo(allergenId);
                            return allergen ? (
                              <span
                                key={allergenId}
                                className="inline-flex items-center gap-1 bg-[#d4af37]/20 text-[#d4af37] px-2 py-1 rounded-full text-xs font-medium"
                              >
                                {allergen.icon} {language === 'it' ? allergen.nameIT : allergen.name}
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

export default MenuModal;