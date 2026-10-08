import { useEffect, useState } from "react";
import { saveToken, saveRuolo, setGateOk, prendiPaginaRichiesta } from "../../auth";
import * as authLotti from "../../auth";
import axios from "axios";
import { LayoutDashboard, Lock, LogOut, Thermometer, CalendarClock, ShieldCheck } from "lucide-react";
import { cambiaOperatore } from "./tablet/BarraReparto";
import { apiError } from "../../utils/apiError";
import { allineaSessioneTitolare, getTabletSession, moveTabletSessionTo, repartiAmmessi, saveTabletSession, sessioneTitolareAttiva } from "../../utils/tabletSession";
import { avviaPollingVisibile } from "../../utils/visiblePolling";

const API = process.env.REACT_APP_LOTTI_BACKEND_URL + "/api";

// Card del tablet.
// REGOLA ENZO 25/07/2026: «il dipendente deve solo produrre e vedere le
// ricette, tutto il resto lo guardo io e lo utilizzo io». Le card restano
// tutte visibili; quelle marcate `soloAdmin` si aprono solo al titolare. Il
// titolare si riconosce dalla sessione del Gestionale (/auth/session) oppure
// dal proprio PIN personale collegato alla scheda HR, che conserva il ruolo
// amministratore. Il PIN amministratore centrale si usa solo nel Gestionale e
// non e' accettato dal tablet. Le card di reparto chiedono il PIN personale:
// identifica chi firma HACCP e produzioni.
const REPARTI = [
  { id: "pasticceria", label: "Pasticceria", emoji: "🍰", grad: "linear-gradient(135deg,#fb923c,#ea580c)", shadow: "rgba(234,88,12,.5)" },
  { id: "rosticceria", label: "Rosticceria", emoji: "🥙", grad: "linear-gradient(135deg,#86efac,#22c55e)", shadow: "rgba(34,197,94,.5)" },
  { id: "bar", label: "Bar", emoji: "☕", grad: "linear-gradient(135deg,#b45309,#78350f)", shadow: "rgba(120,53,15,.5)" },
  { id: "vendita", label: "Produzioni al banco", emoji: "🧾", grad: "linear-gradient(135deg,#5b7a6b,#3f5a4e)", shadow: "rgba(63,90,78,.5)" },
  { id: "ricette", label: "Ricette", emoji: "📖", grad: "linear-gradient(135deg,#c4894a,#9c6a32)", shadow: "rgba(156,106,50,.5)" },
  { id: "magazzino", label: "Magazzino", emoji: "📦", grad: "linear-gradient(135deg,#6f583a,#4a3f33)", shadow: "rgba(74,63,51,.5)" },
  { id: "lavagna", label: "Lavagna richieste", emoji: "📺", grad: "linear-gradient(135deg,#8a6f47,#6f583a)", shadow: "rgba(111,88,58,.5)" },
  { id: "ordini", label: "Ordini", emoji: "🛒", grad: "linear-gradient(135deg,#6f9180,#4f6d5f)", shadow: "rgba(79,109,95,.5)", soloAdmin: true },
  // Registri, anomalie, conformità e apparecchi: si entra col PIN personale,
  // e la pagina si apre solo al responsabile HACCP (ruolo sulla scheda HR).
  { id: "haccp", label: "Registri HACCP", icona: ShieldCheck, grad: "linear-gradient(135deg,#5b7a6b,#2f4a3e)", shadow: "rgba(47,74,62,.5)", etichetta: "Responsabile HACCP" },
];

