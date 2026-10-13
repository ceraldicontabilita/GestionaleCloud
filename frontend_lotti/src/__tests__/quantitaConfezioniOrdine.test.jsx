import {
  fornitoreUnicoOrdine,
  primoGruppoFornitoreOrdine,
  quantitaSuccessivaOrdine,
} from "../components/haccp/OrdiniView";

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

describe("fornitore delle righe da confermare", () => {
  test("considera equivalenti maiuscole, punti e spazi", () => {
    expect(fornitoreUnicoOrdine([
      { fornitore: "SAIMA S.p.a." },
      { fornitore: "SAIMA S.p.A" },
      { fornitore: " saima spa " },
    ])).toBe("SAIMA S.p.a.");
  });

  test("continua a bloccare fornitori realmente diversi o non assegnati", () => {
    expect(fornitoreUnicoOrdine([
      { fornitore: "SAIMA S.p.a." }, { fornitore: "MEPA Alimentari" },
    ])).toBe("");
    expect(fornitoreUnicoOrdine([{ fornitore: "DA ASSEGNARE" }])).toBe("");
  });

  test("una bozza mista prepara un fornitore e conserva le altre righe", () => {
    const gruppo = primoGruppoFornitoreOrdine([
      { prodotto_id: "m1", fornitore: "MEPA Alimentari" },
      { prodotto_id: "s1", fornitore: "SAIMA S.p.a." },
      { prodotto_id: "m2", fornitore: "mepa alimentari" },
    ]);
    expect(gruppo.fornitore).toBe("MEPA Alimentari");
    expect(gruppo.righe.map(r => r.prodotto_id)).toEqual(["m1", "m2"]);
    expect(gruppo.escluse.map(r => r.prodotto_id)).toEqual(["s1"]);
  });
});
