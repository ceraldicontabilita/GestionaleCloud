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

export function statoCellaHaccp(record) {
  if (!record || typeof record !== "object") return null;
  if (record.temp !== undefined && record.temp !== null) return null;
  if (record.stato === STATO_CONFORME || record.esito === STATO_CONFORME) {
    return {
      value: "C",
      stampa: "C",
      className: "bg-[#e6efe9] text-[#3d8168] font-bold",
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
  "C = conforme (controllo visivo firmato dal responsabile) · N.R. = non rilevato · D.R. / … = da rilevare";
