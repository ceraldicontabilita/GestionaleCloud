const { opzioniDestinazione } = require("../components/haccp/tablet/registraLotto/SelettorePosizione");

describe("destinazione lotto in un solo tocco", () => {
  test("usa solo apparecchi reali e non inventa ripiani o posizioni", () => {
    const opzioni = opzioniDestinazione(
      "pasticceria",
      ["Frigorifero laboratorio"],
      ["Abbattitore principale"],
    );
    expect(opzioni.map((o) => [o.id, o.nome])).toEqual([
      ["banco", ""],
      ["frigo", "Frigorifero laboratorio"],
      ["abbattitore", "Abbattitore principale"],
    ]);
  });

  test("il bar non propone il banco delle produzioni", () => {
    expect(opzioniDestinazione("bar", ["Frigo bar"], []).map((o) => o.id)).toEqual(["frigo"]);
  });
});
