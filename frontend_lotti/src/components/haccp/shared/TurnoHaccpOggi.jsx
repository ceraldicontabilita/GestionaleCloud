// Il turno HACCP di oggi, sopra i registri di frigoriferi e congelatori.
//
// Legge GET /haccp-auto/turno-oggi e offre le due azioni che fino al
// 02/10/2026 esistevano solo nel backend, senza nessun bottone:
//  - «Dichiaro conformi i controlli di oggi» (permesso haccp_conformita):
//    POST /haccp-auto/dichiara-conformi-oggi. Prima dice quante caselle
//    aperte verranno dichiarate, poi chiede conferma, poi mostra l'esito.
//    Il backend scrive stato=conforme e temp=null: nessun numero inventato,
//    e firma chi tocca il bottone (PIN o sessione del Gestionale).
//  - «Apri le caselle di oggi» (permesso haccp_registri), solo se un
//    apparecchio attivo non ha ancora la casella (aggiunto dopo le 07:00,
//    servizio spento al turno): POST /haccp-auto/apri-rilevazioni-oggi.
//
// Un errore del backend si mostra con le sue parole: 409 = controllo visivo
// non attivo nelle Impostazioni, 401 = nessuna firma verificata.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { CalendarCheck, ClipboardCheck, RefreshCw } from "lucide-react";
import { API } from "../../../utils/constants";
import { apiError } from "../../../utils/apiError";
import { conferma } from "../../../utils/conferma";
import { puo } from "../../../utils/permessiRuolo";

const SALVIA = "#5b7a6b";
const SALVIA_SCURA = "#3f5a4e";
const INCHIOSTRO = "#2a3329";
const CARD = "#fffefb";
const BORDO = "#e6e0d4";
const SMORZATO = "#6b7669";

const bottone = (pieno, occupato) => ({
  minHeight: 44, padding: "0 16px", borderRadius: 12, fontFamily: "inherit",
  fontSize: 14, fontWeight: 800, cursor: occupato ? "wait" : "pointer",
  opacity: occupato ? 0.6 : 1, display: "inline-flex", alignItems: "center", gap: 8,
  border: pieno ? "none" : `1.5px solid ${BORDO}`,
  background: pieno ? SALVIA : CARD, color: pieno ? "#fff" : SALVIA_SCURA,
});

function conta(n, singolare, plurale) {
  return `${n} ${n === 1 ? singolare : plurale}`;
}

