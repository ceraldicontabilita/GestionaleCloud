import { useEffect, useState } from "react";
import { saveToken, saveRuolo, setAdminGateOk, adminGateStillValid, setGateOk } from "@/auth";
import axios from "axios";
import { Lock } from "lucide-react";
import { apiError } from "../../utils/apiError";
import { clearTabletSession, getTabletSession, moveTabletSessionTo, saveTabletSession } from "../../utils/tabletSession";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

// Card del tablet.
// REGOLA ENZO 25/07/2026: «il dipendente deve solo produrre e vedere le
// ricette, tutto il resto lo guardo io e lo utilizzo io: metti tutto sotto
// PIN». Quindi le card restano tutte visibili — Enzo le usa dal tablet col
// SUO pin — ma quelle marcate `soloAdmin` chiedono il PIN da amministratore e
// respingono il PIN di un dipendente.
const REPARTI = [
  { id: "pasticceria", label: "Pasticceria", emoji: "🍰", grad: "linear-gradient(135deg,#fb923c,#ea580c)", shadow: "rgba(234,88,12,.5)" },
  { id: "rosticceria", label: "Rosticceria", emoji: "🥙", grad: "linear-gradient(135deg,#86efac,#22c55e)", shadow: "rgba(34,197,94,.5)" },
  { id: "bar", label: "Bar", emoji: "☕", grad: "linear-gradient(135deg,#b45309,#78350f)", shadow: "rgba(120,53,15,.5)" },
  { id: "vendita", label: "Produzioni al banco", emoji: "🧾", grad: "linear-gradient(135deg,#5b7a6b,#3f5a4e)", shadow: "rgba(63,90,78,.5)" },
  { id: "dosi", label: "Dose di oggi", emoji: "⚖️", grad: "linear-gradient(135deg,#c4894a,#9c6a32)", shadow: "rgba(156,106,50,.5)" },
  { id: "magazzino", label: "Magazzino", emoji: "📦", grad: "linear-gradient(135deg,#6f583a,#4a3f33)", shadow: "rgba(74,63,51,.5)" },
  { id: "lavagna", label: "Lavagna richieste", emoji: "📺", grad: "linear-gradient(135deg,#8a6f47,#6f583a)", shadow: "rgba(111,88,58,.5)" },
  { id: "ordini", label: "Ordini", emoji: "🛒", grad: "linear-gradient(135deg,#6f9180,#4f6d5f)", shadow: "rgba(79,109,95,.5)", soloAdmin: true },
];

// Elenco usato anche da KioskLayout: se qualcuno arriva col link diretto
// (#tablet/ordini) senza essere amministratore, viene rimandato alle card.
export const REPARTI_SOLO_ADMIN = REPARTI.filter(r => r.soloAdmin).map(r => r.id);

const buzz = (ms = 12) => { try { navigator.vibrate && navigator.vibrate(ms); } catch {} };

