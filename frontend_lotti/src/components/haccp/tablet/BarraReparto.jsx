// Barra fissa di ogni reparto del tablet: sempre gli stessi comandi, nello
// stesso posto, qualunque pagina ci sia sotto (audit 26/09/2026: ogni vista
// aveva il suo «← Reparti», qualcuna nessun modo di tornare indietro, e dal
// tablet non c'era un «Torna al Gestionale» per il titolare).
//
// Indietro · Reparti · Gestionale (solo titolare) · chi è entrato · Cambia operatore
import { ArrowLeft, LayoutGrid, LayoutDashboard, LogOut, User } from "lucide-react";
import { logout, setGateOk } from "../../../auth";
import { clearTabletSession, getTabletSession, sessioneTitolareAttiva } from "../../../utils/tabletSession";

const stileBottone = {
  minHeight: 44,
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  padding: "0 14px",
  borderRadius: 12,
  border: "1px solid #e6e0d4",
  background: "#fffefb",
  color: "#2a3329",
  fontWeight: 800,
  fontSize: 14,
  cursor: "pointer",
  fontFamily: "inherit",
};

export function vaiAiReparti() {
  window.location.hash = "tablet/home";
}

export function indietro() {
  // Senza storia (tablet appena acceso su un reparto) si torna ai reparti,
  // mai fuori dall'app.
  if (window.history.length > 1) window.history.back();
  else vaiAiReparti();
}

export function cambiaOperatore() {
  clearTabletSession();
  logout();
  vaiAiReparti();
}

export default function BarraReparto({ titolo }) {
  const sessione = getTabletSession();
  const titolare = sessione ? sessione.ruolo === "amministratore" : sessioneTitolareAttiva();

  const vaiAlGestionale = () => {
    setGateOk();
    window.location.hash = "dashboard";
    window.dispatchEvent(new Event("tablet-auth"));
  };

  return (
    <nav
      aria-label="Navigazione reparto"
      data-testid="barra-reparto"
      style={{
        position: "sticky", top: 0, zIndex: 60,
        display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
        padding: "8px 12px", background: "#faf7f0", borderBottom: "1px solid #e6e0d4",
      }}
    >
      <button type="button" onClick={indietro} style={stileBottone} aria-label="Indietro">
        <ArrowLeft size={18} aria-hidden="true" /> Indietro
      </button>
      <button type="button" onClick={vaiAiReparti} style={stileBottone}>
        <LayoutGrid size={18} aria-hidden="true" /> Reparti
      </button>
      {titolare && (
        <button type="button" onClick={vaiAlGestionale} style={{ ...stileBottone, background: "#5b7a6b", color: "#fff", borderColor: "#5b7a6b" }}>
          <LayoutDashboard size={18} aria-hidden="true" /> Gestionale
        </button>
      )}
      {titolo ? <span style={{ fontWeight: 800, color: "#3f5a4e", marginLeft: 4 }}>{titolo}</span> : null}
      <span style={{ flex: 1 }} />
      {sessione?.nome && (
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "#2a3329", fontWeight: 700, fontSize: 14 }}>
          <User size={16} aria-hidden="true" /> {sessione.nome}
        </span>
      )}
      <button type="button" onClick={cambiaOperatore} style={stileBottone}>
        <LogOut size={18} aria-hidden="true" /> Cambia operatore
      </button>
    </nav>
  );
}
