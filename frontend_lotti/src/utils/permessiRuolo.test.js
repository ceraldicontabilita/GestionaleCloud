import { profiloCorrente, puo } from "./permessiRuolo";

const sessione = (profilo) => ({ dipendente_id: "hr-1", nome: "Prova", ruolo: "operatore", profilo });

test("il titolare può tutto", () => {
  const p = profiloCorrente(null, true);
  expect(puo("ricette", "bar", p)).toBe(true);
  expect(puo("smaltimento", undefined, p)).toBe(true);
});

test("un operatore senza profilo non ha permessi", () => {
  const p = profiloCorrente(sessione(undefined), false);
  expect(p.ruolo).toBe("operatore");
  expect(puo("smaltimento", undefined, p)).toBe(false);
  expect(puo("haccp_registri", undefined, p)).toBe(false);
});

test("il caporeparto consulta le ricette anche con vecchi permessi in cache", () => {
  const p = profiloCorrente(sessione({ ruolo: "caporeparto", reparti: ["pasticceria"], permessi: ["produzione", "ricette", "smaltimento"] }), false);
  expect(puo("ricette", "pasticceria", p)).toBe(false);
  expect(puo("ricette", "Pasticceria", p)).toBe(false);
  expect(puo("ricette", undefined, p)).toBe(false);
  expect(puo("produzione", "pasticceria", p)).toBe(true);
  expect(puo("produzione", "rosticceria", p)).toBe(false);
  expect(puo("ricette", "rosticceria", p)).toBe(false);
  expect(puo("ricette", "", p)).toBe(false);
  expect(puo("smaltimento", undefined, p)).toBe(true);
  expect(puo("haccp_registri", undefined, p)).toBe(false);
});

test("il responsabile HACCP gestisce registri e anomalie, non le ricette", () => {
  const p = profiloCorrente(sessione({ ruolo: "haccp", reparti: [], permessi: ["frigoriferi", "haccp_anomalie", "haccp_conformita", "haccp_registri", "smaltimento"] }), false);
  expect(puo("haccp_registri", undefined, p)).toBe(true);
  expect(puo("frigoriferi", undefined, p)).toBe(true);
  expect(puo("ricette", "pasticceria", p)).toBe(false);
});
