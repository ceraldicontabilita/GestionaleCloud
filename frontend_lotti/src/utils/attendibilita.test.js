import { eNonAttendibile, firmata, titoloNa, valoreOriginale } from "./attendibilita";

const temp = { non_attendibili: { celle: { 3: ["1", "2"] } } };
const scheda = { non_attendibili: { celle: { Pavimentazione: ["4"] } } };
const apparecchi = {
  non_attendibili: { celle: { registrazioni_frigoriferi: { 1: ["3-5"] } } },
};

test("casella segnata senza firma: n.a.", () => {
  expect(eNonAttendibile(temp, [3, 1], 2.7)).toBe(true);
  expect(eNonAttendibile(temp, ["03", "02"], { temp: 3.1 })).toBe(true);
  expect(eNonAttendibile(scheda, ["Pavimentazione", 4], undefined)).toBe(true);
  expect(eNonAttendibile(apparecchi, ["registrazioni_frigoriferi", 1, "3-5"], { eseguita: true })).toBe(true);
});

test("casella non segnata o documento senza segno: attendibile", () => {
  expect(eNonAttendibile(temp, [3, 9], 2.7)).toBe(false);
  expect(eNonAttendibile({}, [3, 1], 2.7)).toBe(false);
  expect(eNonAttendibile(null, [3, 1], 2.7)).toBe(false);
  expect(eNonAttendibile(apparecchi, ["registrazioni_congelatori", 1, "3-5"], {})).toBe(false);
});

test("una rilevazione firmata successiva sostituisce il segno", () => {
  expect(eNonAttendibile(temp, [3, 1], { temp: 3.0, firma_verificata: true })).toBe(false);
  expect(eNonAttendibile(scheda, ["Pavimentazione", 4], { firma_verificata: true })).toBe(false);
  // solo il booleano vale come firma
  expect(firmata({ firma_verificata: "true" })).toBe(false);
});

test("il title conserva il valore originale", () => {
  expect(valoreOriginale(2.7)).toBe("2.7°C");
  expect(valoreOriginale({ is_manutenzione: true, temp: null })).toBe("manutenzione");
  expect(titoloNa("X")).toContain("(X)");
});
