import { messaggioMigliore, rigaCarrello, unitaOrdine, versoIlMigliore } from "../utils/confrontoFornitori";

const barone = {
  fornitore: "Barone Achille & figli srl", fornitore_id: "piva:01527580615", origine: "listino",
  prezzo_fattura: "3.6000", prezzo_pezzo: "0.3000", unita_vendita: "12 PZ", unita_fattura: "PZ",
  codice_articolo: "285SAL01", per_cartone: true,
};
const fiorentino = {
  fornitore: "F.lli Fiorentino Srl", fornitore_id: "piva:01234567890", origine: "fattura",
  prezzo_fattura: "0.3600", prezzo_pezzo: "0.3600", unita_fattura: "KG", per_cartone: false,
};

test("l'ordine si sposta sul fornitore che costa meno, con prezzo e unità sue", () => {
  const item = { id: "x", nome: "SALE FINO ITALKALI DA KG.1X12", fornitore: "F.lli Fiorentino Srl", prezzo: 0.36, unita_misura: "kg" };
  const esito = {
    trovato: true,
    articolo: { nome_standard: "Sale fino Italkali 1 kg × 12" },
    consiglio: { cambia: true, migliore: barone, attuale: fiorentino, risparmio_pezzo: "0.0600" },
  };
  const spostato = versoIlMigliore(item, esito);
  expect(spostato.cambiato).toBe(true);
  expect(spostato.item).toMatchObject({
    fornitore: "Barone Achille & figli srl", prezzo: 3.6, unita_misura: "12 pz",
    prezzo_fonte: "listino_fornitore", codici: ["285SAL01"], nome: "Sale fino Italkali 1 kg × 12",
    fornitore_proposto: "F.lli Fiorentino Srl",
  });
  expect(messaggioMigliore("Sale fino", spostato)).toMatch(/si ordina da Barone Achille & figli srl.*invece di F\.lli Fiorentino Srl/);
});

test("senza confronto la riga resta dov'era", () => {
  const item = { id: "y", nome: "EDAMER", fornitore: "Barone", prezzo: 4.59 };
  expect(versoIlMigliore(item, null)).toEqual({ item, cambiato: false });
  expect(versoIlMigliore(item, { consiglio: { cambia: false } }).cambiato).toBe(false);
});

test("unità d'ordine: listino come scritto, fattura come prima", () => {
  expect(unitaOrdine(barone)).toBe("12 pz");
  expect(unitaOrdine(fiorentino)).toBe("kg");
  expect(unitaOrdine({ per_cartone: true, unita_fattura: "C5" })).toBe("cartone");
  expect(rigaCarrello({ chiave: "k", nome: "SALE", nome_standard: "Sale fino" }, barone))
    .toMatchObject({ nome: "Sale fino", fornitore: "Barone Achille & figli srl", prezzo_fonte: "listino_fornitore" });
});
