import { useState, useEffect } from "react";
import axios from "axios";
import { API } from "../../../utils/constants";

const BADGE = [
  { key: "kcal",   label: "Calorie",      unit: "kcal", color: "var(--danger)", bg: "#fef2f2" },
  { key: "prot",   label: "Proteine",     unit: "g",    color: "var(--info)", bg: "var(--info-soft)" },
  { key: "carb",   label: "Carboidrati",  unit: "g",    color: "var(--warning)", bg: "#fffbeb" },
  { key: "grassi", label: "Grassi",       unit: "g",    color: "#c4894a", bg: "#f7ecdc" },
];

export default function TabNutrizionali({ ricettaId }) {
  const [dati, setDati]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [errore, setErrore]  = useState(null);

  useEffect(() => {
    if (!ricettaId) return;
    setLoading(true);
    setErrore(null);
    axios.get(`${API}/ricette/${ricettaId}/nutrizionali`)
      .then(r => setDati(r.data))
      .catch(() => setErrore("Impossibile calcolare i valori nutrizionali per questa ricetta."))
      .finally(() => setLoading(false));
  }, [ricettaId]);

  if (loading) return (
    <div style={{ padding: 40, textAlign: "center", color: "#9aa593" }}>Calcolo in corso...</div>
  );

  if (errore) return (
    <div style={{ padding: 20, color: "var(--danger-dark)", background: "#fef2f2", borderRadius: 10, margin: 16 }}>{errore}</div>
  );

  if (!dati) return null;

  const copertura = dati.ingredienti_totali > 0
    ? Math.round((dati.ingredienti_coperti / dati.ingredienti_totali) * 100)
    : 0;

  return (
    <div style={{ padding: "16px 0" }}>
      {/* Intestazione */}
      <div style={{ marginBottom: 16, padding: "0 4px" }}>
        <p style={{ margin: 0, fontSize: 13, fontWeight: 700, color: "#2a3329" }}>
          Valori Nutrizionali per Porzione
        </p>
        <p style={{ margin: "2px 0 0", fontSize: 11, color: "#9aa593" }}>
          Stima su {dati.ingredienti_coperti}/{dati.ingredienti_totali} ingredienti mappati ({copertura}% copertura) · {dati.porzioni} pz/ricetta
        </p>
      </div>

      {/* 4 badge grandi */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 16 }}>
        {BADGE.map(b => {
          const val = dati.per_porzione?.[b.key] ?? 0;
          return (
            <div key={b.key} style={{
              background: b.bg,
              border: `1.5px solid ${b.color}30`,
              borderRadius: 12,
              padding: "12px 14px",
              textAlign: "center",
            }}>
              <p style={{ margin: 0, fontSize: 22, fontWeight: 800, color: b.color }}>
                {val.toFixed(1)}
              </p>
              <p style={{ margin: "2px 0 0", fontSize: 10, fontWeight: 700, color: b.color, opacity: 0.8, textTransform: "uppercase", letterSpacing: "0.5px" }}>
                {b.unit}
              </p>
              <p style={{ margin: "2px 0 0", fontSize: 11, color: "#6b7669" }}>
                {b.label}
              </p>
            </div>
          );
        })}
      </div>

      {/* Barra macro */}
      {(() => {
        const p = dati.per_porzione || {};
        const protKcal = (p.prot   || 0) * 4;
        const carbKcal = (p.carb   || 0) * 4;
        const fatKcal  = (p.grassi || 0) * 9;
        const totMacro = protKcal + carbKcal + fatKcal || 1;
        return (
          <div style={{ marginBottom: 16 }}>
            <p style={{ margin: "0 0 6px", fontSize: 11, fontWeight: 700, color: "#6b7669" }}>
              Distribuzione macronutrienti
            </p>
            <div style={{ display: "flex", borderRadius: 8, overflow: "hidden", height: 18 }}>
              <div style={{ width: `${Math.round(protKcal/totMacro*100)}%`, background: "var(--info)" }} title={`Proteine ${Math.round(protKcal/totMacro*100)}%`} />
              <div style={{ width: `${Math.round(carbKcal/totMacro*100)}%`, background: "var(--warning)" }} title={`Carboidrati ${Math.round(carbKcal/totMacro*100)}%`} />
              <div style={{ width: `${Math.round(fatKcal/totMacro*100)}%`,  background: "#c4894a" }} title={`Grassi ${Math.round(fatKcal/totMacro*100)}%`} />
            </div>
            <div style={{ display: "flex", gap: 12, marginTop: 4 }}>
              {[
                { label: "Prot", pct: Math.round(protKcal/totMacro*100), color: "var(--info)" },
                { label: "Carb", pct: Math.round(carbKcal/totMacro*100), color: "var(--warning)" },
                { label: "Gras", pct: Math.round(fatKcal/totMacro*100),  color: "#c4894a" },
              ].map(m => (
                <span key={m.label} style={{ fontSize: 10, color: m.color, fontWeight: 700 }}>
                  {m.label} {m.pct}%
                </span>
              ))}
            </div>
          </div>
        );
      })()}

      {/* Dettaglio per ingrediente */}
      {dati.dettaglio?.length > 0 && (
        <div>
          <p style={{ margin: "0 0 8px", fontSize: 11, fontWeight: 700, color: "#6b7669" }}>
            Dettaglio ingredienti calcolati
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {dati.dettaglio.sort((a, b) => b.kcal - a.kcal).map((ing, i) => (
              <div key={i} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "5px 10px", background: "#f7f4ec", borderRadius: 7,
                fontSize: 12,
              }}>
                <span style={{ color: "#2a3329", textTransform: "capitalize", fontWeight: 500 }}>{ing.nome}</span>
                <span style={{ color: "#6b7669" }}>{ing.grammi}g</span>
                <span style={{ color: "var(--danger)", fontWeight: 700 }}>{ing.kcal} kcal</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <p style={{ margin: "12px 0 0", fontSize: 10, color: "#c7cfc2", textAlign: "center" }}>
        {dati.nota}
      </p>
    </div>
  );
}
