// Collegamenti esterni del menu pubblico: l'unico punto dove si scrivono.
//
// Oggi nessun indirizzo e' configurato: nel repository e nel database del Menu
// non c'e' un URL reale per le pagine social o per le informative, e un link
// che punta a `#` sembra funzionare ma non porta da nessuna parte. Finche' un
// valore resta `null` il link non si mostra. Per attivarlo basta scrivere qui
// l'indirizzo vero (https), senza toccare le pagine.
export const COLLEGAMENTI_PUBBLICI = {
  facebook: null,
  instagram: null,
  cookiePolicy: null,
  privacyPolicy: null,
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