function PinKeypad({ titolo, sottotitolo, colore = "#5b7a6b", onSuccess, onCancel, maxLen = 6, onlyAdmin = false }) {
  const [digits, setDigits] = useState("");
  const [errore, setErrore] = useState("");
  const [loading, setLoading] = useState(false);
  const [okNome, setOkNome] = useState(null);
  const [avvio, setAvvio] = useState("");
  const [scelte, setScelte] = useState([]);

  const reset = () => {
    setDigits("");
    setErrore("");
    setAvvio("");
    setScelte([]);
    setLoading(false);
  };

  const conferma = async (operatoreId = null) => {
    if (loading || digits.length < 4) return;
    setLoading(true);
    setErrore("");
    setAvvio("");
    const pin = digits;

    const start = Date.now();
    const MAX_WAIT = 150000; // copre anche un risveglio lento di Render
    let tentativo = 0;
    while (true) {
      tentativo += 1;
      try {
        const res = await axios.post(`${API}/tablet-operatori/login`, {
          pin,
          ...(operatoreId ? { operatore_id: operatoreId } : {}),
        }, { timeout: 15000 });
        if (res.data?.scelta_operatore) {
          const candidati = (res.data.operatori || []).filter(
            (op) => !onlyAdmin || op?.ruolo === "amministratore"
          );
          if (!candidati.length) {
            setErrore("PIN non autorizzato");
            setDigits("");
          } else {
            setScelte(candidati);
          }
          setLoading(false);
          return;
        }
        const op = res.data?.operatore;
        if (!op) throw new Error("Operatore non valido");
        if (res.data?.token) saveToken(res.data.token);  // token per le letture sotto enforce
        if (onlyAdmin && op.ruolo !== "amministratore") {
          setErrore("PIN non autorizzato");
          setDigits("");
          setLoading(false);
          return;
        }
        buzz(20);
        setOkNome(op?.nome || "");
        setTimeout(() => onSuccess(op), 180);
        return;
      } catch (err) {
        const status = err?.response?.status;
        if (status === 401 || status === 403) {
          buzz([40, 60, 40]);
          setErrore(apiError(err, "PIN non riconosciuto"));
          setDigits("");
          setLoading(false);
          return;
        }
        const retryable = !err?.response || [502, 503, 504].includes(status) || err?.code === "ECONNABORTED";
        if (retryable && Date.now() - start < MAX_WAIT) {
          const secs = Math.round((Date.now() - start) / 1000);
          setAvvio(`Avvio del server in corso… l'accesso parte da solo, attendi (${secs}s)`);
          await new Promise((r) => setTimeout(r, 2500));
          continue;
        }
        buzz([40, 60, 40]);
        setAvvio("");
        setErrore(apiError(err, "Server non raggiungibile, riprova tra poco"));
        setLoading(false);
        return;
      }
    }
  };

  useEffect(() => {
    if (digits.length !== maxLen || loading || scelte.length > 0) return;
    const t = setTimeout(conferma, 80);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [digits, loading, maxLen, scelte.length]);

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
        ) : scelte.length > 0 ? (
          <div>
            <div style={{ textAlign: "center", marginBottom: 20 }}>
              <div style={{ fontSize: 34, marginBottom: 8 }}>👤</div>
              <h2 style={{ margin: 0, fontSize: 21, fontWeight: 700, color: "#2a3329" }}>Chi sta operando?</h2>
              <p style={{ margin: "7px 0 0", fontSize: 13, color: "#6b7669" }}>Il PIN è condiviso; scegli il nome da registrare nei log.</p>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {scelte.map((op) => (
                <button key={op.id} onClick={() => conferma(op.id)} disabled={loading}
                  style={{ padding: "15px 14px", border: "none", borderRadius: 14, background: colore, color: "#fff", fontSize: 16, fontWeight: 800, cursor: loading ? "wait" : "pointer", opacity: loading ? .6 : 1 }}>
                  {op.nome}
                </button>
              ))}
            </div>
            <button onClick={reset} disabled={loading}
              style={{ width: "100%", marginTop: 14, padding: 12, border: "1.5px solid #e6e0d4", borderRadius: 14, background: "#fffefb", color: "#6b7669", fontSize: 14, fontWeight: 700, cursor: "pointer" }}>
              Indietro
            </button>
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

export default function TabletHome({ onEntra, preselectReparto }) {
  const [repSel, setRepSel] = useState(preselectReparto && REPARTI.find(r => r.id === preselectReparto) ? preselectReparto : null);
  const [showAdminEsci, setShowAdminEsci] = useState(false);

  useEffect(() => {
    axios.get(`${API}/tablet-operatori/verifica`, { timeout: 8000 }).catch(() => {});
  }, []);

  const handleSuccess = (operatore) => {
    const repartoCorrente = repSel;
    // Il ruolo entrato dal tablet è la fonte di verità anche per il gestionale:
    // se entra un dipendente, un eventuale "amministratore" rimasto in memoria
    // da una sessione precedente viene declassato (25/07/2026).
    saveRuolo(operatore?.ruolo || "operatore");
    saveTabletSession(operatore, repartoCorrente);
    setRepSel(null);
    const targetHash = `tablet/${repartoCorrente}`;
    if (window.location.hash !== `#${targetHash}`) window.location.hash = targetHash;
    window.dispatchEvent(new Event("tablet-auth"));
    onEntra?.(repartoCorrente, operatore);
  };

  const handleEsciAdmin = () => {
    setAdminGateOk(); // PIN admin verificato ORA: vale 2 ore, niente richiesta ripetuta
    // Serve anche il ruolo salvato: il gestionale ora si apre SOLO da
    // amministratore (25/07/2026), altrimenti si tornerebbe subito al kiosk.
    saveRuolo("amministratore");
    // Apre anche il cancello del gestionale per 2 ore: senza, bastava
    // ricaricare la pagina per ritrovarsi il tastierino "Accesso Lotti"
    // (trovato al collaudo del 25/07/2026).
    setGateOk();
    const op = getTabletSession({ allowExpired: true });
    if (op?.nome) axios.post(`${API}/tablet-operatori/logout`, { nome: op.nome, reparto: op.reparto || "" }, { timeout: 6000 }).catch(() => {});
    clearTabletSession();
    setShowAdminEsci(false);
    window.location.hash = "dashboard";
    window.dispatchEvent(new Event("tablet-auth"));
  };

  // Se il PIN admin è già stato verificato nelle ultime 2 ore, esci subito
  // senza richiederlo di nuovo (richiesta Enzo 03/07/2026).
  const chiediEsciAdmin = () => {
    if (adminGateStillValid()) handleEsciAdmin();
    else setShowAdminEsci(true);
  };

  const colorePin = repSel === "pasticceria" ? "var(--warning)" : repSel === "rosticceria" ? "var(--info)" : repSel === "bar" ? "#b45309" : repSel === "vendita" ? "#f97316" : "var(--success)";

  const scegliReparto = (rep) => {
    const session = getTabletSession();
    if (session && (!rep.soloAdmin || session.ruolo === "amministratore")) {
      moveTabletSessionTo(rep.id);
      onEntra?.(rep.id, session);
      window.location.hash = `tablet/${rep.id}`;
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
        <div style={{ fontSize: 12, color: "#8a8478", marginTop: 5 }}>Seleziona reparto e inserisci il tuo PIN</div>
      </div>
      <div style={{ display: "flex", gap: 20, flexWrap: "wrap", justifyContent: "center", maxWidth: 760, marginBottom: 48 }}>
        {REPARTI.map(r => (
          <button key={r.id} onClick={() => scegliReparto(r)}
            style={{ position: "relative", width: 220, height: 200, borderRadius: 24, border: "none", background: r.grad, color: "#fff", cursor: "pointer", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, boxShadow: `0 8px 32px ${r.shadow}`, fontFamily: "inherit" }}>
            {r.soloAdmin && (
              <span style={{ position: "absolute", top: 12, right: 12, display: "inline-flex", alignItems: "center", gap: 5, background: "rgba(0,0,0,.35)", borderRadius: 999, padding: "4px 10px", fontSize: 11, fontWeight: 800, letterSpacing: .3 }}>
                <Lock size={12} /> Solo titolare
              </span>
            )}
            <span style={{ fontSize: 56 }}>{r.emoji}</span>
            <span style={{ fontSize: 20, fontWeight: 900 }}>{r.label}</span>
          </button>
        ))}
      </div>
      <button onClick={chiediEsciAdmin} style={{ position: "absolute", bottom: 20, right: 20, padding: "8px 16px", borderRadius: 10, border: "1px solid #4a463c", background: "transparent", color: "#8a8478", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>🔒 Gestionale — solo titolare</button>
      {repSel && (() => {
        const rep = REPARTI.find(r => r.id === repSel);
        return (
          <PinKeypad
            titolo={rep?.label || repSel}
            sottotitolo={rep?.soloAdmin ? "Riservato al titolare: serve il PIN da amministratore" : "Inserisci il tuo PIN personale"}
            colore={rep?.soloAdmin ? "#b04a3a" : colorePin}
            maxLen={6}
            onlyAdmin={!!rep?.soloAdmin}
            onSuccess={handleSuccess}
            onCancel={() => setRepSel(null)}
          />
        );
      })()}
      {showAdminEsci && <PinKeypad titolo="PIN Amministratore" sottotitolo="Solo l'amministratore può uscire dal kiosk" colore="#b04a3a" maxLen={6} onlyAdmin onSuccess={handleEsciAdmin} onCancel={() => setShowAdminEsci(false)} />}
    </div>
  );
}

export { PinKeypad };
