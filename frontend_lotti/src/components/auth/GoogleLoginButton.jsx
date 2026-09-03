import { useEffect, useRef } from "react";
import axios from "axios";
import { toast } from "sonner";
import { API } from "@/utils/constants";
import { saveToken, saveRuolo, saveOperatoreNome } from "@/auth";

/**
 * Pulsante "Accedi con Google".
 * Carica Google Identity Services, mostra il bottone ufficiale e, ricevuto
 * l'ID token, lo manda al backend (/auth/google) che lo verifica ed emette il
 * nostro token. Renderizza nulla finché non arriva un clientId valido.
 */
export default function GoogleLoginButton({ clientId, onSuccess }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!clientId) return;

    const onCredential = async (resp) => {
      try {
        const r = await axios.post(
          `${API}/auth/google`,
          { credential: resp.credential },
          { timeout: 15000 }
        );
        if (r.data && r.data.token) {
          saveToken(r.data.token);
          saveRuolo(r.data?.operatore?.ruolo || "amministratore");
          saveOperatoreNome(r.data?.operatore?.nome || "Amministratore");
          try { sessionStorage.setItem("tablet_operatore", JSON.stringify(r.data.operatore || {})); } catch { /* no-op */ }
          onSuccess && onSuccess(r.data.operatore);
        }
      } catch (e) {
        toast.error("Accesso Google non riuscito o email non autorizzata");
      }
    };

    const init = () => {
      const g = window.google;
      if (!g || !g.accounts || !g.accounts.id) return;
      g.accounts.id.initialize({ client_id: clientId, callback: onCredential });
      if (ref.current) {
        g.accounts.id.renderButton(ref.current, {
          theme: "outline", size: "large", width: 300, text: "signin_with", shape: "pill",
        });
      }
    };

    if (window.google && window.google.accounts && window.google.accounts.id) {
      init();
      return;
    }
    const SCRIPT_ID = "gsi-client";
    let s = document.getElementById(SCRIPT_ID);
    if (!s) {
      s = document.createElement("script");
      s.src = "https://accounts.google.com/gsi/client";
      s.async = true;
      s.defer = true;
      s.id = SCRIPT_ID;
      s.onload = init;
      document.body.appendChild(s);
    } else {
      s.addEventListener("load", init);
    }
  }, [clientId, onSuccess]);

  return <div ref={ref} style={{ display: "flex", justifyContent: "center" }} />;
}
