import { aggiungiAlCarrello, dataIt, differenza, euroPezzo, rigaCarrello } from "./confrontoFornitori";

const articolo = { chiave: "CRODINO|100ml|x48", nome: "CRODINO CL.10X48" };
const migliore = { fornitore: "DI COSMO S.R.L.", fornitore_id: "piva:01835050616", prezzo_pezzo: "0.4514",
  prezzo_fattura: "21.6700", per_cartone: true, unita_fattura: "CT" };
const altro = { fornitore: "SIRO", fornitore_id: "piva:1", prezzo_pezzo: "0.4525", prezzo_fattura: "21.7200",
  per_cartone: false, unita_fattura: "B4" };

test("date e prezzi all'italiana", () => {
  expect(dataIt("2026-08-26")).toBe("26/08/2026");
  expect(euroPezzo("0.4514")).toBe("€ 0,451");
  expect(euroPezzo("12.5")).toBe("€ 12,50");
});

test("differenza dal migliore solo se costa di piu'", () => {
  expect(differenza(altro, migliore)).toBe("+€ 0,001 al pezzo");
  expect(differenza(migliore, migliore)).toBe("");
});

test("il carrello ordina nell'unita' di fattura e somma le quantita'", () => {
  const riga = rigaCarrello(articolo, migliore);
  expect(riga).toMatchObject({ unita_misura: "cartone", fornitore: "DI COSMO S.R.L.", prezzo: 21.67, quantita: 1 });
  expect(rigaCarrello(articolo, altro).unita_misura).toBe("pz");
  const memoria = { v: {}, getItem(k) { return this.v[k] || null; }, setItem(k, x) { this.v[k] = x; } };
  aggiungiAlCarrello(riga, memoria);
  const items = aggiungiAlCarrello(riga, memoria);
  expect(items).toHaveLength(1);
  expect(items[0].quantita).toBe(2);
});
