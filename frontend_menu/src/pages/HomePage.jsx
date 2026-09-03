import React, { useState, useEffect } from 'react';
import { MapPin, Filter, Facebook, Instagram, Loader2 } from 'lucide-react';
import { useMenu } from '../context/MenuContext';
import CookieBanner from '../components/CookieBanner';
import SubcategoryModal from '../components/SubcategoryModal';
import MenuModal from '../components/MenuModal';
import AllergensModal from '../components/AllergensModal';
import CartDrawer from '../components/CartDrawer';

const HomePage = () => {
  const { menuCategories, allergensList, loading, error } = useMenu();
  const [showCookieBanner, setShowCookieBanner] = useState(true);
  const [language, setLanguage] = useState('en');
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [selectedSubcategory, setSelectedSubcategory] = useState(null);
  const [showSubcategoryModal, setShowSubcategoryModal] = useState(false);
  const [showMenuModal, setShowMenuModal] = useState(false);
  const [showAllergensModal, setShowAllergensModal] = useState(false);
  const [selectedAllergens, setSelectedAllergens] = useState([]);

  useEffect(() => {
    const cookieAccepted = localStorage.getItem('cookieAccepted');
    if (cookieAccepted) {
      setShowCookieBanner(false);
    }
  }, []);

  const handleCookieAccept = () => {
    localStorage.setItem('cookieAccepted', 'true');
    setShowCookieBanner(false);
  };

  const handleCookieDecline = () => {
    setShowCookieBanner(false);
  };

  const handleCategoryClick = (category) => {
    setSelectedCategory(category);
    setShowSubcategoryModal(true);
  };

  const handleSubcategorySelect = (subcategory) => {
    setSelectedSubcategory(subcategory);
    setShowSubcategoryModal(false);
    setShowMenuModal(true);
  };

  const toggleLanguage = () => {
    setLanguage(prev => prev === 'en' ? 'it' : 'en');
  };

  return (
    <div className="min-h-screen bg-[#4a5d4a]">
      {showCookieBanner && (
        <CookieBanner onAccept={handleCookieAccept} onDecline={handleCookieDecline} />
      )}

      <div className={`${showCookieBanner ? 'pt-16' : ''}`}>
        {/* Header Banner */}
        <div className="relative w-full h-48 overflow-hidden">
          <img
            src={`${process.env.PUBLIC_URL || ''}/images/banner.jpg`}
            alt="Ceraldi Caffé"
            className="w-full h-full object-cover"
          />
        </div>

        {/* Main Content */}
        <div className="max-w-4xl mx-auto px-4 py-8">
          {/* Logo Section */}
          <div className="flex justify-center mb-6">
            <div className="w-24 h-24 rounded-full overflow-hidden border-4 border-white shadow-lg">
              <img
                src={`${process.env.PUBLIC_URL || ''}/images/logo.jpg`}
                alt="Logo"
                className="w-full h-full object-cover"
              />
            </div>
          </div>

          {/* Title and Description */}
          <div className="text-center mb-6">
            <h1 className="text-3xl font-bold text-white mb-3">Ceraldi Caffé</h1>
            <p className="text-white/90 text-sm mb-2">
              {language === 'it'
                ? 'Artigiani per passione dal 1973. Dalla colazione all\'aperitivo nel cuore di Napoli. #ceraldicaffe #ceraldipassion'
                : 'Artisans with passion since 1973. From breakfast to aperitif in the heart of Naples. #ceraldicaffe #ceraldipassion'}
            </p>
            <a
              href="https://maps.google.com/?q=Piazza+Carità,+14,+80134+Napoli+NA,+Italia"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-white/80 hover:text-white transition-colors text-sm"
            >
              <MapPin className="w-4 h-4" />
              Piazza Carità 14, Napoli (NA)
            </a>
          </div>

          {/* Allergens Filter */}
          <div className="mb-8">
            <button
              onClick={() => setShowAllergensModal(true)}
              className="w-full bg-[#3d4d3d] text-white rounded-lg py-3 px-4 flex items-center justify-between hover:bg-[#354535] transition-colors"
            >
              <span>{language === 'it' ? 'Filtro Allergeni' : 'Allergens filter'}</span>
              <div className="flex items-center gap-2">
                {selectedAllergens.length > 0 && (
                  <span className="bg-[#d4af37] text-black text-xs px-2 py-1 rounded-full font-medium">
                    {selectedAllergens.length}
                  </span>
                )}
                <Filter className="w-5 h-5 text-[#d4af37]" />
              </div>
            </button>
          </div>

          {/* Loading State */}
          {loading && (
            <div className="flex flex-col items-center justify-center py-12">
              <Loader2 className="w-8 h-8 text-[#d4af37] animate-spin mb-4" />
              <p className="text-white/80">
                {language === 'it' ? 'Caricamento menu...' : 'Loading menu...'}
              </p>
            </div>
          )}

          {/* Error State */}
          {error && !loading && (
            <div className="text-center py-12">
              <p className="text-white/80 mb-4">
                {language === 'it' ? 'Errore nel caricamento del menu' : 'Error loading menu'}
              </p>
            </div>
          )}

          {/* Menu Categories */}
          {!loading && !error && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
              {menuCategories.map(category => (
                <div
                  key={category.id}
                  onClick={() => handleCategoryClick(category)}
                  className="relative h-48 rounded-lg overflow-hidden cursor-pointer group transform transition-transform hover:scale-105"
                  data-testid={`category-${category.id}`}
                >
                  <img
                    src={category.image}
                    alt={category.name}
                    className="w-full h-full object-cover"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent" />
                  <div className="absolute bottom-0 left-0 right-0 p-4">
                    <div className="bg-[#d4af37]/90 rounded-lg py-2 px-4 text-center group-hover:bg-[#d4af37] transition-colors">
                      <h3 className="font-semibold text-black">
                        {language === 'it' ? category.nameIT : category.name}
                      </h3>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Language Selector */}
          <div className="mb-6">
            <button
              onClick={toggleLanguage}
              className="w-full bg-[#3d4d3d] text-white rounded-lg py-3 px-4 flex items-center justify-between hover:bg-[#354535] transition-colors"
            >
              <span>{language === 'it' ? 'Cambia Lingua' : 'Change Language'}</span>
              <div className="flex items-center gap-2">
                <span className="text-sm">{language === 'it' ? '🇮🇹 IT' : '🇬🇧 EN'}</span>
              </div>
            </button>
          </div>

          {/* Social Media Icons */}
          <div className="flex justify-center gap-4 mb-8">
            <a
              href="#"
              className="w-12 h-12 rounded-full bg-[#d4af37] flex items-center justify-center hover:bg-[#c9a332] transition-colors"
            >
              <Facebook className="w-6 h-6 text-black" />
            </a>
            <a
              href="#"
              className="w-12 h-12 rounded-full bg-[#d4af37] flex items-center justify-center hover:bg-[#c9a332] transition-colors"
            >
              <Instagram className="w-6 h-6 text-black" />
            </a>
          </div>

          {/* Footer */}
          <div className="text-center space-y-3 pb-8">
            <div className="flex justify-center gap-6 text-sm">
              <a href="#" className="text-white/70 hover:text-white transition-colors">
                {language === 'it' ? 'Politica sui Cookie' : 'Cookie policy'}
              </a>
              <a href="#" className="text-white/70 hover:text-white transition-colors">
                {language === 'it' ? 'Informativa sulla Privacy' : 'Privacy Policy'}
              </a>
            </div>
          </div>
        </div>
      </div>

      {/* Modals */}
      <SubcategoryModal
        isOpen={showSubcategoryModal}
        onClose={() => setShowSubcategoryModal(false)}
        category={selectedCategory}
        language={language}
        onSelectSubcategory={handleSubcategorySelect}
      />

      <MenuModal
        isOpen={showMenuModal}
        onClose={() => setShowMenuModal(false)}
        category={selectedSubcategory}
        language={language}
        selectedAllergens={selectedAllergens}
        allergensList={allergensList}
      />

      <AllergensModal
        isOpen={showAllergensModal}
        onClose={() => setShowAllergensModal(false)}
        selectedAllergens={selectedAllergens}
        onApply={setSelectedAllergens}
        language={language}
        allergensList={allergensList}
      />

      <CartDrawer language={language} />
    </div>
  );
};

export default HomePage;