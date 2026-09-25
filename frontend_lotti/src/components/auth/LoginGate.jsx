import { useEffect, useState, useCallback } from "react";
import { LogIn } from "lucide-react";
import GoogleLoginButton from "@/components/auth/GoogleLoginButton";
import { fetchAuthConfig, cachedAuthConfig, gateStillValid, setGateOk, clearGate, isAdmin, ricordaPaginaRichiesta, entraDalGestionale, loginGestionale } from "@/auth";
import { getTabletSession } from "../../utils/tabletSession";

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
    if (isTablet() || (window.location.hash === "#ricette" && getTabletSession())) { setState("open"); return; }

    // Sessione unica (25/09/2026): chi e' gia' entrato nel Gestionale apre
    // Lotti da amministratore senza un secondo PIN.
    if (!(isAdmin() && gateStillValid()) && await entraDalGestionale()) { setState("open"); return; }

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
