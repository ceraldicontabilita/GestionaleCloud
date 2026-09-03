import React from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { ChevronRight } from 'lucide-react';

const SubcategoryModal = ({ isOpen, onClose, category, language, onSelectSubcategory }) => {
  if (!category) return null;

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="bg-[#4a5d4a] text-white border-[#5d7056] max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-2xl font-bold text-white">
            {language === 'it' ? category.nameIT : category.name}
          </DialogTitle>
        </DialogHeader>
        <div className="mt-6 space-y-3">
          {category.subcategories && category.subcategories.map(subcategory => (
            <div
              key={subcategory.id}
              onClick={() => onSelectSubcategory(subcategory)}
              className="bg-[#3d4d3d] rounded-lg overflow-hidden hover:bg-[#354535] transition-all cursor-pointer group"
            >
              <div className="flex items-center">
                {subcategory.image && (
                  <div className="w-24 h-24 flex-shrink-0">
                    <img 
                      src={subcategory.image} 
                      alt={language === 'it' ? subcategory.nameIT : subcategory.name}
                      className="w-full h-full object-cover"
                    />
                  </div>
                )}
                <div className="flex-1 p-4 flex items-center justify-between">
                  <div>
                    <h3 className="font-semibold text-lg">
                      {language === 'it' ? subcategory.nameIT : subcategory.name}
                    </h3>
                    <p className="text-sm text-white/60 mt-1">
                      {subcategory.items.length} {language === 'it' ? 'prodotti' : 'products'}
                    </p>
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

export default SubcategoryModal;