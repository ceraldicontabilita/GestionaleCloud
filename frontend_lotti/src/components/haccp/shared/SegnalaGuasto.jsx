import { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";
import { API } from "../../../utils/constants";
import { apiError } from "../../../utils/apiError";
import { getOperatoreNome } from "../../../auth";

// SEGNALA GUASTO (richiesta Enzo 25/07/2026)
// Un tocco accanto al frigorifero/congelatore: apre l'anomalia sull'apparecchio
// e porta SUBITO alla pagina Anomalie, dove il sistema ricalcola i lotti che
// sono dentro e propone di spostarli. Prima bisognava ricordarsi di andare in
// Anomalie e riscrivere il nome dell'attrezzatura a mano.
export default function SegnalaGuasto({ attrezzatura, categoria = "Frigorifero", compatto = true }) {
  const [aperto, setAperto] = useState(false);
  const [descrizione, setDescrizione] = useState("");
  const [invio, setInvio] = useState(false);

  const segnala = async () => {
    const testo = descrizione.trim() || `Guasto ${attrezzatura}`;
    setInvio(true);
    try {
      await axios.post(`${API}/anomalie/registra`, {
        attrezzatura,
        categoria,
        tipo: "Guasto",
        descrizione: testo,
        operatore_segnalazione: getOperatoreNome() || "",
        priorita: "Alta",
      });
      toast.success(`Guasto segnalato su ${attrezzatura} — sposta i lotti che sono dentro`);
      setAperto(false);
      setDescrizione("");
      window.location.hash = "anomalie";
    } catch (e) {
      toast.error("Errore segnalazione: " + apiError(e));
    } finally {
      setInvio(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); setAperto(true); }}
        title={`Segnala un guasto su ${attrezzatura} e sposta i lotti`}
        style={{
          display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 4,
          minWidth: compatto ? 28 : 44, minHeight: compatto ? 28 : 44,
          padding: compatto ? "2px 6px" : "10px 14px",
          border: "1px solid #f3cfc8", borderRadius: 8, background: "#fbe6e2",
          color: "#8f3829", fontSize: compatto ? 10 : 13, fontWeight: 800, cursor: "pointer",
        }}
      >
        <AlertTriangle size={compatto ? 11 : 16} />
        {!compatto && "Segnala guasto"}
      </button>

      {aperto && (
        <div onClick={() => setAperto(false)}
          style={{ position: "fixed", inset: 0, background: "rgba(42,51,41,0.55)", zIndex: 400,
            display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
          <div onClick={(e) => e.stopPropagation()}
            style={{ background: "#fffefb", borderRadius: 20, padding: 20, width: "100%", maxWidth: 380,
              boxShadow: "0 24px 70px rgba(42,51,41,.35)" }}>
            <h3 style={{ margin: "0 0 6px", fontSize: 18, fontWeight: 800, color: "#2a3329" }}>
              Guasto su {attrezzatura}
            </h3>
            <p style={{ margin: "0 0 14px", fontSize: 13, color: "#6b7669" }}>
              Registro l'anomalia e ti porto subito all'elenco dei lotti che sono
              dentro, così li sposti in un altro apparecchio.
            </p>
            <textarea
              value={descrizione}
              onChange={(e) => setDescrizione(e.target.value)}
              placeholder="Cosa è successo? (es. non raffredda più, sportello rotto)"
              style={{ width: "100%", minHeight: 84, padding: "10px 12px", fontSize: 14,
                border: "2px solid #e6e0d4", borderRadius: 12, boxSizing: "border-box",
                fontFamily: "inherit", resize: "vertical" }}
            />
            <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
              <button onClick={() => setAperto(false)}
                style={{ flex: 1, padding: 13, borderRadius: 12, border: "1.5px solid #e6e0d4",
                  background: "#fffefb", fontSize: 14, fontWeight: 700, color: "#6b7669", cursor: "pointer" }}>
                Annulla
              </button>
              <button onClick={segnala} disabled={invio}
                style={{ flex: 2, padding: 13, borderRadius: 12, border: "none", background: "#d35f4e",
                  color: "#fff", fontSize: 14, fontWeight: 800, cursor: invio ? "wait" : "pointer",
                  opacity: invio ? 0.6 : 1 }}>
                {invio ? "Registro…" : "Segnala e sposta i lotti"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
