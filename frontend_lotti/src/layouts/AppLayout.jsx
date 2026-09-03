// Layout dell'app principale: header, barra di navigazione e cornice pagina.
// Estratto da App.js (fase 2 ristrutturazione 24/07/2026) — SOLO presentazione:
// stato e logica restano in App.js / useAppNavigation.
import { FileText, HelpCircle, LayoutDashboard, LogOut, ShoppingCart } from "lucide-react";
import { logout } from "../auth";
import { conferma } from "../utils/conferma";
import { HACCP_TABS, PRIMARY_TABS, SECONDARY_TABS } from "../config/navigation";
import { PAGE_META, PAGE_NAMES, TAB_HEADER_PROPRIO } from "../config/pageMeta";
import PageHeader from "../components/haccp/shared/PageHeader";
import Breadcrumb from "../components/haccp/Breadcrumb";
import HACCPPdfButton from "../components/haccp/HACCPPdfButton";
import { HACCPDropdown } from "../components/haccp/HACCPDropdown";
import { AltroDropdown } from "../components/haccp/AltroDropdown";
import { ImportDropdown } from "../components/haccp/ImportaFattureView";
import { SupervisoreBadge } from "../components/haccp/SupervisoreBadge";
import { RicercaGlobale } from "../components/haccp/RicercaGlobale";

// Icona Lucide per tab (da navigation.js): nelle intestazioni di pagina va
// preferita all'emoji di PAGE_META — le emoji rendono con colori di sistema
// non controllabili (es. blu su Android), contro il design system.
const TAB_ICONS = {};
[...PRIMARY_TABS, ...SECONDARY_TABS, ...HACCP_TABS].forEach((t) => { TAB_ICONS[t.id] = t.icon; });

const btnHeaderStyle = {
  display: "flex", alignItems: "center", gap: 6,
  background: "rgba(255,255,255,.12)", color: "#fff",
  border: "1px solid rgba(255,255,255,.25)", borderRadius: 10,
  padding: "7px 11px", fontSize: 13, fontWeight: 600, cursor: "pointer",
  flexShrink: 0,
};

export default function AppLayout({ activeTab, onTabChange, ordiniPendenti, onSupervisoreNavigate, children }) {
  return (
    <div style={{ minHeight: "100dvh", background: "var(--bg)" }}>
      {/* ── Header — .topbar stile app mobile ── */}
      <header className="g-app-header">
        {/* Logo + titolo */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 0 }}>
          <div style={{
            width: 40, height: 40, borderRadius: 12,
            background: "linear-gradient(135deg,#7d9b8b 0%,#5b7a6b 100%)",
            display: "grid", placeItems: "center", flexShrink: 0,
          }}>
            <FileText color="#fff" size={18} />
          </div>
          <div style={{ minWidth: 0, overflow: "hidden" }}>
            <div style={{ fontWeight: 700, fontSize: 16, letterSpacing: "-.01em", color: "#fff", lineHeight: 1.1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              Ceraldi Group
            </div>
            <div className="g-brand-sub" style={{ fontWeight: 500, opacity: .65, fontSize: 12, marginTop: 3, color: "#fff", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              Tracciabilità HACCP
            </div>
          </div>
        </div>

        {/* Azioni header */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          {activeTab !== "dashboard" && (
            <button
              onClick={() => onTabChange("dashboard")}
              title="Torna alla Home"
              data-testid="btn-home-dashboard"
              style={{
                display: "flex", alignItems: "center", gap: 6,
                background: "#fff", color: "#5b7a6b",
                border: "none", borderRadius: 10,
                padding: "8px 14px", fontSize: 14, fontWeight: 800, cursor: "pointer",
                whiteSpace: "nowrap", boxShadow: "0 2px 8px rgba(0,0,0,.18)",
              }}
            >
              <LayoutDashboard size={16} />
              Home
            </button>
          )}
          <HACCPDropdown tabsHACCP={HACCP_TABS} activeTab={activeTab} onTabChange={onTabChange} />
          <RicercaGlobale onNavigate={onTabChange} />
          <SupervisoreBadge onNavigate={onSupervisoreNavigate} />
          <button
            onClick={() => onTabChange("guida")}
            title="Apri la guida dell'applicazione"
            aria-label="Guida"
            data-testid="btn-guida-header"
            style={btnHeaderStyle}
          >
            <HelpCircle size={15} />
            <span className="g-header-btn-label" style={{ whiteSpace: "nowrap" }}>Guida</span>
          </button>
          <button
            onClick={async () => { if (await conferma("Uscire? Servirà di nuovo il PIN (o Google) per rientrare.")) logout(); }}
            title="Esci / blocca accesso"
            aria-label="Esci"
            style={btnHeaderStyle}
          >
            <LogOut size={15} />
            <span className="g-header-btn-label" style={{ whiteSpace: "nowrap" }}>Esci</span>
          </button>
        </div>
      </header>

      {/* ── Nav bar — scroll orizzontale tablet ── */}
      <nav className="g-nav-bar">
        <div className="g-nav-inner">
          {PRIMARY_TABS.map((tab) => (
            <button
              key={tab.id}
              data-tour={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={`g-nav-btn${activeTab === tab.id ? " active" : ""}`}
            >
              <tab.icon size={13} />
              {tab.label}
              {tab.id === "ordini" && ordiniPendenti > 0 && (
                <span className="g-nav-badge">{ordiniPendenti}</span>
              )}
            </button>
          ))}

          <AltroDropdown tabs={SECONDARY_TABS} activeTab={activeTab} onTabChange={onTabChange} />

          <div className="g-divider-v" style={{ margin: "0 6px" }} />
          <ImportDropdown activeTab={activeTab} onTabChange={onTabChange} />
          <HACCPPdfButton />
          <div className="g-divider-v" style={{ margin: "0 6px" }} />

          <a
            href={process.env.REACT_APP_GESTIONALE_URL || "https://www.impresasemplice.online"}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="nav-gestionale"
            className="g-gestionale-link"
          >
            <ShoppingCart size={13} />
            Gestionale
          </a>
        </div>
      </nav>

      {/* ── Contenuto ── */}
      <div className="g-page">
        <Breadcrumb />
        {/* Intestazione UNIFORME di pagina (stessa struttura ovunque, colore per pagina) */}
        {!TAB_HEADER_PROPRIO.has(activeTab) && PAGE_NAMES[activeTab] && (
          <PageHeader
            titolo={PAGE_NAMES[activeTab]}
            sottotitolo={(PAGE_META[activeTab] || {}).sub}
            icona={(() => {
              const Ico = TAB_ICONS[activeTab];
              return Ico ? <Ico size={26} color="#fff" /> : (PAGE_META[activeTab] || {}).icona;
            })()}
            colore={(PAGE_META[activeTab] || {}).colore}
          />
        )}
        {children}
      </div>
    </div>
  );
}
