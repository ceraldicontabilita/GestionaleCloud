const DIMISSIONI_CODE = "DIP_DIMISSIONI_RICEVUTE";

const testoAlert = (alert) => String(alert?.dettaglio || alert?.messaggio || "");

const dataDaTesto = (testo, etichetta) => {
  const match = testo.match(new RegExp(`${etichetta}\\s+(\\d{4}-\\d{2}-\\d{2})`, "i"));
  return match?.[1] || "";
};

export const isAlertDimissioni = (alert) =>
  alert?.codice === DIMISSIONI_CODE || /dimissioni telematiche ricevute/i.test(testoAlert(alert));

export const datiDimissioniAlert = (alert) => {
  const testo = testoAlert(alert);
  const extra = alert?.extra && typeof alert.extra === "object" ? alert.extra : {};
  const nome = extra.dipendente || testo.match(/ricevute per\s+(.+?):\s*decorrenza/i)?.[1]?.trim() || "Dipendente";
  const decorrenza = extra.data_decorrenza || dataDaTesto(testo, "decorrenza");
  const scadenzaUnilav = extra.scadenza_unilav || dataDaTesto(testo, "UNILAV di cessazione entro il");
  return { nome, decorrenza, scadenzaUnilav, testo };
};

const dataOrdinamento = (alert) => {
  if (isAlertDimissioni(alert)) return datiDimissioniAlert(alert).decorrenza;
  return String(alert?.created_at || "").slice(0, 10);
};

export const ordinaAlertDashboard = (alerts = []) =>
  alerts
    .map((alert, indice) => ({ alert, indice, data: dataOrdinamento(alert) }))
    .sort((a, b) => b.data.localeCompare(a.data) || a.indice - b.indice)
    .map(({ alert }) => alert);

