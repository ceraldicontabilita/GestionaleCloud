// Stato di una casella del registro temperature quando NON c'è un numero.
//
// Fino al 26/09/2026 «conforme» (controllo visivo firmato dal responsabile),
// «non rilevato» (giorno passato senza lettura, dichiarato) e «da rilevare»
// (casella aperta dal turno, in attesa) comparivano tutti come «-» «Nessun
// dato», a schermo e in stampa: davanti a un'ispezione un controllo firmato e
// una dimenticanza erano indistinguibili.
//
// Ritorna null se la casella ha una temperatura (la mostra chi chiama) o se
// non è uno di questi tre stati.

export const STATO_CONFORME = "conforme";
export const STATO_DA_RILEVARE = "da_rilevare";

function formattaLimiteTemperatura(value, mostraPiu = false) {
  const numero = Number(value);
  if (!Number.isFinite(numero)) return null;
  if (numero < 0) return `−${Math.abs(numero)}`;
  if (mostraPiu && numero > 0) return `+${numero}`;
  return String(numero);
}

function formattaRangeTemperatura(range) {
  const minimo = formattaLimiteTemperatura(range?.min);
  const massimo = formattaLimiteTemperatura(range?.max, true);
  if (minimo === null || massimo === null) return null;
  return `${minimo}…${massimo}`;
}

export function rangeConformeHaccp(range, { operatore, valoreRegistrato } = {}) {
  const rangeFormattato = formattaRangeTemperatura(range);
  if (!rangeFormattato) return null;
  const haValoreRegistrato = valoreRegistrato !== undefined && valoreRegistrato !== null;
  return {
    value: `${rangeFormattato}°`,
    stampa: `${rangeFormattato} °C`,
    className: "bg-[#e6efe9] text-[#3d8168] font-bold text-[9px] whitespace-nowrap",
    stile: "background:#e6efe9;color:#3d8168;font-weight:bold;",
    title: `Range conforme dichiarato: ${rangeFormattato} °C. ${haValoreRegistrato ? `Lettura registrata: ${valoreRegistrato}°C` : "Non è una misurazione numerica"}${operatore ? `, firmato da ${operatore}` : ""}`,
    stato: "conforme",
  };
}

export function temperaturaNumericaHaccp(valore, { operatore } = {}) {
  const numero = Number(valore);
  if (!Number.isFinite(numero)) return null;
  const formattato = formattaLimiteTemperatura(numero);
  return {
    value: `${formattato}°`,
    stampa: `${formattato} °C`,
    className: "bg-[#e6efe9] text-[#3d8168] font-bold text-[10px] whitespace-nowrap",
    stile: "background:#e6efe9;color:#3d8168;font-weight:bold;",
    title: `Temperatura rilevata: ${formattato}°C${operatore ? `, firmata da ${operatore}` : ""}`,
    stato: "temperatura",
  };
}

export function statoCellaHaccp(record, range = null) {
  if (!record || typeof record !== "object") return null;
  if (record.temp !== undefined && record.temp !== null) return null;
  if (record.stato === STATO_CONFORME || record.esito === STATO_CONFORME) {
    const rangeConforme = rangeConformeHaccp(range, { operatore: record.operatore });
    if (rangeConforme) return rangeConforme;
    return {
      value: "Conforme",
      stampa: "Conforme",
      className: "bg-[#e6efe9] text-[#3d8168] font-bold text-[9px] whitespace-nowrap",
      stile: "background:#e6efe9;color:#3d8168;font-weight:bold;",
      title: `Conforme: controllo visivo del responsabile${record.operatore ? `, firmato da ${record.operatore}` : ""}`,
      stato: "conforme",
    };
  }
  if (record.non_rilevato) {
    return {
      value: "N.R.",
      stampa: "N.R.",
      className: "bg-[#f6ebe0] text-[#9a6a32] font-bold text-[10px]",
      stile: "background:#f6ebe0;color:#9a6a32;font-weight:bold;",
      title: `Non rilevato${record.motivo ? `: ${record.motivo}` : ""}`,
      stato: "non_rilevato",
    };
  }
  if (record.stato === STATO_DA_RILEVARE) {
    return {
      value: "…",
      stampa: "D.R.",
      className: "bg-[#faf7f0] text-[#8a6f47] border border-dashed border-[#c4894a]",
      stile: "color:#8a6f47;",
      title: `Da rilevare${record.operatore_nome ? `: tocca a ${record.operatore_nome}` : ""}`,
      stato: "da_rilevare",
    };
  }
  return null;
}

export const LEGENDA_STATI_HACCP =
  "Intervallo in cella = range conforme dichiarato (non misura numerica) · N.R. = non rilevato · D.R. / … = da rilevare";
