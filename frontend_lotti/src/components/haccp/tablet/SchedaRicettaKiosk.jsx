/**
 * tablet/SchedaRicettaKiosk.jsx — «Vedi la ricetta» dal tablet.
 *
 * Enzo 25/07/2026: «il dipendente deve solo produrre e vedere le ricette, tutto
 * il resto lo guardo io e lo utilizzo io».
 *
 * Prima la matita sulla card portava a #ricette, cioè al Backoffice del
 * gestionale: da quando il gestionale è riservato al titolare, per un
 * dipendente quel bottone finiva contro il tastierino. Qui la ricetta si legge
 * e basta: ingredienti con le dosi, resa, conservazione, allergeni, note.
 * Il moltiplicatore calcola la dose di lavoro senza modificare la ricetta.
 */
import { useEffect, useState } from "react";
import axios from "axios";
import { X, ChefHat, AlertTriangle, Pencil } from "lucide-react";
import { API } from "../../../utils/constants";
import { apiError } from "../../../utils/apiError";
import ModificaRicettaKiosk from "./ModificaRicettaKiosk";
import DosiRicetta from "../shared/DosiRicetta";

const C = {
  crema: "#faf7f0", card: "#fffefb", bordo: "#e6e0d4",
  testo: "#2a3329", tenue: "#6b7669", salvia: "#5b7a6b", sabbia: "#8a6f47",
};

