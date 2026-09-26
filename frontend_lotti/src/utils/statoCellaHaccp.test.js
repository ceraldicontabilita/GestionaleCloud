import { statoCellaHaccp } from "./statoCellaHaccp";

describe("statoCellaHaccp", () => {
  test("conforme, non rilevato e da rilevare sono tre cose diverse", () => {
    const c = statoCellaHaccp({ temp: null, stato: "conforme", esito: "conforme", operatore: "Enzo" });
    const nr = statoCellaHaccp({ temp: null, non_rilevato: true, motivo: "nessuna lettura" });
    const dr = statoCellaHaccp({ temp: null, stato: "da_rilevare", operatore_nome: "Anna" });
    expect([c.stato, nr.stato, dr.stato]).toEqual(["conforme", "non_rilevato", "da_rilevare"]);
    expect(new Set([c.value, nr.value, dr.value]).size).toBe(3);
    expect(new Set([c.stampa, nr.stampa, dr.stampa]).size).toBe(3);
    expect(c.title).toContain("Enzo");
    expect(dr.title).toContain("Anna");
  });

  test("una temperatura vera non è uno stato", () => {
    expect(statoCellaHaccp({ temp: 3.2, stato: "conforme" })).toBeNull();
    expect(statoCellaHaccp(null)).toBeNull();
    expect(statoCellaHaccp(4)).toBeNull();
  });
});