// Stato del giorno sotto l'orologio, solo con una persona identificata (senza
// token le API rispondono 401). Un dato che non arriva si dice, non diventa 0.
function StatoGiorno({ attivo }) {
  const [stato, setStato] = useState(null);
  useEffect(() => {
    if (!attivo) return undefined;
    let vivo = true;
    const leggi = async () => {
      const [turno, scadenze] = await Promise.allSettled([
        axios.get(`${API}/haccp-auto/turno-oggi`, { timeout: 15000 }),
        axios.get(`${API}/supervisor/lotti-in-scadenza`, { params: { giorni: 2, limit: 1 }, timeout: 15000 }),
      ]);
      if (!vivo) return;
      setStato({
        daRilevare: turno.status === "fulfilled" ? turno.value.data?.quante_da_rilevare ?? null : null,
        inScadenza: scadenze.status === "fulfilled" ? scadenze.value.data?.totale ?? null : null,
      });
    };
    leggi();
    const fermaPolling = avviaPollingVisibile(leggi, 5 * 60 * 1000);
    return () => { vivo = false; fermaPolling(); };
  }, [attivo]);
  if (!attivo || !stato) return null;
  const nd = "dato non disponibile";
  const voce = { display: "inline-flex", alignItems: "center", gap: 6, background: "rgba(255,255,255,.08)", border: "1px solid #3a4a40", borderRadius: 12, padding: "8px 12px", color: "#e6e0d4", fontSize: 14, fontWeight: 700 };
  return (
    <div data-testid="stato-giorno" style={{ display: "flex", gap: 10, flexWrap: "wrap", justifyContent: "center", marginTop: -28, marginBottom: 32 }}>
      <span style={voce}><Thermometer size={16} aria-hidden="true" /> Temperature da rilevare: {stato.daRilevare ?? nd}</span>
      <span style={voce}><CalendarClock size={16} aria-hidden="true" /> Lotti in scadenza entro 2 giorni: {stato.inScadenza ?? nd}</span>
    </div>
  );
}

// Elenco usato anche da KioskLayout: se qualcuno arriva col link diretto
// (#tablet/ordini) senza essere amministratore, viene rimandato alle card.
export const REPARTI_SOLO_ADMIN = REPARTI.filter(r => r.soloAdmin).map(r => r.id);

const buzz = (ms = 12) => { try { navigator.vibrate && navigator.vibrate(ms); } catch {} };

