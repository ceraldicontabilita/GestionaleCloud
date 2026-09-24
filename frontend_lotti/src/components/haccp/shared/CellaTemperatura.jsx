import { useState } from "react";

// Condivisi da frigoriferi e congelatori: prima esistevano solo nella vista
// frigoriferi, e le temperature dei congelatori non si potevano registrare.
// Cella temperatura: click -> input -> salva. Risolve il fatto che le celle erano di sola lettura.
export function CellaTemperatura({ display, tempValue, disabled, onSave }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState("");
  const orig = tempValue === null || tempValue === undefined ? "" : String(tempValue);
  const commit = () => {
    setEditing(false);
    const v = val.replace(",", ".").trim();
    if (v !== "" && v !== orig) onSave(v);
  };
  if (editing) {
    return (
      <input
        type="number"
        step="0.1"
        autoFocus
        value={val}
        onChange={(e) => setVal(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") commit(); else if (e.key === "Escape") setEditing(false); }}
        onBlur={commit}
        className="h-6 w-full rounded border border-orange-400 bg-white text-center text-xs text-gray-900 outline-none"
      />
    );
  }
  return (
    <div
      onClick={() => { if (!disabled) { setVal(orig); setEditing(true); } }}
      className={`flex h-6 w-full items-center justify-center rounded text-xs ${disabled ? "" : "cursor-pointer hover:ring-2 hover:ring-orange-300"} ${display.className}`}
      title={disabled ? display.title : "Tocca per inserire / modificare la temperatura"}
    >
      {display.value}
    </div>
  );
}


// ── Modale azione correttiva (frigo fuori range) ───────────────────────────
export function ModalAzioneCorrettiva({ dati, onSalva, onChiudi, apparecchio = "Frigo", azioni }) {
  const [scelta, setScelta] = useState("");
  const [libero, setLibero] = useState("");
  const AZIONI = azioni || [
    "Merce spostata in altro frigo funzionante",
    "Chiamato tecnico di manutenzione",
    "Regolato/abbassato il termostato",
    "Prodotti deperibili eliminati",
    "Verificata chiusura porta / guarnizione",
  ];
  const azioneFinale = libero.trim() || scelta;
  return (
    <div onClick={onChiudi}
      style={{ position: "fixed", inset: 0, background: "rgba(31,27,46,.45)", display: "grid", placeItems: "center", zIndex: 9999, padding: 16 }}>
      <div onClick={(e) => e.stopPropagation()}
        style={{ width: "min(440px,95vw)", background: "#fffefb", borderRadius: 18, padding: 22, boxShadow: "0 20px 60px rgba(0,0,0,.3)", border: "1px solid #e6e0d4" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
          <span style={{ fontSize: 26 }}>⚠️</span>
          <h3 style={{ margin: 0, fontSize: 18, fontWeight: 800, color: "#d35f4e" }}>{apparecchio} fuori range: {dati.temperatura}°C</h3>
        </div>
        <p style={{ margin: "0 0 14px", fontSize: 13, color: "#6b6456", lineHeight: 1.4 }}>
          La legge (Reg. 852/2004) richiede di documentare <b>cosa è stato fatto</b>. Seleziona o scrivi l'azione correttiva.
        </p>
        <div style={{ display: "grid", gap: 8, marginBottom: 12 }}>
          {AZIONI.map((a) => (
            <button key={a} onClick={() => { setScelta(a); setLibero(""); }}
              style={{ textAlign: "left", padding: "10px 12px", borderRadius: 10, cursor: "pointer",
                border: `1.5px solid ${scelta === a ? "#5b7a6b" : "#e6e0d4"}`,
                background: scelta === a ? "#5b7a6b14" : "#fff", fontWeight: 600, fontSize: 14, color: "#384038" }}>
              {a}
            </button>
          ))}
        </div>
        <textarea value={libero} onChange={(e) => { setLibero(e.target.value); setScelta(""); }}
          placeholder="…oppure descrivi un'altra azione" rows={2}
          style={{ width: "100%", boxSizing: "border-box", padding: "10px 12px", borderRadius: 10, border: "1px solid #e6e0d4", fontSize: 14, resize: "vertical", marginBottom: 14 }} />
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button onClick={onChiudi}
            style={{ padding: "10px 16px", borderRadius: 10, border: "1px solid #e6e0d4", background: "#fff", fontWeight: 700, cursor: "pointer", color: "#6b6456" }}>
            Più tardi
          </button>
          <button onClick={() => azioneFinale && onSalva(azioneFinale)} disabled={!azioneFinale}
            style={{ padding: "10px 18px", borderRadius: 10, border: "none", background: azioneFinale ? "#5b7a6b" : "#cfc8ba", color: "#fff", fontWeight: 800, cursor: azioneFinale ? "pointer" : "not-allowed" }}>
            Registra azione
          </button>
        </div>
      </div>
    </div>
  );
}
