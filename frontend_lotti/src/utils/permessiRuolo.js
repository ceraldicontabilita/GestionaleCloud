// Cosa può fare chi è davanti al tablet. La regola vive nel backend
// (app/lotti/servizi/ruoli.py), che la ricontrolla a ogni operazione: qui
// arriva al login (`operatore.profilo`) e serve solo a non mostrare comandi
// che risponderebbero 403. Il titolare, entrato dal Gestionale o col proprio
// PIN personale HR, può tutto.
import { isAdmin } from "../auth";
import { getTabletSession } from "./tabletSession";

export const RUOLO_TITOLARE = "amministratore";

export function profiloCorrente(sessione = getTabletSession(), admin = isAdmin()) {
  if (admin || sessione?.ruolo === RUOLO_TITOLARE) {
    return { ruolo: RUOLO_TITOLARE, ruolo_etichetta: "Titolare", reparti: [], permessi: null };
  }
  const p = sessione?.profilo || {};
  return {
    ruolo: p.ruolo || "operatore",
    ruolo_etichetta: p.ruolo_etichetta || "Operatore",
    reparti: Array.isArray(p.reparti) ? p.reparti : [],
    permessi: Array.isArray(p.permessi) ? p.permessi : [],
  };
}

// reparto: solo per ricette e produzione, che il caporeparto ha sui propri.
export function puo(permesso, reparto, profilo = profiloCorrente()) {
  if (profilo.ruolo === RUOLO_TITOLARE) return true;
  if (!profilo.permessi.includes(permesso)) return false;
  if (reparto === undefined) return true;
  return !!reparto && profilo.reparti.includes(String(reparto).toLowerCase());
}

export const MOTIVO_NON_PERMESSO = {
  haccp_registri: "Solo il responsabile HACCP o il titolare",
  haccp_anomalie: "Solo il responsabile HACCP o il titolare",
  haccp_conformita: "Solo il responsabile HACCP o il titolare",
  frigoriferi: "Solo il responsabile HACCP o il titolare",
  smaltimento: "Solo il caporeparto, il responsabile HACCP o il titolare",
  ricette: "Solo il caporeparto del reparto o il titolare",
  produzione: "Solo il caporeparto del reparto o il titolare",
};
