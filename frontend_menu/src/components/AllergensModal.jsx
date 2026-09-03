import React, { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Checkbox } from './ui/checkbox';
import { allergensList } from '../mockData';
import { Button } from './ui/button';
import { Info } from 'lucide-react';

const AllergensModal = ({ isOpen, onClose, selectedAllergens, onApply, language }) => {
  const [tempSelected, setTempSelected] = useState(selectedAllergens);

  const handleToggle = (allergenId) => {
    setTempSelected(prev => 
      prev.includes(allergenId)
        ? prev.filter(id => id !== allergenId)
        : [...prev, allergenId]
    );
  };

  const handleApply = () => {
    onApply(tempSelected);
    onClose();
  };

  const handleCancel = () => {
    setTempSelected(selectedAllergens);
    onClose();
  };

  const handleClearAll = () => {
    setTempSelected([]);
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleCancel}>
      <DialogContent className="bg-[#4a5d4a] text-white border-[#5d7056] max-w-md max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-2xl font-bold text-white">
            {language === 'it' ? 'Filtro Allergeni' : 'Allergens Filter'}
          </DialogTitle>
        </DialogHeader>
        <div className="mt-6 space-y-4">
          <div className="bg-[#3d4d3d] rounded-lg p-3 flex items-start gap-2">
            <Info className="w-5 h-5 text-[#d4af37] flex-shrink-0 mt-0.5" />
            <p className="text-xs text-white/80">
              {language === 'it' 
                ? 'Seleziona gli allergeni che vuoi escludere dal menu. I prodotti contenenti questi allergeni non saranno mostrati.'
                : 'Select allergens to exclude from the menu. Products containing these allergens will not be shown.'}
            </p>
          </div>
          
          <div className="flex justify-between items-center pt-2">
            <p className="text-sm font-medium text-white/90">
              {language === 'it' ? 'Allergeni disponibili:' : 'Available allergens:'}
            </p>
            {tempSelected.length > 0 && (
              <button
                onClick={handleClearAll}
                className="text-xs text-[#d4af37] hover:text-[#c9a332] transition-colors"
              >
                {language === 'it' ? 'Deseleziona tutto' : 'Clear all'}
              </button>
            )}
          </div>

          <div className="space-y-3 max-h-[300px] overflow-y-auto pr-2">
            {allergensList.map(allergen => (
              <div 
                key={allergen.id} 
                className="flex items-center space-x-3 bg-[#3d4d3d] rounded-lg p-3 hover:bg-[#354535] transition-colors"
              >
                <Checkbox
                  id={allergen.id}
                  checked={tempSelected.includes(allergen.id)}
                  onCheckedChange={() => handleToggle(allergen.id)}
                  className="border-white data-[state=checked]:bg-[#d4af37] data-[state=checked]:border-[#d4af37]"
                />
                <label
                  htmlFor={allergen.id}
                  className="flex items-center gap-2 flex-1 text-sm font-medium leading-none cursor-pointer"
                >
                  <span className="text-lg">{allergen.icon}</span>
                  <span>{language === 'it' ? allergen.nameIT : allergen.name}</span>
                </label>
              </div>
            ))}
          </div>

          <div className="flex gap-3 mt-6 pt-4 border-t border-white/10">
            <Button
              onClick={handleCancel}
              variant="outline"
              className="flex-1 bg-transparent border-white text-white hover:bg-white/10"
            >
              {language === 'it' ? 'Annulla' : 'Cancel'}
            </Button>
            <Button
              onClick={handleApply}
              className="flex-1 bg-[#d4af37] text-black hover:bg-[#c9a332] font-semibold"
            >
              {language === 'it' ? 'Applica' : 'Apply'}
              {tempSelected.length > 0 && ` (${tempSelected.length})`}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default AllergensModal;