// Card «Registri HACCP» del tablet: il responsabile HACCP (ruolo sulla
// scheda HR) apre qui, col suo PIN, le stesse pagine del gestionale per
// registri, anomalie, conformità e frigoriferi. Nessuna copia: sono le
// pagine del gestionale, e il backend ricontrolla il ruolo a ogni scrittura.
import { useState } from "react";
import { ShieldAlert } from "lucide-react";
import {
  AnomalieView, SanificazioneView, TemperatureNegativeView, TemperaturePositiveView,
} from "..";
import AttrezzatureView from "../AttrezzatureView";
import ErrorBoundary from "../../ErrorBoundary";
import { MOTIVO_NON_PERMESSO, puo } from "../../../utils/permessiRuolo";
import { vaiAiReparti } from "./BarraReparto";

export const SEZIONI_REGISTRI = [
  { id: "frigo", label: "Frigoriferi", render: () => <TemperaturePositiveView /> },
  { id: "congelatori", label: "Congelatori", render: () => <TemperatureNegativeView /> },
  { id: "anomalie", label: "Anomalie", render: () => <AnomalieView /> },
  { id: "sanificazione", label: "Sanificazione", render: () => <SanificazioneView /> },
  { id: "apparecchi", label: "Apparecchi", render: () => <AttrezzatureView /> },
];

export default function RegistriHaccpTablet() {
  const [sezione, setSezione] = useState(SEZIONI_REGISTRI[0].id);

  if (!puo("haccp_registri")) {
    return (
      <div role="alert" style={{ maxWidth: 520, margin: "48px auto", padding: 24, background: "#fffefb", border: "1px solid #e6e0d4", borderRadius: 16, textAlign: "center", color: "#2a3329" }}>
        <ShieldAlert size={36} color="#c4894a" aria-hidden="true" />
        <h2 style={{ margin: "10px 0 6px", fontSize: 20, fontWeight: 800 }}>Registri HACCP</h2>
        <p style={{ margin: "0 0 16px", fontSize: 15 }}>{MOTIVO_NON_PERMESSO.haccp_registri}. Le temperature del giorno si registrano dal proprio reparto.</p>
        <button type="button" onClick={vaiAiReparti}
          style={{ minHeight: 48, padding: "0 20px", borderRadius: 12, border: "none", background: "#5b7a6b", color: "#fff", fontWeight: 800, fontSize: 15, fontFamily: "inherit", cursor: "pointer" }}>
          Torna ai reparti
        </button>
      </div>
    );
  }

  const attiva = SEZIONI_REGISTRI.find((s) => s.id === sezione) || SEZIONI_REGISTRI[0];
  return (
    <div style={{ minHeight: "100vh", background: "#faf7f0" }}>
      <div role="tablist" aria-label="Registri HACCP" style={{ display: "flex", gap: 8, flexWrap: "wrap", padding: "12px 16px 0" }}>
        {SEZIONI_REGISTRI.map((s) => (
          <button key={s.id} type="button" role="tab" aria-selected={s.id === attiva.id} onClick={() => setSezione(s.id)}
            style={{
              minHeight: 48, padding: "0 18px", borderRadius: 12, fontWeight: 800, fontSize: 15, fontFamily: "inherit", cursor: "pointer",
              border: `1px solid ${s.id === attiva.id ? "#3f5a4e" : "#e6e0d4"}`,
              background: s.id === attiva.id ? "#5b7a6b" : "#fffefb", color: s.id === attiva.id ? "#fff" : "#2a3329",
            }}>
            {s.label}
          </button>
        ))}
      </div>
      <div style={{ padding: "12px 16px" }}>
        <ErrorBoundary key={attiva.id}>{attiva.render()}</ErrorBoundary>
      </div>
    </div>
  );
}