export default function TurnoHaccpOggi({ onAggiornato }) {
  const [turno, setTurno] = useState(null);
  const [errore, setErrore] = useState("");
  const [occupato, setOccupato] = useState(null);
  const [esito, setEsito] = useState("");

  const carica = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/haccp-auto/turno-oggi`, { timeout: 15000 });
      setTurno(data || null);
      setErrore("");
    } catch (e) {
      setTurno(null);
      setErrore(apiError(e, "Turno di oggi non disponibile"));
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const aggiorna = async () => {
    await carica();
    if (typeof onAggiornato === "function") onAggiornato();
  };

  const dichiara = async () => {
    const aperte = turno?.quante_da_rilevare ?? 0;
    const daFirmare = turno?.da_firmare ?? 0;
    const ok = await conferma(
      `Confermi ${conta(aperte, "casella aperta", "caselle aperte")} e firmi ` +
      `${conta(daFirmare, "controllo già registrato", "controlli già registrati")} di oggi? ` +
      "Le caselle aperte diventano «conformi» senza inventare gradi. Le temperature già registrate, " +
      "comprese eventuali anomalie, non vengono modificate: si aggiunge soltanto la tua firma.",
      { titolo: "Controlli di oggi", ok: "Dichiaro conformi" },
    );
    if (!ok) return;
    setOccupato("dichiara");
    setEsito("");
    try {
      const { data } = await axios.post(`${API}/haccp-auto/dichiara-conformi-oggi`, null, { timeout: 30000 });
      const testo = `Confermate ${conta(data?.dichiarate ?? 0, "casella aperta", "caselle aperte")} e firmati ` +
        `${conta(data?.firmate ?? 0, "controllo registrato", "controlli registrati")}, da ${data?.firmato_da || "—"}`;
      setEsito(testo);
      toast.success(testo);
      await aggiorna();
    } catch (e) {
      toast.error(apiError(e, "Dichiarazione non registrata"));
    } finally {
      setOccupato(null);
    }
  };

  const apri = async () => {
    setOccupato("apri");
    setEsito("");
    try {
      const { data } = await axios.post(`${API}/haccp-auto/apri-rilevazioni-oggi`, null, { timeout: 30000 });
      const testo = `Aperte ${conta(data?.aperte ?? 0, "casella", "caselle")} di oggi`;
      setEsito(testo);
      toast.success(testo);
      await aggiorna();
    } catch (e) {
      toast.error(apiError(e, "Caselle non aperte"));
    } finally {
      setOccupato(null);
    }
  };

  const puoDichiarare = puo("haccp_conformita");
  const puoAprire = puo("haccp_registri");
  if (!puoDichiarare && !puoAprire) return null;

  const aperte = turno?.quante_da_rilevare ?? null;
  const rilevate = turno?.gia_rilevate ?? null;
  const daFirmare = turno?.da_firmare ?? 0;
  const giaFirmate = turno?.gia_firmate ?? 0;
  const senzaCasella = turno?.quante_senza_casella ?? 0;
  const controlloVisivo = turno?.controllo_visivo_attivo !== false;

  return (
    <section data-testid="turno-haccp-oggi" aria-label="Turno HACCP di oggi" style={{
      background: CARD, border: `1px solid ${BORDO}`, borderRadius: 14, padding: 14,
      display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center",
    }}>
      <div style={{ flex: "1 1 240px", minWidth: 0, color: INCHIOSTRO }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 15, fontWeight: 800 }}>
          <ClipboardCheck size={18} color={SALVIA} aria-hidden="true" /> Controlli di oggi
        </div>
        <div data-testid="turno-haccp-riepilogo" style={{ fontSize: 13.5, color: SMORZATO, marginTop: 4, lineHeight: 1.5 }}>
          {errore ? errore : turno === null ? "Lettura in corso…" : (
            <>
              {conta(aperte, "casella aperta", "caselle aperte")} da dichiarare, {conta(rilevate, "già rilevata", "già rilevate")}
              {daFirmare > 0 ? ` · ${conta(daFirmare, "controllo da firmare", "controlli da firmare")}` : ""}
              {giaFirmate > 0 ? ` · ${conta(giaFirmate, "controllo già firmato", "controlli già firmati")}` : ""}
              {senzaCasella > 0 ? ` · ${conta(senzaCasella, "apparecchio", "apparecchi")} senza casella: ${(turno.senza_casella || []).join(", ")}` : ""}
              {!controlloVisivo ? " · Il controllo visivo del responsabile non è attivo nelle Impostazioni." : ""}
            </>
          )}
          {esito ? <div style={{ color: SALVIA_SCURA, fontWeight: 700, marginTop: 2 }}>{esito}</div> : null}
        </div>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {puoAprire && senzaCasella > 0 ? (
          <button type="button" onClick={apri} disabled={!!occupato} style={bottone(false, occupato === "apri")}>
            <CalendarCheck size={16} aria-hidden="true" /> Apri le caselle di oggi
          </button>
        ) : null}
        {puoDichiarare && controlloVisivo ? (
          <button type="button" onClick={dichiara} disabled={!!occupato || !(aperte || daFirmare)} style={bottone(true, occupato === "dichiara")}
            title={(aperte || daFirmare) ? `${aperte} caselle da chiudere, ${daFirmare} controlli da firmare` : "Tutti i controlli di oggi sono già firmati"}>
            <ClipboardCheck size={16} aria-hidden="true" /> Dichiaro conformi i controlli di oggi
          </button>
        ) : null}
        <button type="button" onClick={carica} aria-label="Rileggi il turno di oggi" style={{ ...bottone(false, false), minWidth: 44, padding: 0, justifyContent: "center" }}>
          <RefreshCw size={16} aria-hidden="true" />
        </button>
      </div>
    </section>
  );
}
