import { quantitaSuccessivaOrdine } from "../components/haccp/OrdiniView";

describe("quantità delle confezioni negli ordini", () => {
  test("un prodotto catalogo aumenta e diminuisce solo per confezioni intere", () => {
    const secchiello = { prodotto_id: "cat_glf-002", quantita: 2, unita: "13 kg" };
    expect(quantitaSuccessivaOrdine(secchiello, 1)).toBe(3);
    expect(quantitaSuccessivaOrdine(secchiello, -1)).toBe(1);
  });

  test("un vecchio valore frazionario viene ricondotto a confezioni intere", () => {
    const secchiello = { prodotto_id: "cat_glf-002", quantita: 2.5, unita: "13 kg" };
    expect(quantitaSuccessivaOrdine(secchiello, 1)).toBe(3);
    expect(quantitaSuccessivaOrdine(secchiello, -1)).toBe(2);
  });

  test("le righe non provenienti dal catalogo possono mantenere mezze unità", () => {
    expect(quantitaSuccessivaOrdine({ prodotto_id: "sfuso", quantita: 1 }, -1)).toBe(0.5);
  });
});
