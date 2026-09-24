/**
 * GC-02h — registrazioni HACCP in archivio senza firma verificata.
 *
 * Stessa regola di `app/lotti/servizi/haccp_attendibilita.py::e_non_attendibile`:
 * una casella e' «n.a.» se il documento la elenca in `non_attendibili.celle`
 * e il valore di oggi non porta `firma_verificata: true` (una rilevazione
 * firmata successiva la sostituisce). Il valore originale resta nel sistema:
 * qui si decide solo come mostrarlo.
 *
 * Coordinate: temperature [mese, giorno]; schede sanificazione [area, giorno]
 * (valore = voce `firme[area][giorno]`); apparecchi [campo, numero, "mese-giorno"].
 */

export const LEGENDA_NA =
  "n.a. = valore in archivio senza firma verificata, non attendibile (conservato nel sistema)";

const norm = (x) => {
  const t = String(x ?? "").trim();
  return /^\d+$/.test(t) ? String(Number(t)) : t;
};

export const firmata = (valore) =>
  Boolean(valore && typeof valore === "object" && valore.firma_verificata === true);

export function eNonAttendibile(doc, coordinate, valoreAttuale) {
  if (firmata(valoreAttuale)) return false;
  const celle = doc?.non_attendibili?.celle;
  if (!celle || typeof celle !== "object") return false;
  if (coordinate.length === 3) {
    const [campo, numero, mg] = coordinate;
    const perNumero = celle[campo];
    if (!perNumero || typeof perNumero !== "object") return false;
    const chiave = Object.keys(perNumero).find((k) => norm(k) === norm(numero));
    return chiave !== undefined && (perNumero[chiave] || []).map(String).includes(String(mg));
  }
  const [prima, giorno] = coordinate;
  const chiave = Object.keys(celle).find((k) => norm(k) === norm(prima));
  if (chiave === undefined || !Array.isArray(celle[chiave])) return false;
  return celle[chiave].some((g) => norm(g) === norm(giorno));
}

/** Testo del valore originale, per il title della casella «n.a.». */
export function valoreOriginale(valore) {
  if (valore && typeof valore === "object") {
    if (valore.temp !== undefined && valore.temp !== null) return `${valore.temp}°C`;
    if (valore.is_manutenzione) return "manutenzione";
    if (valore.is_non_usato) return "non usato";
    if (valore.is_sanificazione) return "sanificazione";
    if ("eseguita" in valore) return valore.eseguita ? "eseguita" : "non eseguita";
    if (valore.valore) return String(valore.valore);
    return "registrazione";
  }
  if (typeof valore === "number") return `${valore}°C`;
  return String(valore ?? "");
}

export const titoloNa = (valore) =>
  `Non attendibile: valore in archivio senza firma verificata (${valoreOriginale(valore)}). Conservato nel sistema.`;

/** Classi della casella «n.a.»: neutra calda, bordo tratteggiato, mai solo colore. */
export const CLASSE_NA = "bg-[#faf7f0] text-[#6b6358] border border-dashed border-[#b8ad99] italic";

/** Stile inline equivalente per le stampe. */
export const STILE_NA_STAMPA = "background:#faf7f0;color:#6b6358;border:1px dashed #b8ad99;font-style:italic;";
