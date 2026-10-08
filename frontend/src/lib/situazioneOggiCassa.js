/** Aggrega i movimenti cassa di una giornata. Non inventa importi. */

export function dataOggiISO(now = new Date()) {
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function categoriaDi(movimento) {
  return String(movimento?.categoria || "").trim();
}

function segno(movimento) {
  const tipo = String(movimento?.tipo || "").toLowerCase();
  const importo = Number(movimento?.importo || 0);
  if (tipo === "uscita" || tipo === "avere") return -Math.abs(importo);
  if (tipo === "entrata" || tipo === "dare") return Math.abs(importo);
  return importo;
}

export function aggregaCassaGiorno(payload, giorno) {
  const movimenti = Array.isArray(payload)
    ? payload
    : payload?.movimenti || payload?.items || [];
  const delGiorno = movimenti.filter((riga) => String(riga?.data || "").slice(0, 10) === giorno);
  let corrispettivi = 0;
  let posVersoBanca = 0;
  let altreUscite = 0;
  let altreEntrate = 0;
  for (const riga of delGiorno) {
    const cat = categoriaDi(riga).toLowerCase();
    const valore = segno(riga);
    if (cat === "corrispettivi") corrispettivi += Math.abs(valore);
    else if (cat.includes("pos") && cat.includes("banca")) posVersoBanca += Math.abs(valore);
    else if (valore < 0) altreUscite += Math.abs(valore);
    else altreEntrate += Math.abs(valore);
  }
  return {
    giorno,
    corrispettivi,
    posVersoBanca,
    altreUscite,
    altreEntrate,
    movimenti: delGiorno.length,
    saldoGiorno: corrispettivi + altreEntrate - posVersoBanca - altreUscite,
    saldoRegistro: payload && !Array.isArray(payload) && payload.saldo != null
      ? Number(payload.saldo)
      : null,
  };
}
