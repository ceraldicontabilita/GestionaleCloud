// Le fonti catalogo aggiunte dopo le tre storiche (Acquaviva, SAIMA, MEPA) devono
// comparire nella Home di Lotti da sole: una card per fonte con prodotti, senza
// toccare il codice (come la scheda in «Listini e cataloghi»).
export const FONTI_FISSE = ["acquaviva", "saima", "mepa"];

const dataIt = (iso) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
  return m ? `${m[3]}/${m[2]}/${m[1]}` : "";
};

export function carteFontiCatalogo(fonti) {
  return (Array.isArray(fonti) ? fonti : [])
    .filter((f) => f && f.fornitore_key && (f.prodotti_trovati || 0) > 0
      && !FONTI_FISSE.includes(f.fornitore_key))
    .map((f) => {
      const listino = f.tipo === "listino";
      const data = dataIt(f.listino_data);
      return {
        chiave: f.fornitore_key,
        titolo: f.nome || f.fornitore_key,
        sottotitolo: listino
          ? `Listino${data ? ` del ${data}` : ""}: ${f.prodotti_trovati} articoli con prezzo dichiarato, nel confronto prezzi.`
          : `Catalogo con ${f.prodotti_trovati} prodotti.`,
        badge: listino ? "Listino" : "Catalogo",
        percorso: `prodotti/${f.fornitore_key}`,
      };
    });
}