function PinKeypad({ titolo, sottotitolo, colore = "#5b7a6b", onSuccess, onCancel, maxLen = 6 }) {
  const [digits, setDigits] = useState("");
  const [errore, setErrore] = useState("");
  const [loading, setLoading] = useState(false);
  const [okNome, setOkNome] = useState(null);
  const [avvio, setAvvio] = useState("");

  const reset = () => {
    setDigits("");
    setErrore("");
    setAvvio("");
    setLoading(false);
  };

  const conferma = async () => {
    if (loading || digits.length < 4) return;
    setLoading(true);
    setErrore("");
    setAvvio("");
    const pin = digits;

    try {
      const res = await axios.post(`${API}/tablet-operatori/login`, { pin }, { timeout: 15000 });
      const op = res.data?.operatore;
      if (!op) throw new Error("Operatore non valido");
      if (res.data?.token) saveToken(res.data.token);
      buzz(20);
      setOkNome(op?.nome || "");
      setTimeout(() => onSuccess(op), 180);
    } catch (err) {
      buzz([40, 60, 40]);
      setAvvio("");
      setErrore(apiError(err, err?.code === "ECONNABORTED"
        ? "Verifica scaduta dopo 15 secondi: controlla la connessione e riprova"
        : "PIN non riconosciuto"));
      setDigits("");
      setLoading(false);
    }
  };

  useEffect(() => {
    if (digits.length !== maxLen || loading) return;
    const t = setTimeout(conferma, 80);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [digits, loading, maxLen]);

  const addDigit = (d) => {
    if (loading || digits.length >= maxLen) return;
    buzz(8);
    setDigits((p) => p + d);
    setErrore("");
  };
  const delDigit = () => { if (!loading) { setDigits((d) => d.slice(0, -1)); setErrore(""); } };
  const annulla = () => { reset(); onCancel?.(); };
  const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "⌫"];

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(42,51,41,0.55)", backdropFilter: "blur(3px)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 300, padding: 16 }} onClick={annulla}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fffefb", borderRadius: 26, padding: "30px 24px", width: "100%", maxWidth: 340, boxShadow: "0 24px 70px rgba(42,51,41,0.35)" }}>
        {okNome !== null ? (
          <div style={{ textAlign: "center", padding: "24px 0" }}>
            <div style={{ width: 72, height: 72, borderRadius: 99, margin: "0 auto 16px", background: colore, display: "flex", alignItems: "center", justifyContent: "center", boxShadow: `0 8px 24px ${colore}55` }}><span style={{ fontSize: 38, color: "#fff" }}>✓</span></div>
            <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "#2a3329" }}>Ciao{okNome ? `, ${okNome}` : ""}</h2>
            <p style={{ margin: "6px 0 0", fontSize: 13, color: "#6b7669" }}>Accesso effettuato</p>
          </div>
        ) : (
          <>
            <div style={{ textAlign: "center", marginBottom: 22 }}>
              <div style={{ fontSize: 34, marginBottom: 8 }}>🔐</div>
              <h2 style={{ margin: 0, fontSize: 21, fontWeight: 700, color: "#2a3329" }}>{titolo}</h2>
              {sottotitolo && <p style={{ margin: "6px 0 0", fontSize: 13, color: "#6b7669" }}>{sottotitolo}</p>}
            </div>
            <div style={{ display: "flex", justifyContent: "center", gap: 12, marginBottom: 18 }}>
              {Array.from({ length: maxLen }).map((_, i) => <div key={i} style={{ width: 15, height: 15, borderRadius: 99, background: i < digits.length ? colore : "#e6e0d4", transform: i < digits.length ? "scale(1.1)" : "scale(1)", boxShadow: i < digits.length ? `0 0 0 4px ${colore}22` : "none" }} />)}
            </div>
            {avvio && !errore && <div style={{ background: "#e2efe8", border: "1px solid #cfe0d5", borderRadius: 10, padding: "10px 14px", marginBottom: 16, textAlign: "center", fontSize: 13, fontWeight: 700, color: "#234d3d" }}>{avvio}</div>}
            {errore && <div style={{ background: "#fbe6e2", border: "1px solid #f3cfc8", borderRadius: 10, padding: "10px 14px", marginBottom: 16, textAlign: "center", fontSize: 13, fontWeight: 700, color: "#8f3829" }}>{errore}</div>}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10 }}>
              {KEYS.map((k, i) => k === "" ? <div key={i} /> : <button key={i} onClick={() => k === "⌫" ? delDigit() : addDigit(k)} disabled={loading} style={{ height: 62, borderRadius: 14, border: "none", background: k === "⌫" ? "#f0ebe0" : "#f7f4ec", color: "#2a3329", fontSize: k === "⌫" ? 22 : 25, fontWeight: 700, cursor: loading ? "wait" : "pointer", opacity: loading ? .6 : 1 }}>{k}</button>)}
            </div>
            <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
              <button onClick={annulla} style={{ flex: 1, padding: 13, border: "1.5px solid #e6e0d4", borderRadius: 14, background: "#fffefb", fontSize: 14, fontWeight: 700, color: "#6b7669", cursor: "pointer" }}>Annulla</button>
              <button onClick={() => conferma()} disabled={loading || digits.length < 4} style={{ flex: 2, padding: 13, border: "none", borderRadius: 14, background: colore, color: "#fff", fontSize: 14, fontWeight: 800, cursor: loading ? "wait" : "pointer", opacity: (loading || digits.length < 4) ? .45 : 1 }}>{loading ? "Verifica..." : "Conferma"}</button>
            </div>
            <p style={{ margin: "10px 0 0", textAlign: "center", color: "#8a8f86", fontSize: 11, fontWeight: 600 }}>4 cifre: premi Conferma. 6 cifre: verifica automatica.</p>
          </>
        )}
      </div>
    </div>
  );
}

function Orologio() {
  const [now, setNow] = useState(new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(t); }, []);
  return <div style={{ textAlign: "center", marginBottom: 48 }}><div style={{ fontSize: 72, fontWeight: 900, color: "#f5f2ea", letterSpacing: -2, lineHeight: 1 }}>{now.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}</div><div style={{ fontSize: 17, color: "#9aa593", marginTop: 8, textTransform: "capitalize" }}>{now.toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" })}</div></div>;
}

