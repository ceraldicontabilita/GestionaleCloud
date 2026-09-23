import { aggregaCassaGiorno } from "./situazioneOggiCassa";

test("aggrega solo la giornata chiesta e non inventa importi", () => {
  const out = aggregaCassaGiorno({
    saldo: 900,
    movimenti: [
      { data: "2026-09-23", tipo: "entrata", categoria: "Corrispettivi", importo: 100 },
      { data: "2026-09-23", tipo: "uscita", categoria: "POS Verso Banca", importo: 30 },
      { data: "2026-09-23", tipo: "uscita", categoria: "Fatture", importo: 10 },
      { data: "2026-09-22", tipo: "entrata", categoria: "Corrispettivi", importo: 999 },
    ],
  }, "2026-09-23");
  expect(out.corrispettivi).toBe(100);
  expect(out.posVersoBanca).toBe(30);
  expect(out.altreUscite).toBe(10);
  expect(out.movimenti).toBe(3);
  expect(out.saldoGiorno).toBe(60);
  expect(out.saldoRegistro).toBe(900);
});

test("lista vuota resta a zero", () => {
  const out = aggregaCassaGiorno({ movimenti: [] }, "2026-09-23");
  expect(out.corrispettivi).toBe(0);
  expect(out.movimenti).toBe(0);
  expect(out.saldoRegistro).toBe(null);
});
