// repartiColori.js — Mappa colori reparto CENTRALIZZATA (single source of truth).
// Usata da PageHeader e da qualsiasi vista per dare lo stesso colore allo stesso
// reparto in tutta l'app. I COLORI cambiano, la STRUTTURA resta uniforme.

const TEMI = {
  pasticceria: {
    emoji: "🍰",
    label: "Pasticceria",
    solid: "#ea580c",
    grad: "linear-gradient(135deg,#fb923c,#ea580c)",
    soft: "#fff1e6",
    text: "#9a3412",
  },
  rosticceria: {
    emoji: "🥙",
    label: "Rosticceria",
    solid: "#16a34a",
    grad: "linear-gradient(135deg,#86efac,#16a34a)",
    soft: "#eafaf0",
    text: "#166534",
  },
  bar: {
    emoji: "☕",
    label: "Bar",
    solid: "#78350f",
    grad: "linear-gradient(135deg,#b45309,#78350f)",
    soft: "#f5efe6",
    text: "#78350f",
  },
  // Tema neutro per le pagine non legate a un reparto (sage brand dell'app).
  generale: {
    emoji: "📋",
    label: "Generale",
    solid: "#5b7a6b",
    grad: "linear-gradient(135deg,#7d9b8b,#5b7a6b)",
    soft: "#eef3f0",
    text: "#3f5a4e",
  },
};

/** Ritorna il tema del reparto (o quello generale se sconosciuto/assente). */
export function temaReparto(reparto) {
  const k = (reparto || "").toString().trim().toLowerCase();
  return TEMI[k] || TEMI.generale;
}

export const REPARTI_THEME = TEMI;
export default TEMI;