export default function TabletHome({ onEntra, preselectReparto, hashRichiesto = "" }) {
  // Il tastierino si apre solo per le card di reparto (PIN personale).
  const [repSel, setRepSel] = useState(REPARTI.find(r => r.id === preselectReparto && !r.soloAdmin) ? preselectReparto : null);
  const [erroreGestionale, setErroreGestionale] = useState("");
  const [verificaGestionale, setVerificaGestionale] = useState(false);
  const sessione = getTabletSession();
  // Un operatore vede solo le card della sua mansione; il titolare tutte.
  const ammessi = repartiAmmessi(sessione);
  const titolareInSessione = !sessione || sessione.ruolo === "amministratore";
  const [richiesteOrdini, setRichiesteOrdini] = useState(0);
  const [avvisoTitolare, setAvvisoTitolare] = useState("");

  // Card riservata (es. Ordini): il titolare entra con la sessione del
  // Gestionale, altrimenti va al login del Gestionale e torna qui.
  const apriRiservata = async (rep, rimandaAlLogin = true) => {
    if (verificaGestionale) return;
    setVerificaGestionale(true);
    setAvvisoTitolare("");
    const titolare = await authLotti.entraDalGestionale();
    setVerificaGestionale(false);
    if (!titolare) {
      if (rimandaAlLogin) authLotti.vaiAlLoginGestionale(`/lotti/#tablet/${rep.id}`);
      else setAvvisoTitolare(`«${rep.label}» è riservata al titolare: entra dal Gestionale.`);
      return;
    }
    allineaSessioneTitolare(titolare, rep.id);
    window.location.hash = `tablet/${rep.id}`;
    window.dispatchEvent(new Event("tablet-auth"));
    onEntra?.(rep.id, titolare);
  };

  // Ritorno dal login del Gestionale su #tablet/<card riservata>: si prova la
  // sessione una volta sola, senza rimandare di nuovo al login (niente giri).
  useEffect(() => {
    const rep = REPARTI.find((r) => r.id === preselectReparto);
    if (rep?.soloAdmin && !ammessi?.includes(rep.id)) apriRiservata(rep, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preselectReparto]);

  useEffect(() => {
    if (sessione?.ruolo !== "amministratore") return;
    let attivo = true;
    const aggiorna = async () => {
      try {
        const risposta = await axios.get(`${API}/ordini-fornitori/carrello-sospesi`);
        if (attivo) setRichiesteOrdini((risposta.data?.richieste || []).length);
      } catch { /* il badge si aggiorna alla prossima lettura */ }
    };
    aggiorna();
    const fermaPolling = avviaPollingVisibile(aggiorna, 15000);
    return () => { attivo = false; fermaPolling(); };
  }, [sessione?.ruolo]);

  // Il ruolo di Lotti (HACCP, caporeparto) si rilegge dal server a ogni
  // apertura della home: cambiato nella scheda HR, il tablet lo vede senza
  // rifare il PIN. Il backend lo ricontrolla comunque a ogni operazione.
  const sessioneId = sessione?.dipendente_id;
  useEffect(() => {
    if (!sessioneId || sessione?.ruolo === "amministratore") return;
    let attivo = true;
    axios.get(`${API}/auth/me`).then((r) => {
      const attuale = getTabletSession();
      if (attivo && r.data?.profilo && attuale?.dipendente_id === sessioneId) {
        saveTabletSession({ ...attuale, profilo: r.data.profilo }, attuale.reparto);
      }
    }).catch(() => { /* resta il profilo del login */ });
    return () => { attivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessioneId]);

  const handleSuccess = (operatore) => {
    const repartoCorrente = repSel;
    // Il ruolo entrato dal tablet è la fonte di verità anche per il gestionale:
    // se entra un dipendente, un eventuale "amministratore" rimasto in memoria
    // da una sessione precedente viene declassato (25/07/2026).
    saveRuolo(operatore?.ruolo || "operatore");
    saveTabletSession({ ...operatore, reparto_pin: repartoCorrente }, repartoCorrente);
    setRepSel(null);
    // Il login riapre la sottopagina richiesta, non il cruscotto del reparto.
    // Non trasferire però Colazione/Produci quando si sceglie un altro reparto.
    // La destinazione viene dal router, non dall'hash letto dopo la risposta PIN.
    const repartoHash = `tablet/${repartoCorrente}`;
    const targetHash = repartoCorrente === "ricette" ? "ricette"
      : hashRichiesto.startsWith(`${repartoHash}/`) ? hashRichiesto : repartoHash;
    if (window.location.hash !== `#${targetHash}`) window.location.hash = targetHash;
    window.dispatchEvent(new Event("tablet-auth"));
    onEntra?.(repartoCorrente, operatore);
  };

  const handleEsciAdmin = (operatore = null) => {
    if (operatore) saveTabletSession(operatore, "home");
    // Serve anche il ruolo salvato: il gestionale ora si apre SOLO da
    // amministratore (25/07/2026), altrimenti si tornerebbe subito al kiosk.
    saveRuolo("amministratore");
    // Apre anche il cancello del gestionale: senza, bastava ricaricare la
    // pagina per ritrovarsi il tastierino "Accesso Lotti" (collaudo del
    // 25/07/2026). Quanto dura lo decide il server: il token si rinnova da
    // solo al massimo 24 ore dall'ingresso dell'amministratore, poi 401.
    setGateOk();
    window.location.hash = prendiPaginaRichiesta("dashboard");
    window.dispatchEvent(new Event("tablet-auth"));
  };

  const chiediEsciAdmin = async () => {
    if (verificaGestionale) return;
    // Sessione unica: se il titolare e' gia' entrato nel Gestionale, basta
    // un tocco. Altrimenti si passa dal login del Gestionale e si torna qui:
    // niente secondo tastierino per l'amministratore (25/09/2026).
    setVerificaGestionale(true);
    const dalGestionale = await authLotti.entraDalGestionale();
    setVerificaGestionale(false);
    if (dalGestionale) { allineaSessioneTitolare(dalGestionale, "home"); handleEsciAdmin(); return; }
    const corrente = getTabletSession();
    if (corrente?.ruolo !== "amministratore") {
      authLotti.vaiAlLoginGestionale("/lotti/#dashboard");
      return;
    }
    setVerificaGestionale(true);
    setErroreGestionale("");
    try {
      const risposta = await axios.get(`${API}/auth/me`);
      const utente = risposta.data?.user;
      if (utente?.ruolo === "amministratore" && utente?.dipendente_id === corrente.dipendente_id) {
        handleEsciAdmin();
      } else {
        authLotti.vaiAlLoginGestionale("/lotti/#dashboard");
      }
    } catch (err) {
      if (err?.response?.status === 401) authLotti.vaiAlLoginGestionale("/lotti/#dashboard");
      else setErroreGestionale(apiError(err, "Verifica non disponibile, riprova"));
    } finally {
      setVerificaGestionale(false);
    }
  };

  const colorePin = repSel === "pasticceria" ? "var(--warning)" : repSel === "rosticceria" ? "var(--info)" : repSel === "bar" ? "#b45309" : repSel === "vendita" ? "#f97316" : "var(--success)";

  const scegliReparto = (rep) => {
    const session = getTabletSession();
    if (rep.soloAdmin && !ammessi?.includes(rep.id)) {
      // Un dipendente identificato sul tablet non passa per il ruolo salvato:
      // si riverifica la sessione del Gestionale, che riallinea la persona.
      if (session?.ruolo === "amministratore" || (!session && sessioneTitolareAttiva())) {
        if (session) moveTabletSessionTo(rep.id);
        onEntra?.(rep.id, session);
        window.location.hash = `tablet/${rep.id}`;
        return;
      }
      apriRiservata(rep);
      return;
    }
    if (session) {
      moveTabletSessionTo(rep.id);
      onEntra?.(rep.id, session);
      window.location.hash = rep.id === "ricette" ? "ricette" : `tablet/${rep.id}`;
      return;
    }
    setRepSel(rep.id);
  };

  return (
    <div style={{ minHeight: "100vh", background: "#1c2620", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "32px 16px", userSelect: "none", position: "relative", overflow: "hidden" }}>
      <div style={{ position: "absolute", top: -100, right: -100, width: 400, height: 400, borderRadius: "50%", background: "radial-gradient(circle, rgba(63,90,78,.15) 0%, transparent 70%)", pointerEvents: "none" }} />
      <Orologio />
      <div style={{ marginBottom: 40, textAlign: "center" }}>
        <div style={{ fontSize: 13, color: "#6b7669", fontWeight: 800, letterSpacing: 4, textTransform: "uppercase" }}>Ceraldi Group</div>
        <div style={{ fontSize: 12, color: "#8a8478", marginTop: 5 }}>{sessione ? `Seleziona reparto · ${sessione.nome}` : "Seleziona reparto e inserisci il tuo PIN"}</div>
      </div>
      <StatoGiorno attivo={!!sessione && titolareInSessione} />
      <div style={{ display: "flex", gap: 20, flexWrap: "wrap", justifyContent: "center", width: "100%", maxWidth: 760, marginBottom: 48 }}>
        {REPARTI.filter(r => !ammessi || ammessi.includes(r.id)).map(r => (
          <button key={r.id} onClick={() => scegliReparto(r)}
            style={{ position: "relative", flex: "1 1 150px", maxWidth: 220, minWidth: 0, height: 200, padding: "0 8px", borderRadius: 24, border: "none", background: r.grad, color: "#fff", cursor: "pointer", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, boxShadow: `0 8px 32px ${r.shadow}`, fontFamily: "inherit" }}>
            {r.soloAdmin && !ammessi?.includes(r.id) && (
              <span style={{ position: "absolute", top: 12, right: 12, display: "inline-flex", alignItems: "center", gap: 5, background: "rgba(0,0,0,.35)", borderRadius: 999, padding: "4px 10px", fontSize: 11, fontWeight: 800, letterSpacing: .3 }}>
                <Lock size={12} /> Solo titolare
              </span>
            )}
            {r.id === "ordini" && sessione?.ruolo === "amministratore" && richiesteOrdini > 0 && (
              <span style={{ position:"absolute", top:12, left:12, background:"#d35f4e", color:"#fff", borderRadius:999, padding:"5px 9px", fontSize:12, fontWeight:900 }}>
                {richiesteOrdini} da valutare
              </span>
            )}
            {r.etichetta && (
              <span style={{ position: "absolute", top: 12, right: 12, display: "inline-flex", alignItems: "center", gap: 5, background: "rgba(0,0,0,.35)", borderRadius: 999, padding: "4px 10px", fontSize: 11, fontWeight: 800, letterSpacing: .3 }}>
                <Lock size={12} /> {r.etichetta}
              </span>
            )}
            {r.icona ? <r.icona size={56} aria-hidden="true" /> : <span style={{ fontSize: 56 }}>{r.emoji}</span>}
            <span style={{ fontSize: 20, fontWeight: 900 }}>{r.label}</span>
          </button>
        ))}
      </div>
      {avvisoTitolare && (
        <div role="status" style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", justifyContent: "center", background: "#fffefb", color: "#2a3329", borderRadius: 14, padding: "10px 16px", marginTop: -28, marginBottom: 20, fontWeight: 700 }}>
          {avvisoTitolare}
          <a href={authLotti.loginGestionale("/lotti/#tablet/home")} style={{ minHeight: 44, display: "inline-flex", alignItems: "center", padding: "0 14px", borderRadius: 10, background: "#5b7a6b", color: "#fff", textDecoration: "none" }}>Entra dal Gestionale</a>
        </div>
      )}
      {erroreGestionale && <div role="alert" style={{ position: "absolute", bottom: 60, right: 20, color: "#fff" }}>{erroreGestionale}</div>}
      {/* Cambio operatore e Gestionale: due bottoni grandi e sempre visibili
          (prima il Gestionale era un bottoncino nell'angolo e per cambiare
          persona bisognava entrare in un reparto). */}
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", justifyContent: "center" }}>
        {sessione && (
          <button onClick={cambiaOperatore} data-testid="home-cambia-operatore"
            style={{ minHeight: 56, padding: "0 22px", borderRadius: 16, border: "1px solid #4a5a50", background: "#2a3329", color: "#f5f2ea", fontSize: 16, fontWeight: 800, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 8, fontFamily: "inherit" }}>
            <LogOut size={18} aria-hidden="true" /> Cambia operatore · {sessione.nome}
          </button>
        )}
        {titolareInSessione && <button onClick={chiediEsciAdmin} disabled={verificaGestionale} data-testid="home-gestionale"
          style={{ minHeight: 56, padding: "0 22px", borderRadius: 16, border: "1px solid #4a5a50", background: "transparent", color: "#e6e0d4", fontSize: 16, fontWeight: 800, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 8, fontFamily: "inherit" }}>
          <LayoutDashboard size={18} aria-hidden="true" /> Gestionale <Lock size={14} aria-hidden="true" /> solo titolare
        </button>}
      </div>
      {repSel && (() => {
        const rep = REPARTI.find(r => r.id === repSel);
        return (
          <PinKeypad
            titolo={rep?.label || repSel}
            sottotitolo="Inserisci il tuo PIN personale"
            colore={colorePin}
            maxLen={6}
            onSuccess={handleSuccess}
            onCancel={() => setRepSel(null)}
          />
        );
      })()}
    </div>
  );
}
