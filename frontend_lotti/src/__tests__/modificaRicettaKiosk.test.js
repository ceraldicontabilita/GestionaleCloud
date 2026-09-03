const { creaBozzaRicetta, payloadRicettaDaBozza } = require("../components/haccp/tablet/ModificaRicettaKiosk");

describe("modifica rapida ricetta dal tablet", () => {
  test("legge correttamente anche le unita archiviate come unita_misura", () => {
    const bozza = creaBozzaRicetta({
      nome: "Bollino",
      ingredienti_dettaglio: [{ nome: "Farina", quantita: 500, unita_misura: "g" }],
      procedimento_testo: "Impastare.",
    });

    expect(bozza.ingredienti).toEqual([{ nome: "Farina", quantita: 500, unita: "g" }]);
    expect(bozza.procedimento).toBe("Impastare.");
  });

  test("genera un salvataggio completo senza perdere foto e componenti", () => {
    const payload = payloadRicettaDaBozza({
      nome: "Bollino uova e stracciatella",
      reparto: "rosticceria",
      porzioni: "12",
      metodo_conservazione: "frigo",
      ingredienti: [{ nome: "Farina", quantita: "500,5", unita: "g" }],
      allergeni: "Glutine, Uova",
      procedimento: "Impastare e cuocere.",
      note: "Servire caldo",
    }, { foto_url: "/api/foto/bollino", componenti: [{ ref_id: "x" }] });

    expect(payload.porzioni).toBe(12);
    expect(payload.ingredienti_dettaglio[0]).toEqual({ nome: "Farina", quantita: 500.5, unita_misura: "g" });
    expect(payload.allergeni).toEqual(["Glutine", "Uova"]);
    expect(payload.allergeni_confermati).toBe(false);
    expect(payload.procedimento_testo).toBe("Impastare e cuocere.");
    expect(payload.foto_url).toBe("/api/foto/bollino");
    expect(payload.componenti).toEqual([{ ref_id: "x" }]);
  });

  test("marca gli allergeni come manuali solo dopo una conferma esplicita", () => {
    const payload = payloadRicettaDaBozza({
      nome: "Crema",
      reparto: "pasticceria",
      porzioni: 1,
      ingredienti: [{ nome: "Latte", quantita: 500, unita: "g" }],
      allergeni: "Latte",
    }, {}, true);

    expect(payload.allergeni).toEqual(["Latte"]);
    expect(payload.allergeni_confermati).toBe(true);
  });
});
