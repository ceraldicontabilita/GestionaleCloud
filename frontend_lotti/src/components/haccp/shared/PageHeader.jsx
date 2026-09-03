// PageHeader.jsx — Intestazione di pagina UNIFORME per tutta l'app.
// Stessa struttura ovunque: fascia con icona + titolo + sottotitolo a sinistra,
// azioni a destra. Cambia solo il COLORE (per reparto o pagina), non il layout.
//
// Uso:
//   <PageHeader titolo="Ricette" sottotitolo="Crea e modifica ricette"
//               icona="🍰" reparto="pasticceria" azioni={<button>…</button>} />
//   <PageHeader titolo="Ordini fornitori" sottotitolo="…" colore="#5b7a6b" />

import { temaReparto } from "../../../utils/repartiColori";

export default function PageHeader({
  titolo,
  sottotitolo,
  icona,
  reparto,
  colore,      // gradiente o colore solido esplicito (ha precedenza sul reparto)
  azioni,
  compatta = false,
}) {
  const tema = temaReparto(reparto);
  const sfondo = colore || tema.grad;
  const emoji = icona || (reparto ? tema.emoji : "");

  return (
    <div
      style={{
        background: sfondo,
        borderRadius: 18,
        padding: compatta ? "16px 18px" : "22px 24px",
        marginBottom: 18,
        color: "#fff",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 14,
        flexWrap: "wrap",
        boxShadow: "0 8px 24px rgba(0,0,0,.14)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 14, minWidth: 0 }}>
        {emoji && (
          <div
            style={{
              width: compatta ? 42 : 52,
              height: compatta ? 42 : 52,
              borderRadius: 14,
              background: "rgba(255,255,255,.22)",
              display: "grid",
              placeItems: "center",
              fontSize: compatta ? 22 : 28,
              flexShrink: 0,
            }}
          >
            {emoji}
          </div>
        )}
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              fontWeight: 800,
              fontSize: compatta ? 20 : 26,
              lineHeight: 1.15,
              letterSpacing: "-.01em",
              textShadow: "0 1px 2px rgba(0,0,0,.15)",
            }}
          >
            {titolo}
          </div>
          {sottotitolo && (
            <div style={{ fontSize: 13, opacity: 0.9, marginTop: 4, fontWeight: 500 }}>
              {sottotitolo}
            </div>
          )}
        </div>
      </div>
      {azioni && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          {azioni}
        </div>
      )}
    </div>
  );
}
