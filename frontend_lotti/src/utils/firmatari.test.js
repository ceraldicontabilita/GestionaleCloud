import { firmatariDelMese, testoFirmatari } from "./firmatari";

test("solo chi ha firmato con PIN o sessione verificata", () => {
  const schede = {
    1: { temperature: { 9: { 1: { temp: 3, operatore: "Pocci Salvatore", firma_verificata: true },
                             2: { temp: 4, operatore: "Scritto a mano", firma_verificata: false } } } },
    2: { temperature: { 9: { 3: { temp: null, non_rilevato: true } } } },
  };
  expect(firmatariDelMese(schede, 9)).toEqual(["Pocci Salvatore"]);
  expect(testoFirmatari({}, 9)).toBe("nessuna firma verificata nel mese");
});
