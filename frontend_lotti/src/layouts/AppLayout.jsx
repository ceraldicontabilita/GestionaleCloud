// Layout dell'app principale: header, barra di navigazione e cornice pagina.
// Estratto da App.js (fase 2 ristrutturazione 24/07/2026) — SOLO presentazione:
// stato e logica restano in App.js / useAppNavigation.
import { ArrowLeft, FileText, HelpCircle, LogOut, Settings, ShieldCheck } from "lucide-react";
import SelettoreSezioni from "../components/shared/SelettoreSezioni";
import { isAdmin, logout } from "../auth";
import { conferma } from "../utils/conferma";
import { HACCP_TABS, IMPOSTAZIONI_TABS, PRIMARY_TABS, SECONDARY_TABS } from "../config/navigation";
import { PAGE_META, PAGE_NAMES, TAB_HEADER_PROPRIO } from "../config/pageMeta";
import PageHeader from "../components/haccp/shared/PageHeader";
import Breadcrumb from "../components/haccp/Breadcrumb";
import HACCPPdfButton from "../components/haccp/HACCPPdfButton";
import { HACCPDropdown } from "../components/haccp/HACCPDropdown";
import { AltroDropdown } from "../components/haccp/AltroDropdown";
import { SupervisoreBadge } from "../components/haccp/SupervisoreBadge";
import { RicercaGlobale } from "../components/haccp/RicercaGlobale";

// Icona Lucide per tab (da navigation.js): nelle intestazioni di pagina va
// preferita all'emoji di PAGE_META — le emoji rendono con colori di sistema
// non controllabili (es. blu su Android), contro il design system.
const TAB_ICONS = {};
[...PRIMARY_TABS, ...SECONDARY_TABS, ...HACCP_TABS, ...IMPOSTAZIONI_TABS].forEach((t) => { TAB_ICONS[t.id] = t.icon; });

const btnHeaderStyle = {
  display: "flex", alignItems: "center", gap: 6,
  background: "rgba(255,255,255,.12)", color: "#fff",
  border: "1px solid rgba(255,255,255,.25)", borderRadius: 10,
  padding: "7px 11px", fontSize: 13, fontWeight: 600, cursor: "pointer",
  flexShrink: 0,
};

export default function AppLayout({ activeTab, onTabChange, ordiniPendenti, onSupervisoreNavigate, children }) {
  const amministratore = isAdmin();
  return (
    <div style={{ minHeight: "100dvh", background: "var(--bg)" }}>
      {/* ── Header — .topbar stile app mobile ── */}
      <header className="g-app-header">
        {/* Sinistra: per primo il ritorno al Gestionale (solo titolare; il
            dipendente torna ai reparti), poi il logo che riporta alla Home. */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 0 }}>
          {amministratore ? (
            <a href="/" data-testid="btn-torna-gestionale" title="Torna al Gestionale" aria-label="Torna al Gestionale" style={{ ...btnHeaderStyle, background: "#fff", color: "#3f5a4e", border: "none", fontWeight: 800, textDecoration: "none", minHeight: 44 }}>
              <ArrowLeft size={16} aria-hidden="true" />
              Gestionale
            </a>
          ) : (
            <button onClick={() => { window.location.hash = "tablet/home"; }} style={{ ...btnHeaderStyle, minHeight: 44 }}>
              <ArrowLeft size={16} aria-hidden="true" />
              Reparti
            </button>
          )}
          <button
            type="button"
            onClick={() => onTabChange("dashboard")}
            data-testid="logo-home-lotti"
            aria-label="Home di Lotti"
            title="Home di Lotti"
            style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0, minHeight: 44, background: "none", border: "none", padding: 0, cursor: "pointer", fontFamily: "inherit", textAlign: "left" }}
          >
            <div style={{
              width: 40, height: 40, borderRadius: 12,
              background: "linear-gradient(135deg,#7d9b8b 0%,#5b7a6b 100%)",
              display: "grid", placeItems: "center", flexShrink: 0,
            }}>
              <FileText color="#fff" size={18} aria-hidden="true" />
            </div>
            <div className="g-brand-title" style={{ minWidth: 0, overflow: "hidden" }}>
              <div style={{ fontWeight: 700, fontSize: 16, letterSpacing: "-.01em", color: "#fff", lineHeight: 1.1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                Ceraldi Group
              </div>
              <div className="g-brand-sub" style={{ fontWeight: 500, opacity: .65, fontSize: 12, marginTop: 3, color: "#fff", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                Tracciabilità HACCP
              </div>
            </div>
          </button>
        </div>

        {/* Destra: azioni del titolare, ingranaggio Impostazioni sempre ultimo.
            Sul telefono le azioni scendono su una seconda riga e l'ingranaggio
            resta in testata accanto a «← Gestionale» (App.css). */}
        {amministratore && (
          <div className="g-header-azioni" style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
            <span data-testid="indicatore-amministratore" title="Amministratore" aria-label="Amministratore"
              style={{ display: "inline-flex", alignItems: "center", gap: 5, background: "rgba(255,255,255,.14)", color: "#fff", border: "1px solid rgba(255,255,255,.3)", borderRadius: 999, padding: "4px 10px", fontSize: 12, fontWeight: 800 }}>
              <ShieldCheck size={14} aria-hidden="true" />
              <span className="g-header-btn-label">Amministratore</span>
            </span>
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
              onClick={async () => { if (await conferma("Uscire da Lotti? Per rientrare si passa dal login del Gestionale.")) logout(); }}
              title="Esci / blocca accesso"
              aria-label="Esci"
              style={btnHeaderStyle}
            >
              <LogOut size={15} />
              <span className="g-header-btn-label" style={{ whiteSpace: "nowrap" }}>Esci</span>
            </button>
          </div>
        )}
        {amministratore && (
          <div className="g-header-ingranaggio" style={{ flexShrink: 0 }}>
            <AltroDropdown
              tabs={IMPOSTAZIONI_TABS}
              activeTab={activeTab}
              onTabChange={onTabChange}
              etichetta="Impostazioni"
              icona={Settings}
              nome="impostazioni"
              ariaLabel="Impostazioni e amministrazione"
              classeBottone="g-impostazioni-btn"
              stileBottone={{ ...btnHeaderStyle, minHeight: 44 }}
              classeEtichetta="g-header-btn-label"
              freccia={false}
            />
          </div>
        )}
      </header>

      {/* ── Nav bar — scroll orizzontale tablet ── */}
      {amministratore && <nav className="g-nav-bar">
        <div className="g-nav-inner">
          {PRIMARY_TABS.map((tab) => (
            <button
              key={tab.id}
              data-tour={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={`g-nav-btn${activeTab === tab.id ? " active" : ""}`}
              aria-current={activeTab === tab.id ? "page" : undefined}
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
          <HACCPPdfButton />
          <div className="g-divider-v" style={{ margin: "0 6px" }} />

          {/* Il Gestionale ha il suo bottone in testata: qui le altre app. */}
          <SelettoreSezioni sezioneCorrente="lotti" escludi={["gestionale"]} />
        </div>
      </nav>}

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
