import { useEffect, useState, useCallback } from "react";
import PinKeypad from "@/components/haccp/shared/PinKeypad";
import GoogleLoginButton from "@/components/auth/GoogleLoginButton";
import { fetchAuthConfig, cachedAuthConfig, gateStillValid, setGateOk, clearGate, isAdmin } from "@/auth";

/**
 * Cancello di accesso. Regole (riviste 13/06/2026 dopo i bug visti da Enzo):
 *  - rotte tablet (kiosk) → l'app tablet ha il suo login → passa
 *  - enforcement spento (da config FRESCA o dall'ultima config nota) → passa
 *  - enforcement acceso → serve un token valido. Se la rete è giù e un token
 *    ESISTE → grazia (il vero 401 lo intercetta axios alla prima chiamata).
 *  - il controllo si fa UNA volta a sessione: NIENTE ricontrollo a ogni cambio
 *    pagina (era la causa delle richieste PIN ripetute dopo l'accesso).
 */
export default function LoginGate({ children }) {
  const [state, setState] = useState("checking"); // checking | open | locked
  const [cfg, setCfg] = useState({ enforce: false, google_enabled: false, google_client_id: "" });

  const isTablet = () => (window.location.hash || "").replace("#", "").startsWith("tablet");

  const check = useCallback(async () => {
    if (isTablet()) { setState("open"); return; }

    // Enzo 25/07/2026: chi non è amministratore non deve nemmeno vedere il
    // tastierino del gestionale — l'app si apre sulle card del tablet, che
    // hanno il loro login per reparto. Il titolare rientra dal bottone
    // "Gestionale — solo titolare" nella home del kiosk.
    if (!isAdmin()) {
      window.location.hash = "tablet/home";
      setState("open");
      return;
    }
    // PIN valido nelle ultime 2 ORE (localStorage): entra senza richiederlo,
    // su qualunque pagina/scheda. Scadute le 2 ore → si richiede il PIN,
    // anche se il token tecnicamente vive ancora. (richiesta Enzo 02/07/2026)
    if (gateStillValid()) { setState("open"); return; }

    const cached = cachedAuthConfig();   // null se non c'è una config REALE
    if (cached) setCfg(cached);

    // Se sappiamo per certo (config reale) che l'enforcement è spento → apri.
    if (cached && cached.enforce === false) { setState("open"); return; }

    // Cancello scaduto o mai aperto: PIN subito. Niente attesa, niente
    // apertura senza PIN. (fix Enzo 14/06/2026)
    setState("locked");

    // In background allineo la config vera per le sessioni future.
    fetchAuthConfig().then((c) => {
      setCfg(c);
      if (c && c.enforce === false) {
        setState("open");
      }
    }).catch(() => {});
  }, []);

  useEffect(() => { check(); }, [check]);

  useEffect(() => {
    // SOLO il vero cambio di autenticazione (401 dall'interceptor, logout)
    // riapre il cancello. Il cambio pagina NON ricontrolla più nulla.
    const h = () => { clearGate(); check(); };
    window.addEventListener("lotti-auth-changed", h);
    return () => window.removeEventListener("lotti-auth-changed", h);
  }, [check]);

  if (state === "checking") {
    return (
      <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", background: "#faf7f0", color: "#5b7a6b", fontWeight: 700 }}>
        Caricamento…
      </div>
    );
  }
  if (state === "open") return children;

  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", background: "#faf7f0", padding: 16 }}>
      <div style={{ width: "min(420px, 94vw)" }}>
        <PinKeypad
          titolo="Accesso Lotti"
          sottotitolo="Inserisci il tuo PIN"
          maxLen={6}
          onSuccess={() => { setGateOk(); setState("open"); }}
          onCancel={() => {}}
        />
        {cfg.google_enabled && cfg.google_client_id ? (
          <div style={{ marginTop: 20, textAlign: "center" }}>
            <div style={{ color: "#9a917f", fontSize: 13, marginBottom: 10 }}>oppure</div>
            <GoogleLoginButton clientId={cfg.google_client_id} onSuccess={() => { setGateOk(); setState("open"); }} />
          </div>
        ) : null}
      </div>
    </div>
  );
}