export default function SchedaRicettaKiosk({ ricettaId, nome, onClose, modificabile = false, onSalvato }) {
  const [ricetta, setRicetta] = useState(null);
  const [errore, setErrore] = useState("");
  const [caricando, setCaricando] = useState(true);
  const [modifica, setModifica] = useState(false);

  useEffect(() => {
    let vivo = true;
    setCaricando(true);
    setErrore("");
    axios.get(`${API}/ricette/${ricettaId}`)
      .then((r) => { if (vivo) setRicetta(r.data || null); })
      .catch((e) => { if (vivo) setErrore(apiError(e, "Ricetta non trovata")); })
      .finally(() => { if (vivo) setCaricando(false); });
    return () => { vivo = false; };
  }, [ricettaId]);

  const allergeni = Array.isArray(ricetta?.allergeni) ? ricetta.allergeni.filter(Boolean) : [];
  const procedimento = ricetta?.procedimento_testo || ricetta?.procedimento || ricetta?.preparazione || ricetta?.metodo_preparazione || "";

  return (
    <div
      onClick={() => { if (!modifica) onClose(); }}
      style={{
        position: "fixed", inset: 0, background: "rgba(28,38,32,.6)", zIndex: 500,
        display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: C.crema, borderRadius: 22, width: "100%", maxWidth: 520,
          maxHeight: "88vh", overflowY: "auto", boxShadow: "0 24px 70px rgba(28,38,32,.45)",
        }}
      >
        <div style={{
          position: "sticky", top: 0, zIndex: 2,
          background: "linear-gradient(135deg,#6f9180,#4f6d5f)", color: "#fff",
          padding: "16px 18px", display: "flex", alignItems: "center", gap: 12,
          borderRadius: "22px 22px 0 0",
        }}>
          <ChefHat size={22} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 18, fontWeight: 900, lineHeight: 1.2, textTransform: "capitalize" }}>
              {ricetta?.nome || nome || "Ricetta"}
            </div>
            <div style={{ fontSize: 12, opacity: .85, marginTop: 2 }}>
              {modifica ? "Modifica ricetta ufficiale" : modificabile ? "Scheda ricetta — puoi modificarla qui" : "Scheda di lettura"}
            </div>
          </div>
          {modificabile && ricetta && !modifica && (
            <button onClick={() => setModifica(true)} aria-label="Modifica ricetta"
              style={{
                minHeight: 44, borderRadius: 12, border: "1px solid rgba(255,255,255,.35)",
                background: "rgba(255,255,255,.18)", color: "#fff", cursor: "pointer",
                padding: "0 12px", display: "inline-flex", alignItems: "center", gap: 6,
                fontFamily: "inherit", fontWeight: 800,
              }}>
              <Pencil size={16} /> Modifica
            </button>
          )}
          <button onClick={onClose} aria-label="Chiudi"
            style={{
              minWidth: 44, minHeight: 44, borderRadius: 12, border: "none",
              background: "rgba(255,255,255,.18)", color: "#fff", cursor: "pointer",
              display: "inline-flex", alignItems: "center", justifyContent: "center",
            }}>
            <X size={20} />
          </button>
        </div>

        <div style={{ padding: 18 }}>
          {caricando && (
            <p style={{ margin: 0, textAlign: "center", color: C.tenue, fontSize: 14, padding: "30px 0" }}>
              Carico la ricetta…
            </p>
          )}

          {!caricando && errore && (
            <p style={{ margin: 0, textAlign: "center", color: "#8f3829", fontSize: 14, padding: "24px 0" }}>
              {errore}
            </p>
          )}

          {!caricando && !errore && ricetta && (
            modifica ? (
              <ModificaRicettaKiosk
                ricetta={ricetta}
                onAnnulla={() => setModifica(false)}
                onSalvata={(aggiornata) => {
                  setRicetta(aggiornata);
                  setModifica(false);
                  onSalvato?.(aggiornata);
                }}
              />
            ) : <>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
                {ricetta.porzioni && ricetta.resa_verificata ? (
                  <Etichetta testo={`Resa: ${ricetta.porzioni} pezzi`} />
                ) : null}
                {ricetta.reparto ? <Etichetta testo={ricetta.reparto} /> : null}
                {ricetta.metodo_conservazione ? (
                  <Etichetta testo={`Conservazione: ${ricetta.metodo_conservazione}`} />
                ) : null}
              </div>

              <h3 style={{ margin: "0 0 8px", fontSize: 15, fontWeight: 900, color: C.testo }}>
                Ingredienti
              </h3>
              <DosiRicetta ricetta={ricetta} />

              {allergeni.length > 0 && (
                <>
                  <h3 style={{ margin: "18px 0 8px", fontSize: 15, fontWeight: 900, color: C.testo }}>
                    Allergeni
                  </h3>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
                    {allergeni.map((a) => (
                      <span key={a} style={{
                        display: "inline-flex", alignItems: "center", gap: 5,
                        background: "#fdf4e6", border: "1px solid #e8d5b0", color: "#8a6f47",
                        borderRadius: 999, padding: "5px 11px", fontSize: 12.5, fontWeight: 800,
                      }}>
                        <AlertTriangle size={12} /> {a}
                      </span>
                    ))}
                  </div>
                </>
              )}

              {procedimento ? (
                <>
                  <h3 style={{ margin: "18px 0 8px", fontSize: 15, fontWeight: 900, color: C.testo }}>
                    Modo di preparazione
                  </h3>
                  <p style={{
                    margin: 0, background: C.card, border: `1px solid ${C.bordo}`, borderRadius: 12,
                    padding: 13, fontSize: 14, color: C.testo, lineHeight: 1.55, whiteSpace: "pre-wrap",
                  }}>
                    {procedimento}
                  </p>
                </>
              ) : null}

              {ricetta.note ? (
                <>
                  <h3 style={{ margin: "18px 0 8px", fontSize: 15, fontWeight: 900, color: C.testo }}>
                    Note di lavorazione
                  </h3>
                  <p style={{
                    margin: 0, background: C.card, border: `1px solid ${C.bordo}`, borderRadius: 12,
                    padding: 13, fontSize: 14, color: C.testo, lineHeight: 1.55, whiteSpace: "pre-wrap",
                  }}>
                    {ricetta.note}
                  </p>
                </>
              ) : null}

              <p style={{ margin: "18px 0 0", fontSize: 12.5, color: C.tenue, lineHeight: 1.5 }}>
                Il calcolo vale solo per questa lavorazione. La ricetta ufficiale non cambia.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Etichetta({ testo }) {
  return (
    <span style={{
      background: "#f2f6f3", border: "1px solid #cfdfd5", color: "#3f5a4e",
      borderRadius: 999, padding: "5px 12px", fontSize: 12.5, fontWeight: 800,
      textTransform: "capitalize",
    }}>
      {testo}
    </span>
  );
}
