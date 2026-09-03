// Router radice: kiosk tablet (#tablet/…) vs app principale — estratto da
// App.js (fase 2, 24/07/2026). AppComponent arriva come prop per evitare
// un import circolare con App.js.
import { useEffect, useState } from "react";
import axios from "axios";
import { API } from "../utils/constants";
import KioskLayout from "../layouts/KioskLayout";
import { isAdmin } from "../auth";

export default function AppRouter({ AppComponent }) {
  const [hash, setHash] = useState(window.location.hash.replace("#", ""));
  const [, setAuthTick] = useState(0);

  // Keep-warm: finché l'app è aperta (es. tablet del kiosk sempre acceso) pinga
  // il backend ogni 10 min, così Render non va in sleep e login/temperature
  // restano istantanei.
  useEffect(() => {
    const ping = () => axios.get(`${API}/tablet-operatori/verifica`, { timeout: 8000 }).catch(() => {});
    ping();
    const id = setInterval(ping, 10 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const onHash = () => setHash(window.location.hash.replace("#", ""));
    const onAuth = () => setAuthTick((t) => t + 1);
    window.addEventListener("hashchange", onHash);
    window.addEventListener("tablet-auth", onAuth);
    return () => {
      window.removeEventListener("hashchange", onHash);
      window.removeEventListener("tablet-auth", onAuth);
    };
  }, []);

  if (hash.startsWith("tablet/")) return <KioskLayout hash={hash} />;

  // REGOLA ACCESSI (Enzo 25/07/2026): i dipendenti vedono SOLO le card del
  // tablet; il gestionale compare solo dopo il PIN amministratore (dalla home
  // kiosk, bottone "Gestionale — solo titolare"). Vale anche per un indirizzo
  // digitato a mano: qualunque pagina non-tablet rimanda al kiosk.
  // Questo è un filtro di comodità lato schermo — la sicurezza vera resta nel
  // backend (auth_dependency + require_admin sugli endpoint sensibili).
  if (!isAdmin()) {
    if (!window.location.hash.startsWith("#tablet/")) window.location.hash = "tablet/home";
    return <KioskLayout hash="tablet/home" />;
  }
  return <AppComponent />;
}
