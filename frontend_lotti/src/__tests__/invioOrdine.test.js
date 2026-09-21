import { linkEmailOrdine, linkWhatsAppOrdine, testoOrdineFornitore } from "../utils/invioOrdine";

const ordine = { id: "abcdef12-ordine", fornitore: "Fornitore Uno" };
const righe = [
  { nome: "Farina", quantita: 2, unita: "kg", fornitore: "Fornitore Uno" },
  { nome: "Zucchero", quantita: 1, unita: "kg", fornitore: "Fornitore Uno" },
];

test("email e WhatsApp contengono le sole righe confermate del fornitore", () => {
  const testo = testoOrdineFornitore(ordine, righe);
  expect(testo).toContain("Farina: 2 kg");
  expect(testo).toContain("Zucchero: 1 kg");
  expect(testo).toContain("ORD-ABCDEF12");
  const email = linkEmailOrdine("ordini@example.com", ordine, righe);
  expect(email).toMatch(/^mailto:ordini@example.com\?/);
  expect(decodeURIComponent(email)).toContain("Farina: 2 kg");
  const whatsapp = linkWhatsAppOrdine("333 123 4567", ordine, righe);
  expect(whatsapp).toMatch(/^https:\/\/wa\.me\/393331234567\?/);
  expect(decodeURIComponent(whatsapp)).toContain("Zucchero: 1 kg");
});

test("non apre un client senza destinatario", () => {
  expect(() => linkEmailOrdine("", ordine, righe)).toThrow("email");
  expect(() => linkWhatsAppOrdine("", ordine, righe)).toThrow("cellulare");
});
