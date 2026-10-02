import { rangeConformeHaccp, statoCellaHaccp } from "./statoCellaHaccp";

describe("statoCellaHaccp", () => {
  test("conforme, non rilevato e da rilevare sono tre cose diverse", () => {
    const c = statoCellaHaccp(
      { temp: null, stato: "conforme", esito: "conforme", operatore: "Enzo" },
      { min: -22, max: -18 },
    );
    const nr = statoCellaHaccp({ temp: null, non_rilevato: true, motivo: "nessuna lettura" });
    const dr = statoCellaHaccp({ temp: null, stato: "da_rilevare", operatore_nome: "Anna" });
    expect([c.stato, nr.stato, dr.stato]).toEqual(["conforme", "non_rilevato", "da_rilevare"]);
    expect(new Set([c.value, nr.value, dr.value]).size).toBe(3);
    expect(new Set([c.stampa, nr.stampa, dr.stampa]).size).toBe(3);
    expect(c.title).toContain("Enzo");
    expect(c.title).toContain("Non è una misurazione numerica");
    expect(c.value).toBe("−22…−18°");
    expect(c.stampa).toBe("−22…−18 °C");
    expect(dr.title).toContain("Anna");
  });

  test("mostra anche il range conforme dei frigoriferi", () => {
    const c = statoCellaHaccp({ temp: null, stato: "conforme" }, { min: 0, max: 4 });
    expect(c.value).toBe("0…+4°");
    expect(c.stampa).toBe("0…+4 °C");
  });

  test("il range può rappresentare una lettura numerica conforme senza perderla", () => {
    const c = rangeConformeHaccp({ min: -22, max: -18 }, { valoreRegistrato: -19.4 });
    expect(c.value).toBe("−22…−18°");
    expect(c.title).toContain("Lettura registrata: -19.4°C");
    expect(c.title).not.toContain("Non è una misurazione numerica");
  });

  test("una temperatura vera non è uno stato", () => {
    expect(statoCellaHaccp({ temp: 3.2, stato: "conforme" })).toBeNull();
    expect(statoCellaHaccp(null)).toBeNull();
    expect(statoCellaHaccp(4)).toBeNull();
  });
});
