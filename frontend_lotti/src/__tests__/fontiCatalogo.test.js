import { carteFontiCatalogo } from "../utils/fontiCatalogo";

describe("card delle fonti catalogo nella Home", () => {
  it("mostra il listino Barone con data gg/mm/aaaa e link alla sua scheda", () => {
    const [c] = carteFontiCatalogo([
      { fornitore_key: "barone", nome: "Barone Achille & figli srl", tipo: "listino",
        listino_data: "2026-09-28", prodotti_trovati: 4209 },
    ]);
    expect(c.titolo).toBe("Barone Achille & figli srl");
    expect(c.badge).toBe("Listino");
    expect(c.sottotitolo).toContain("28/09/2026");
    expect(c.percorso).toBe("prodotti/barone");
  });

  it("non ripete le tre card storiche e salta le fonti senza prodotti", () => {
    expect(carteFontiCatalogo([
      { fornitore_key: "saima", nome: "SAIMA", prodotti_trovati: 10 },
      { fornitore_key: "vuota", nome: "Vuota", prodotti_trovati: 0 },
    ])).toEqual([]);
  });

  it("una risposta non valida non rompe la Home", () => {
    expect(carteFontiCatalogo(null)).toEqual([]);
    expect(carteFontiCatalogo({ errore: true })).toEqual([]);
  });
});
