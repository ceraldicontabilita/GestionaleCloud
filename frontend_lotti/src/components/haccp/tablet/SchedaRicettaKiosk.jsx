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
 * Per cambiare le quantità della giornata c'è la card «Dose di oggi»; per
 * modificare la ricetta serve il PIN del titolare.
 */
import { useEffect, useState } from "react";
import axios from "axios";
import { X, ChefHat, AlertTriangle, Pencil } from "lucide-react";
import { API } from "../../../utils/constants";
import { apiError } from "../../../utils/apiError";
import ModificaRicettaKiosk from "./ModificaRicettaKiosk";

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

  // Le dosi stanno in `ingredienti_dettaglio`; `ingredienti` è solo l'elenco
  // dei nomi (ricette vecchie o compilate a mano).
  const dettaglio = Array.isArray(ricetta?.ingredienti_dettaglio) ? ricetta.ingredienti_dettaglio : [];
  const soloNomi = Array.isArray(ricetta?.ingredienti) ? ricetta.ingredienti : [];
  const righe = dettaglio.length
    ? dettaglio.map((i) => ({
        nome: i?.nome || "",
        dose: [i?.quantita, i?.unita_misura || i?.unita].filter((v) => v !== null && v !== undefined && v !== "").join(" "),
      }))
    : soloNomi.map((i) => ({ nome: typeof i === "string" ? i : (i?.nome || ""), dose: "" }));
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
                {ricetta.porzioni ? (
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
              {righe.length === 0 ? (
                <p style={{
                  margin: 0, padding: 14, background: C.card, border: `1px dashed ${C.bordo}`,
                  borderRadius: 12, color: C.tenue, fontSize: 13.5, textAlign: "center",
                }}>
                  Questa ricetta non ha ancora gli ingredienti. Falli mettere al titolare.
                </p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {righe.map((r, i) => (
                    <div key={`${r.nome}-${i}`} style={{
                      display: "flex", alignItems: "center", gap: 10,
                      background: C.card, border: `1px solid ${C.bordo}`, borderRadius: 12,
                      padding: "11px 13px",
                    }}>
                      <span style={{ flex: 1, minWidth: 0, fontSize: 15, fontWeight: 700, color: C.testo, textTransform: "capitalize" }}>
                        {r.nome}
                      </span>
                      <span style={{ fontSize: 15, fontWeight: 900, color: r.dose ? C.salvia : "#b3aa9a", whiteSpace: "nowrap" }}>
                        {r.dose || "—"}
                      </span>
                    </div>
                  ))}
                </div>
              )}

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
                Devi produrre una quantità diversa da quella scritta qui? Usa la
                card <strong>«Dose di oggi»</strong>: cambi l'ingrediente
                principale e tutti gli altri si adeguano da soli. Per cambiare la
                ricetta serve il PIN del titolare.
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
