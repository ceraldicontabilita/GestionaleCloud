export const CATALOGO_PRODOTTI_DEFAULT = "acquaviva";
export const CATALOGHI_PRODOTTI_FISSI = [
  "miei",
  "acquaviva",
  "acquaviva_acquistati",
  "saima",
  "saima_ricettari",
  "mepa",
  "pasticcere",
  "tremarie",
  "alfa",
  "sammontana",
  "bindi",
];

/**
 * Restituisce il catalogo richiesto da un deep-link come
 * #prodotti/saima o #prodotti/mepa. La funzione accetta anche cataloghi
 * dinamici, quindi non contiene una lista chiusa di fornitori.
 */
export function leggiCatalogoProdotti(hash = "") {
  const [pagina, catalogo] = String(hash).replace(/^#/, "").split("/");
  if (pagina !== "prodotti") return null;
  return catalogo?.trim() || null;
}

/** Il contenitore Prodotti deve mostrare i cataloghi quando l'URL ne indica uno. */
export function risolviSottoTabProdotti(hash, fallback = "listino") {
  return leggiCatalogoProdotti(hash) ? "cataloghi" : fallback;
}

/**
 * Risolve il catalogo interno alla pagina. Oltre a quelli fissi accetta le
 * fonti web che il backend restituisce in modo dinamico.
 */
export function risolviCatalogoProdotti(
  hash,
  cataloghiDinamici = [],
  fallback = CATALOGO_PRODOTTI_DEFAULT
) {
  const richiesto = leggiCatalogoProdotti(hash);
  const validi = new Set([...CATALOGHI_PRODOTTI_FISSI, ...cataloghiDinamici]);
  return richiesto && validi.has(richiesto) ? richiesto : fallback;
}

export function hashCatalogoProdotti(catalogo = CATALOGO_PRODOTTI_DEFAULT) {
  return `prodotti/${catalogo || CATALOGO_PRODOTTI_DEFAULT}`;
}
