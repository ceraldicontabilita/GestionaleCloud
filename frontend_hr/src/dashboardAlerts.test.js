import { describe, expect, it } from "vitest";
import { datiDimissioniAlert, isAlertDimissioni, ordinaAlertDashboard } from "./dashboardAlerts";

const dimissioni = (nome, decorrenza, scadenza) => ({
  codice: "DIP_DIMISSIONI_RICEVUTE",
  dettaglio: `Dimissioni telematiche ricevute per ${nome}: decorrenza ${decorrenza}, modulo trasmesso il 2024-01-01.\nUNILAV di cessazione entro il ${scadenza} (-1 giorni) tramite il consulente del lavoro. Adempimenti: testo lungo`,
});

describe("alert dimissioni nel pannello HR", () => {
  it("estrae solo i dati necessari al riepilogo", () => {
    const alert = dimissioni("Ceraldi Vincenzo", "2024-01-05", "2024-01-10");
    expect(isAlertDimissioni(alert)).toBe(true);
    expect(datiDimissioniAlert(alert)).toMatchObject({
      nome: "Ceraldi Vincenzo",
      decorrenza: "2024-01-05",
      scadenzaUnilav: "2024-01-10",
    });
  });

  it("preferisce i campi strutturati quando presenti", () => {
    const alert = {
      ...dimissioni("Nome nel testo", "2020-01-01", "2020-01-06"),
      extra: { dipendente: "Nome corretto", data_decorrenza: "2026-11-01", scadenza_unilav: "2026-11-06" },
    };
    expect(datiDimissioniAlert(alert)).toMatchObject({
      nome: "Nome corretto",
      decorrenza: "2026-11-01",
      scadenzaUnilav: "2026-11-06",
    });
  });

  it("ordina le dimissioni per decorrenza, dalla più recente", () => {
    const alerts = [
      dimissioni("Pocci Salvatore", "2020-07-20", "2020-07-25"),
      dimissioni("Russo Carmine", "2026-11-01", "2026-11-06"),
      dimissioni("Ceraldi Valerio", "2024-01-04", "2024-01-09"),
      dimissioni("Ceraldi Vincenzo", "2024-01-05", "2024-01-10"),
    ];
    expect(ordinaAlertDashboard(alerts).map(a => datiDimissioniAlert(a).nome)).toEqual([
      "Russo Carmine", "Ceraldi Vincenzo", "Ceraldi Valerio", "Pocci Salvatore",
    ]);
  });
});
