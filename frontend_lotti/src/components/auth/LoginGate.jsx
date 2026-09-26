import { useEffect, useState, useCallback } from "react";
import { LogIn } from "lucide-react";
import { fetchAuthConfig, cachedAuthConfig, gateStillValid, clearGate, isAdmin, ricordaPaginaRichiesta, entraDalGestionale, loginGestionale } from "@/auth";
import { allineaSessioneTitolare, getTabletSession } from "../../utils/tabletSession";

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

  const isTablet = () => (window.location.hash || "").replace("#", "").startsWith("tablet");

  const check = useCallback(async () => {
    if (isTablet() || (window.location.hash === "#ricette" && getTabletSession())) { setState("open"); return; }

    // Sessione unica (25/09/2026): chi e' gia' entrato nel Gestionale apre
    // Lotti da amministratore senza un secondo PIN.
    // Il tablet passa al titolare: un dipendente rimasto identificato non
    // firmerebbe col token dell'amministratore.
    if (!(isAdmin() && gateStillValid())) {
      const titolare = await entraDalGestionale();
      if (titolare) { allineaSessioneTitolare(titolare, "home"); setState("open"); return; }
    }

    // Enzo 25/07/2026: chi non è amministratore non deve nemmeno vedere il
    // tastierino del gestionale — l'app si apre sulle card del tablet, che
    // hanno il loro login per reparto. Il titolare rientra dal bottone
    // "Gestionale — solo titolare" nella home del kiosk.
    if (!isAdmin()) {
      ricordaPaginaRichiesta();
      window.location.hash = "tablet/home";
      setState("open");
      return;
    }
    // Cancello aperto finché c'è un token (vedi setGateOk in auth.js): si
    // entra su qualunque pagina/scheda senza chiedere di nuovo l'accesso.
    if (gateStillValid()) { setState("open"); return; }

    const cached = cachedAuthConfig();   // null se non c'è una config REALE

    // Se sappiamo per certo (config reale) che l'enforcement è spento → apri.
    if (cached && cached.enforce === false) { setState("open"); return; }

    // Cancello chiuso: si entra dal Gestionale. Niente attesa, niente
    // apertura senza accesso. (fix Enzo 14/06/2026)
    setState("locked");

    // In background allineo la config vera per le sessioni future.
    fetchAuthConfig().then((c) => {
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
        {/* Niente secondo tastierino: l'amministratore entra con il login del
            Gestionale e torna qui (sessione unica). I dipendenti usano le card
            del tablet, che hanno il loro PIN personale. */}
        <div style={{ background: "#fffefb", border: "1px solid #e6e0d4", borderRadius: 16, padding: 24, textAlign: "center" }}>
          <h1 style={{ margin: "0 0 6px", fontSize: 20, fontWeight: 800, color: "#2a3329", letterSpacing: "-0.02em" }}>Accesso Lotti</h1>
          <p style={{ margin: "0 0 18px", fontSize: 14, color: "#6b6358" }}>
            Entra dal Gestionale: dopo l'accesso torni qui, senza un secondo PIN.
          </p>
          <a href={loginGestionale()} style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8, minHeight: 48, padding: "0 22px", borderRadius: 12, background: "#5b7a6b", color: "#fffefb", fontWeight: 800, textDecoration: "none" }}>
            <LogIn size={18} aria-hidden="true" /> Entra dal Gestionale
          </a>
          <p style={{ margin: "16px 0 0", fontSize: 13 }}>
            <a href="#tablet/home" style={{ color: "#3f5a4e", fontWeight: 700 }}>Sono un dipendente: vai ai reparti</a>
          </p>
        </div>
      </div>
    </div>
  );
}
