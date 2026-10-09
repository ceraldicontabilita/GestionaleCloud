// Filtri di presentazione, non una seconda classificazione persistente.
// Le spunte esplicite della ricetta prevalgono; il nome aiuta solo a sfogliare.
export const CATEGORIE_PRODOTTI = [
  { id: "biscotti", label: "Biscotti" },
  { id: "creme", label: "Creme" },
  { id: "pasticceria_classica", label: "Pasticceria" },
  { id: "colazioni", label: "Colazione" },
  { id: "natale", label: "Natale" },
  { id: "pasqua", label: "Pasqua" },
  { id: "bagne", label: "Bagne" },
  { id: "aperitivo", label: "Aperitivo" },
];

const normalizza = (s) => String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
export function categorieProdotto(prodotto) {
  const esplicite = prodotto.categorie_rapide || [];
  const categorie = new Set(esplicite);
  const nome = normalizza(prodotto.nome);
  // Non usare il testo ingredienti: una torta con crema non è una crema base.
  if (esplicite.includes("dolci_secchi") || /biscott|amarett|baci di dama|brutti e buoni|cantucc|cookies|frollin/.test(nome)) categorie.add("biscotti");
  if (/^crema\b|^creme\b|^ganache\b|^cremoso\b/.test(nome)) categorie.add("creme");
  if (/^bagna\b|^bagne\b/.test(nome)) categorie.add("bagne");
  if (/cornett|croissant|brioche|pain au|venezian|sfogliatell|colazione/.test(nome)) categorie.add("colazioni");
  if (/panetton|pandor|roccoco|mostacciol|struffol|natale/.test(nome)) categorie.add("natale");
  if (/pastiera|colomba|pasqua|casatiell/.test(nome)) categorie.add("pasqua");
  if (prodotto.reparto === "rosticceria" || /aperitivo/.test(nome)) categorie.add("aperitivo");
  if (prodotto.reparto !== "rosticceria" && !["biscotti", "creme", "bagne", "colazioni"].some(c => categorie.has(c))) categorie.add("pasticceria_classica");
  return [...categorie];
}

export function filtraProdotti(prodotti, { scheda = "pasticceria", categoria = "tutte", search = "", mostraTutti = false } = {}) {
  const cerca = normalizza(search).trim();
  return prodotti.filter(p => {
    const casa = p.fonte === "casa";
    const acquaviva = /acquaviva/.test(normalizza(p.fornitore));
    const reparto = p.reparto || "pasticceria";
    if (scheda === "pasticceria" && (!casa || reparto !== "pasticceria")) return false;
    if (scheda === "rosticceria" && (!casa || reparto !== "rosticceria")) return false;
    if (scheda === "acquaviva" && (casa || !acquaviva)) return false;
    if (scheda === "fornitori" && (casa || acquaviva)) return false;
    if (!casa && !mostraTutti && p.gia_acquistato === false) return false;
    return (!cerca || normalizza(p.nome).includes(cerca)) && (categoria === "tutte" || categorieProdotto(p).includes(categoria));
  });
}
