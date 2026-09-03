/**
 * Breadcrumb — mostra il percorso di navigazione basato sul hash URL.
 * Esempio: Prodotti › SAIMA › Canditi
 * Si aggiorna automaticamente ad ogni cambio di hash.
 */
import { useState, useEffect } from "react";
import { ChevronRight, Home } from "lucide-react";

const LABELS = {
  // Tab principali
  dashboard:    "Dashboard",
  ricette:      "Ricettario",
  lotti:        "Lotti",
  fornitori:    "Fornitori",
  prodotti:     "Prodotti",
  ordini:       "Ordini",
  ingredienti:  "Ingredienti",
  tracciabilita:"Tracciabilità",
  haccp:        "HACCP",
  materie:      "Materie Prime",
  colazione:    "Colazione",
  backup:       "Backup",
  audit:        "Audit",
  // Sotto-tab prodotti
  acquaviva:        "Acquaviva",
  saima:            "SAIMA",
  mepa:             "MEPA",
  miei:             "Miei Prodotti",
  saima_ricettari:  "Ricettari SAIMA",
  // Sotto-tab ordini
  automatici: "Automatici",
  manuali:    "Manuali",
  storico:    "Storico",
};

/** Converte slug URL in label leggibile */
function slugToLabel(slug) {
  if (!slug) return null;
  if (LABELS[slug]) return LABELS[slug];
  // Slug categoria: "pane-e-panificati" → "Pane e Panificati"
  return slug.replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

export default function Breadcrumb() {
  const [segs, setSegs] = useState([]);

  const parseHash = () => {
    const raw = window.location.hash.replace("#", "");
    const parts = raw.split("/").filter(Boolean);
    setSegs(parts);
  };

  useEffect(() => {
    parseHash();
    window.addEventListener("hashchange", parseHash);
    return () => window.removeEventListener("hashchange", parseHash);
  }, []);

  if (segs.length <= 1) return null; // Nasconde se solo tab principale

  return (
    <div
      data-testid="breadcrumb"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 4,
        padding: "5px 16px",
        background: "#f8fafc",
        borderBottom: "1px solid #e2e8f0",
        fontSize: 12,
        color: "#64748b",
        overflowX: "auto",
        whiteSpace: "nowrap",
        flexShrink: 0,
      }}
    >
      <Home size={12} style={{ flexShrink: 0, color: "#94a3b8" }} />
      {segs.map((seg, i) => {
        const label = slugToLabel(seg);
        const isLast = i === segs.length - 1;
        // Costruisce il percorso parziale per il link
        const path = "#" + segs.slice(0, i + 1).join("/");
        return (
          <span key={i} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <ChevronRight size={11} style={{ color: "#cbd5e1", flexShrink: 0 }} />
            {isLast ? (
              <span style={{ fontWeight: 700, color: "#1e293b" }}>{label}</span>
            ) : (
              <a
                href={path}
                style={{ color: "var(--info)", textDecoration: "none", fontWeight: 500 }}
              >
                {label}
              </a>
            )}
          </span>
        );
      })}
    </div>
  );
}
