import React from 'react';
import { AlertCircle, Plus } from 'lucide-react';
import { useCart } from '../context/CartContext';
import { toast } from '../hooks/use-toast';

// Anello di focus salvia, visibile anche sul fondo verde scuro del menu.
export const FOCUS_SALVIA =
  'focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[#5b7a6b] focus-visible:ring-offset-2 focus-visible:ring-offset-[#faf7f0]';

/**
 * I prodotti di una sottocategoria, mostrati nella pagina (non in una finestra
 * sopra un'altra finestra): foto, prezzo, allergeni e «Aggiungi al carrello».
 */
const ProdottiSottocategoria = ({ sottocategoria, language, selectedAllergens = [], allergensList = [] }) => {
  const { addItem } = useCart();
  const t = (it, en) => (language === 'it' ? it : en);

  const handleAdd = (item) => {
    addItem(item);
    toast({
      title: t('Aggiunto al carrello', 'Added to cart'),
      description: language === 'it' ? item.nameIT : item.name,
    });
  };

  const prodotti = (sottocategoria.items || []).filter((item) => {
    if (selectedAllergens.length === 0) return true;
    return !(item.allergens || []).some((a) => selectedAllergens.includes(a));
  });

  const allergene = (id) => allergensList.find((a) => a.id === id);

  if (prodotti.length === 0) {
    return (
      <div className="text-center py-12 text-white/70">
        <AlertCircle className="w-12 h-12 mx-auto mb-3 text-[#d4af37]" aria-hidden="true" />
        <p className="text-lg font-medium mb-2">{t('Nessun prodotto disponibile', 'No products available')}</p>
        {selectedAllergens.length > 0 && (
          <p className="text-sm">
            {t(
              'Tutti i prodotti di questa sezione contengono allergeni che hai escluso col filtro.',
              'All products in this section contain allergens you filtered out.'
            )}
          </p>
        )}
      </div>
    );
  }

  return (
    <ul className="space-y-4" data-testid="elenco-prodotti">
      {prodotti.map((item) => {
        const nome = language === 'it' ? item.nameIT : item.name;
        return (
          <li key={item.id} className="bg-[#3d4d3d] rounded-lg overflow-hidden">
            {item.image && (
              <div className="w-full h-48 overflow-hidden">
                <img src={item.image} alt={nome} className="w-full h-full object-cover" loading="lazy" />
              </div>
            )}
            <div className="p-4">
              <div className="flex justify-between items-start gap-4 mb-2">
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-lg break-words">{nome}</h3>
                  {item.description && (
                    <p className="text-sm text-white/70 mt-1">
                      {language === 'it' ? item.descriptionIT || item.description : item.description}
                    </p>
                  )}
                </div>
                <span className="text-[#d4af37] font-bold text-lg whitespace-nowrap">{item.price}</span>
              </div>
              <button
                type="button"
                onClick={() => handleAdd(item)}
                className={`mt-3 w-full min-h-[44px] flex items-center justify-center gap-2 bg-[#d4af37] hover:bg-[#c9a332] text-black font-semibold rounded-lg py-2 transition-colors ${FOCUS_SALVIA}`}
              >
                <Plus className="w-4 h-4" aria-hidden="true" />
                {t('Aggiungi al carrello', 'Add to cart')}
              </button>
              {(item.allergens || []).length > 0 && (
                <div className="mt-3 pt-3 border-t border-white/10">
                  <p className="text-xs text-white/60 mb-2">{t('Contiene allergeni:', 'Contains allergens:')}</p>
                  <div className="flex flex-wrap gap-2">
                    {item.allergens.map((id) => {
                      const a = allergene(id);
                      return a ? (
                        <span
                          key={id}
                          className="inline-flex items-center gap-1 bg-[#d4af37]/20 text-[#d4af37] px-2 py-1 rounded-full text-xs font-medium"
                        >
                          {language === 'it' ? a.nameIT : a.name}
                        </span>
                      ) : null;
                    })}
                  </div>
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
};

export default ProdottiSottocategoria;
