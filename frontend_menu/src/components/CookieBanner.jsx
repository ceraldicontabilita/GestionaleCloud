import React from 'react';
import { Cookie } from 'lucide-react';
import { FOCUS_SALVIA } from './ProdottiSottocategoria';

// Il banner chiede una scelta esplicita: sia «Accetto» sia «Rifiuto» vengono
// registrati (con la data) da chi lo monta, cosi' il rifiuto non si dimentica.
const CookieBanner = ({ onAccept, onDecline, language = 'it' }) => {
  const t = (it, en) => (language === 'it' ? it : en);
  return (
    <div
      role="region"
      aria-label={t('Scelta sui cookie', 'Cookie choice')}
      className="sticky top-0 z-50 bg-[#3d4d3d] text-white py-3 px-4 shadow-lg"
      data-testid="banner-cookie"
    >
      <div className="max-w-4xl mx-auto flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <Cookie className="w-6 h-6 text-[#d4af37] flex-shrink-0" aria-hidden="true" />
          <p className="text-sm">
            {t(
              'Usiamo solo i cookie necessari al funzionamento del sito.',
              'We only use the cookies necessary for the operation of the website.'
            )}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            type="button"
            onClick={onDecline}
            className={`min-h-[44px] px-4 rounded-md bg-transparent border border-white text-white hover:bg-white/10 transition-colors text-sm ${FOCUS_SALVIA}`}
          >
            {t('Rifiuto', 'Decline')}
          </button>
          <button
            type="button"
            onClick={onAccept}
            className={`min-h-[44px] px-4 rounded-md bg-[#d4af37] text-black font-medium hover:bg-[#c9a332] transition-colors text-sm ${FOCUS_SALVIA}`}
          >
            {t('Accetto', 'Accept')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default CookieBanner;
