import { calcolaProduzione, scalaIngredienti } from "../components/haccp/gelati/calcoloProduzione";

test("5 kg di cioccolato con 1,5 kg recuperati richiedono dosi per 3,5 kg nuovi", () => {
  const calcolo = calcolaProduzione(5000, 1500, 1500);
  expect(calcolo).toEqual({ totale: 5000, recuperato: 1500, nuovo: 3500 });
  expect(scalaIngredienti({ Latte: 800, Cacao: 200 }, 1000, calcolo.nuovo)).toEqual([
    { n: "Latte", q: 2800 },
    { n: "Cacao", q: 700 },
  ]);
});

test("il calcolo non mostra più recuperato del peso finale o della giacenza", () => {
  expect(calcolaProduzione(5000, 6000, 6000).recuperato).toBe(5000);
  expect(calcolaProduzione(5000, 2000, 1500).recuperato).toBe(1500);
});
