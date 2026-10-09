const { numeroTastierinoValido } = require("../components/haccp/shared/TouchNumberInput");

describe("tastierino numerico per il laboratorio", () => {
  test("accetta una quantità compresa nel limite disponibile", () => {
    expect(numeroTastierinoValido("900", 1, 1750)).toEqual({ valido: true, messaggio: "" });
  });

  test("non permette di recuperare più gelato della giacenza", () => {
    const risultato = numeroTastierinoValido("1800", 1, 1750);
    expect(risultato.valido).toBe(false);
    expect(risultato.messaggio).toContain("1750 g");
  });

  test("rifiuta campi vuoti e quantità inferiori al minimo", () => {
    expect(numeroTastierinoValido("", 1).valido).toBe(false);
    expect(numeroTastierinoValido("0", 1).valido).toBe(false);
  });
});
