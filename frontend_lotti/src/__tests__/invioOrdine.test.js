import { codiceRigaOrdine, linkEmailOrdine, linkWhatsAppOrdine, testoOrdineFornitore } from "../utils/invioOrdine";

const ordine = { id: "abcdef12-ordine", fornitore: "Fornitore Uno" };
const righe = [
  { nome: "Farina", codice_articolo: "SAIMA 1069", codici: ["SAIMA 1069"], quantita: 2, unita: "kg", fornitore: "Fornitore Uno" },
  { nome: "Zucchero", quantita: 1, unita: "kg", fornitore: "Fornitore Uno" },
];

test("email e WhatsApp contengono le sole righe confermate del fornitore", () => {
  const testo = testoOrdineFornitore(ordine, righe);
  expect(testo).toContain("COD: SAIMA 1069 · Farina: 2 kg");
  expect(testo).toContain("Zucchero: 1 kg");
  expect(testo).toContain("ORD-ABCDEF12");
  const email = linkEmailOrdine("ordini@example.com", ordine, righe);
  expect(email).toMatch(/^mailto:ordini@example.com\?/);
  expect(decodeURIComponent(email)).toContain("COD: SAIMA 1069 · Farina: 2 kg");
  const whatsapp = linkWhatsAppOrdine("333 123 4567", ordine, righe);
  expect(whatsapp).toMatch(/^https:\/\/wa\.me\/393331234567\?/);
  expect(decodeURIComponent(whatsapp)).toContain("Zucchero: 1 kg");
});

test("usa il primo codice esplicito e non inventa un codice quando manca", () => {
  expect(codiceRigaOrdine({ codici: ["ELEN004"] })).toBe("ELEN004");
  expect(codiceRigaOrdine({ nome: "Senza codice", prodotto_id: "cat-interno" })).toBe("");
  expect(testoOrdineFornitore(ordine, [righe[1]])).not.toContain("COD:");
});

test("non apre un client senza destinatario", () => {
  expect(() => linkEmailOrdine("", ordine, righe)).toThrow("email");
  expect(() => linkWhatsAppOrdine("", ordine, righe)).toThrow("cellulare");
});
