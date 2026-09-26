import React, { useState, useEffect, useCallback, useRef } from 'react';
import { MapPin, Filter, Facebook, Instagram, Loader2, ArrowLeft, ChevronRight, Languages } from 'lucide-react';
import { useMenu } from '../context/MenuContext';
import CookieBanner from '../components/CookieBanner';
import AllergensModal from '../components/AllergensModal';
import CartDrawer from '../components/CartDrawer';
import ProdottiSottocategoria, { FOCUS_SALVIA } from '../components/ProdottiSottocategoria';
import {
  leggiLingua, salvaLingua, leggiConsenso, salvaConsenso,
  CONSENSO_ACCETTATO, CONSENSO_RIFIUTATO,
} from '../lib/preferenzeCliente';
import { COLLEGAMENTI_PUBBLICI, urlConfigurato } from '../lib/collegamentiPubblici';

// Percorso del cliente: categorie -> sottocategorie -> prodotti, tutto nella
// stessa pagina. Il livello sta nell'hash (`#categoria=3&sottocategoria=12`):
// il tasto «indietro» del telefono torna al livello precedente e un link
// condiviso riapre la stessa sezione.
export function leggiVista(hash) {
  const parametri = new URLSearchParams(String(hash || '').replace(/^#/, ''));
  return {
    categoriaId: parametri.get('categoria'),
    sottocategoriaId: parametri.get('sottocategoria'),
  };
}

export function hashVista(vista) {
  const { categoriaId, sottocategoriaId } = vista || {};
  if (!categoriaId) return '';
  const parametri = new URLSearchParams({ categoria: String(categoriaId) });
  if (sottocategoriaId) parametri.set('sottocategoria', String(sottocategoriaId));
  return `#${parametri.toString()}`;
}

const stessoId = (a, b) => a != null && b != null && String(a) === String(b);

/** Facebook, Instagram e informative: si mostra solo cio' che ha un URL vero. */
export const CollegamentiEsterni = ({ language, collegamenti = COLLEGAMENTI_PUBBLICI }) => {
  const t = (it, en) => (language === 'it' ? it : en);
  const social = [
    { chiave: 'facebook', etichetta: 'Facebook', Icona: Facebook },
    { chiave: 'instagram', etichetta: 'Instagram', Icona: Instagram },
  ].filter((s) => urlConfigurato(collegamenti[s.chiave]));
  const informative = [
    { chiave: 'cookiePolicy', etichetta: t('Politica sui cookie', 'Cookie policy') },
    { chiave: 'privacyPolicy', etichetta: t('Informativa sulla privacy', 'Privacy policy') },
  ].filter((s) => urlConfigurato(collegamenti[s.chiave]));

  if (!social.length && !informative.length) return null;

  return (
    <div data-testid="collegamenti-esterni">
      {social.length > 0 && (
        <div className="flex justify-center gap-4 mb-8">
          {social.map(({ chiave, etichetta, Icona }) => (
            <a
              key={chiave}
              href={collegamenti[chiave]}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={etichetta}
              className={`w-12 h-12 rounded-full bg-[#d4af37] flex items-center justify-center hover:bg-[#c9a332] transition-colors ${FOCUS_SALVIA}`}
            >
              <Icona className="w-6 h-6 text-black" aria-hidden="true" />
            </a>
          ))}
        </div>
      )}
      {informative.length > 0 && (
        <div className="flex flex-wrap justify-center gap-x-6 gap-y-2 text-sm pb-8">
          {informative.map(({ chiave, etichetta }) => (
            <a
              key={chiave}
              href={collegamenti[chiave]}
              target="_blank"
              rel="noopener noreferrer"
              className={`inline-flex items-center min-h-[44px] text-white/70 hover:text-white transition-colors rounded ${FOCUS_SALVIA}`}
            >
              {etichetta}
            </a>
          ))}
        </div>
      )}
    </div>
  );
};

const HomePage = () => {
  const { menuCategories, allergensList, loading, error } = useMenu();
  const [consenso, setConsenso] = useState(() => leggiConsenso());
  const [language, setLanguage] = useState(() => leggiLingua());
  const [vista, setVista] = useState(() => leggiVista(window.location.hash));
  const [showAllergensModal, setShowAllergensModal] = useState(false);
  const [selectedAllergens, setSelectedAllergens] = useState([]);
  const titoloVistaRef = useRef(null);
  const primoRender = useRef(true);

  const t = (it, en) => (language === 'it' ? it : en);
  const nome = (x) => (language === 'it' ? x.nameIT || x.name : x.name || x.nameIT);

  useEffect(() => {
    const aggiorna = () => setVista(leggiVista(window.location.hash));
    window.addEventListener('popstate', aggiorna);
    window.addEventListener('hashchange', aggiorna);
    return () => {
      window.removeEventListener('popstate', aggiorna);
      window.removeEventListener('hashchange', aggiorna);
    };
  }, []);

  // La lingua della pagina segue la scelta (lettori di schermo, sillabazione).
  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  // Al cambio di livello il fuoco va sul titolo della sezione: chi usa la
  // tastiera o un lettore di schermo sa dove si trova.
  useEffect(() => {
    if (primoRender.current) {
      primoRender.current = false;
      return;
    }
    const titolo = titoloVistaRef.current;
    if (titolo) {
      titolo.focus({ preventScroll: true });
      if (typeof titolo.scrollIntoView === 'function') {
        titolo.scrollIntoView({ block: 'start', behavior: 'smooth' });
      }
    }
  }, [vista.categoriaId, vista.sottocategoriaId]);

  const vai = useCallback((prossima) => {
    const hash = hashVista(prossima);
    const url = `${window.location.pathname}${window.location.search}${hash}`;
    try {
      window.history.pushState(null, '', url);
    } catch {
      // history non disponibile: resta comunque lo stato in pagina
    }
    setVista({ categoriaId: prossima?.categoriaId || null, sottocategoriaId: prossima?.sottocategoriaId || null });
  }, []);

  const registraConsenso = (scelta) => setConsenso(salvaConsenso(scelta));

  const scegliLingua = (lingua) => {
    setLanguage(lingua);
    salvaLingua(lingua);
  };

  const categoria = (menuCategories || []).find((c) => stessoId(c.id, vista.categoriaId)) || null;
  const sottocategoria = categoria
    ? (categoria.subcategories || []).find((s) => stessoId(s.id, vista.sottocategoriaId)) || null
    : null;

  const bottoneIndietro = (etichetta, destinazione) => (
    <button
      type="button"
      onClick={() => vai(destinazione)}
      className={`inline-flex items-center gap-2 min-h-[44px] px-4 mb-4 rounded-lg bg-[#3d4d3d] text-white hover:bg-[#354535] transition-colors ${FOCUS_SALVIA}`}
      data-testid="menu-indietro"
    >
      <ArrowLeft className="w-5 h-5" aria-hidden="true" />
      {etichetta}
    </button>
  );

  let contenuto = null;
  if (!loading && !error) {
    if (categoria && sottocategoria) {
      contenuto = (
        <section aria-labelledby="titolo-vista" data-testid="vista-prodotti">
          {bottoneIndietro(nome(categoria), { categoriaId: categoria.id })}
          <h2 id="titolo-vista" ref={titoloVistaRef} tabIndex={-1} className="text-2xl font-bold text-white mb-4 outline-none">
            {nome(sottocategoria)}
          </h2>
          <ProdottiSottocategoria
            sottocategoria={sottocategoria}
            language={language}
            selectedAllergens={selectedAllergens}
            allergensList={allergensList}
          />
        </section>
      );
    } else if (categoria) {
      const sottocategorie = categoria.subcategories || [];
      contenuto = (
        <section aria-labelledby="titolo-vista" data-testid="vista-sottocategorie">
          {bottoneIndietro(t('Tutte le categorie', 'All categories'), null)}
          <h2 id="titolo-vista" ref={titoloVistaRef} tabIndex={-1} className="text-2xl font-bold text-white mb-4 outline-none">
            {nome(categoria)}
          </h2>
          <ul className="space-y-3">
            {sottocategorie.map((sotto) => (
              <li key={sotto.id}>
                <button
                  type="button"
                  onClick={() => vai({ categoriaId: categoria.id, sottocategoriaId: sotto.id })}
                  className={`w-full text-left bg-[#3d4d3d] rounded-lg overflow-hidden hover:bg-[#354535] transition-colors group flex items-center min-h-[64px] ${FOCUS_SALVIA}`}
                  data-testid={`subcategory-${sotto.id}`}
                >
                  {sotto.image && (
                    <span className="w-24 h-24 flex-shrink-0">
                      <img src={sotto.image} alt="" className="w-full h-full object-cover" loading="lazy" />
                    </span>
                  )}
                  <span className="flex-1 min-w-0 p-4 flex items-center justify-between gap-3">
                    <span className="min-w-0">
                      <span className="block font-semibold text-lg text-white break-words">{nome(sotto)}</span>
                      <span className="block text-sm text-white/60 mt-1">
                        {(sotto.items || []).length} {t('prodotti', 'products')}
                      </span>
                    </span>
                    <ChevronRight className="w-6 h-6 text-[#d4af37] flex-shrink-0 group-hover:translate-x-1 transition-transform" aria-hidden="true" />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      );
    } else {
      contenuto = (
        <section aria-label={t('Categorie del menu', 'Menu categories')} data-testid="vista-categorie">
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {(menuCategories || []).map((cat) => (
              <li key={cat.id}>
                <button
                  type="button"
                  onClick={() => vai({ categoriaId: cat.id })}
                  className={`relative block w-full h-48 rounded-lg overflow-hidden group transform transition-transform hover:scale-[1.02] ${FOCUS_SALVIA}`}
                  data-testid={`category-${cat.id}`}
                >
                  {cat.image && <img src={cat.image} alt="" className="w-full h-full object-cover" loading="lazy" />}
                  <span className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent" aria-hidden="true" />
                  <span className="absolute bottom-0 left-0 right-0 p-4">
                    <span className="block bg-[#d4af37]/90 rounded-lg py-2 px-4 text-center group-hover:bg-[#d4af37] transition-colors font-semibold text-black">
                      {nome(cat)}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      );
    }
  }

  return (
    <div className="min-h-screen bg-[#4a5d4a] overflow-x-clip">
      {!consenso && (
        <CookieBanner
          language={language}
          onAccept={() => registraConsenso(CONSENSO_ACCETTATO)}
          onDecline={() => registraConsenso(CONSENSO_RIFIUTATO)}
        />
      )}

      {/* Intestazione */}
      <div className="relative w-full h-48 overflow-hidden">
        <img
          src={`${process.env.PUBLIC_URL || ''}/images/banner.jpg`}
          alt="Ceraldi Caffè"
          className="w-full h-full object-cover"
        />
      </div>

      <main className="max-w-4xl mx-auto px-4 py-8 pb-28">
        <div className="flex justify-center mb-6">
          <div className="w-24 h-24 rounded-full overflow-hidden border-4 border-white shadow-lg">
            <img src={`${process.env.PUBLIC_URL || ''}/images/logo.jpg`} alt="Logo" className="w-full h-full object-cover" />
          </div>
        </div>

        <div className="text-center mb-6">
          <h1 className="text-3xl font-bold text-white mb-3">Ceraldi Caffè</h1>
          <p className="text-white/90 text-sm mb-2">
            {t(
              'Artigiani per passione dal 1973. Dalla colazione all\'aperitivo nel cuore di Napoli. #ceraldicaffe #ceraldipassion',
              'Artisans with passion since 1973. From breakfast to aperitif in the heart of Naples. #ceraldicaffe #ceraldipassion'
            )}
          </p>
          <a
            href="https://maps.google.com/?q=Piazza+Carità,+14,+80134+Napoli+NA,+Italia"
            target="_blank"
            rel="noopener noreferrer"
            className={`inline-flex items-center gap-2 min-h-[44px] text-white/80 hover:text-white transition-colors text-sm rounded ${FOCUS_SALVIA}`}
          >
            <MapPin className="w-4 h-4" aria-hidden="true" />
            Piazza Carità 14, Napoli (NA)
          </a>
        </div>

        {/* Lingua: italiano di partenza, inglese a scelta */}
        <div className="mb-4 flex items-center justify-center gap-2" role="group" aria-label={t('Lingua', 'Language')}>
          <Languages className="w-5 h-5 text-[#d4af37]" aria-hidden="true" />
          {[
            { codice: 'it', etichetta: 'Italiano' },
            { codice: 'en', etichetta: 'English' },
          ].map(({ codice, etichetta }) => (
            <button
              key={codice}
              type="button"
              lang={codice}
              aria-pressed={language === codice}
              onClick={() => scegliLingua(codice)}
              className={`min-h-[44px] px-4 rounded-lg text-sm font-semibold transition-colors ${FOCUS_SALVIA} ${
                language === codice ? 'bg-[#d4af37] text-black' : 'bg-[#3d4d3d] text-white hover:bg-[#354535]'
              }`}
              data-testid={`lingua-${codice}`}
            >
              {etichetta}
            </button>
          ))}
        </div>

        {/* Filtro allergeni */}
        <div className="mb-8">
          <button
            type="button"
            onClick={() => setShowAllergensModal(true)}
            className={`w-full min-h-[44px] bg-[#3d4d3d] text-white rounded-lg py-3 px-4 flex items-center justify-between hover:bg-[#354535] transition-colors ${FOCUS_SALVIA}`}
          >
            <span>{t('Filtro allergeni', 'Allergens filter')}</span>
            <span className="flex items-center gap-2">
              {selectedAllergens.length > 0 && (
                <span className="bg-[#d4af37] text-black text-xs px-2 py-1 rounded-full font-medium">
                  {selectedAllergens.length} {t('esclusi', 'excluded')}
                </span>
              )}
              <Filter className="w-5 h-5 text-[#d4af37]" aria-hidden="true" />
            </span>
          </button>
        </div>

        {loading && (
          <div className="flex flex-col items-center justify-center py-12">
            <Loader2 className="w-8 h-8 text-[#d4af37] animate-spin mb-4" aria-hidden="true" />
            <p className="text-white/80">{t('Caricamento menu...', 'Loading menu...')}</p>
          </div>
        )}

        {error && !loading && (
          <div className="text-center py-12">
            <p className="text-white/80 mb-4">{t('Errore nel caricamento del menu', 'Error loading menu')}</p>
          </div>
        )}

        <div className="mb-8">{contenuto}</div>

        <CollegamentiEsterni language={language} />
      </main>

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
