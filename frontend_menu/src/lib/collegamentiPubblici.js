// Collegamenti del menu pubblico: l'unico punto dove si scrivono.
//
// - Social: gli account ufficiali del locale (Instagram «Ceraldi Caffè
//   (@ceraldicaffe)», pagina Facebook «ceraldicaffe»), verificati il
//   26/09/2026. Un valore `null` nasconde il link.
// - Informative: pagine del Menu stesso (`/privacy`, `/cookie`), scritte su cio'
//   che questo codice fa davvero. Il sito ceraldicaffe.it non ne pubblica una
//   raggiungibile, e un link a `#` sembra funzionare ma non porta da nessuna parte.
export const COLLEGAMENTI_PUBBLICI = {
  facebook: 'https://www.facebook.com/ceraldicaffe/',
  instagram: 'https://www.instagram.com/ceraldicaffe/',
  cookiePolicy: '/cookie',
  privacyPolicy: '/privacy',
};

/** Vero solo per un indirizzo https completo: `#`, vuoto o `null` non valgono. */
export function urlConfigurato(url) {
  if (typeof url !== 'string' || !url.trim()) return false;
  try {
    const u = new URL(url.trim());
    return u.protocol === 'https:' && Boolean(u.hostname);
  } catch {
    return false;
  }
}

/** Pagina interna del Menu (`/privacy`): mai `//dominio`, che porterebbe fuori. */
export function percorsoInterno(valore) {
  return typeof valore === 'string' && /^\/[a-z0-9-]+$/i.test(valore.trim());
}

/** Indirizzo da mettere nell'href: le pagine interne stanno sotto `/menu`. */
export function hrefCollegamento(valore) {
  if (percorsoInterno(valore)) return `${process.env.PUBLIC_URL || ''}${valore.trim()}`;
  return urlConfigurato(valore) ? valore.trim() : null;
}
