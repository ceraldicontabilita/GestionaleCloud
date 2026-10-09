// App principale — dopo la fase 2 della ristrutturazione (24/07/2026) qui
// restano SOLO: inizializzazione, stato condiviso (dati),
// aggancio del router e provider globali (toast, conferme, tour).
// La navigazione vive in config/ + hooks/useAppNavigation, il layout in
// layouts/, le pagine in router/pages.jsx, il kiosk in layouts/KioskLayout.
import { EVENTO_RICERCA_LOTTI } from "./utils/apriLotti";
import { useState, useEffect } from "react";
import axios from "axios";
import "@/App.css";
import { Toaster } from "sonner";
import { FileText, X } from "lucide-react";

import AppRouter from "./router/AppRouter";
import AppLayout from "./layouts/AppLayout";
import { renderPagina } from "./router/pages";
import { useAppNavigation } from "./hooks/useAppNavigation";
import ConfermaHost from "./components/haccp/shared/ConfermaHost";
import TourInterattivo, { TOUR_LS_KEY } from "./components/haccp/TourInterattivo";

// Hook dati condivisi
import { useStats } from "./hooks/useStats";
import { useRicette } from "./hooks/useRicette";
import { useLotti } from "./hooks/useLotti";
import { useFornitori } from "./hooks/useFornitori";

// ── UI primitivo condiviso (storico; usato da pagine legacy) ───────────────
export const Modal = ({ isOpen, onClose, title, children }) => {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-auto">
        <div className="flex items-center justify-between p-3 border-b bg-gray-50 rounded-t-2xl">
          <h2 className="text-lg font-bold text-gray-800">{title}</h2>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-200 rounded-lg">
            <X size={18} />
          </button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
};

function App() {
  const [loading, setLoading] = useState(true);
  const { activeTab, setActiveTab, handleTabChange } = useAppNavigation();
  const [tourOpen, setTourOpen] = useState(false);
  useEffect(() => {
    // Auto-avvio al primo accesso (utile per nuove pasticcerie); poi non si ripropone.
    let visto = "1";
    try { visto = localStorage.getItem(TOUR_LS_KEY); } catch { /* no-op */ }
    if (!visto) {
      const t = setTimeout(() => setTourOpen(true), 800);
      return () => clearTimeout(t);
    }
  }, []);
  const [filtroSoloScaduti, setFiltroSoloScaduti] = useState(false);
  const [ordiniPendenti, setOrdiniPendenti] = useState(0);

  // Modalità Laboratorio rimossa: la produzione veloce e ora dentro le card del kiosk tablet.
  // Pulizia per eventuali utenti rimasti col flag attivo in localStorage.
  if (localStorage.getItem("modo_laboratorio") === "1") localStorage.setItem("modo_laboratorio", "0");

  const { stats, fetchStats } = useStats();
  const { fetchRicette } = useRicette();
  const {
    lotti, searchLotti, setSearchLotti,
    filtroDataDaLotti, setFiltroDataDaLotti,
    filtroDataALotti, setFiltroDataALotti,
    fetchLotti, notifyLottiChanged,
  } = useLotti();
  const { fornitori, fetchFornitori } = useFornitori();

  // Deep-link da Controllo Dati: apre Lotti con la ricerca già compilata
  // sul lotto segnalato (chiave scritta da ControlloDatiView.apriCampione)
  useEffect(() => {
    const applica = () => {
      let s = null;
      try { s = sessionStorage.getItem("lotti_search"); sessionStorage.removeItem("lotti_search"); } catch { /* no-op */ }
      if (s) setSearchLotti(s);
    };
    if (activeTab === "lotti") applica();
    // Serve anche l'evento: se si è GIÀ su Lotti l'hash non cambia, activeTab
    // non cambia e senza questo il salto sembrava non fare nulla (25/07/2026).
    window.addEventListener(EVENTO_RICERCA_LOTTI, applica);
    return () => window.removeEventListener(EVENTO_RICERCA_LOTTI, applica);
  }, [activeTab, setSearchLotti]);

  // Badge ordini pendenti
  useEffect(() => {
    const API_URL = process.env.REACT_APP_LOTTI_BACKEND_URL + "/api";
    const fetch_count = () => axios.get(`${API_URL}/ordini-fornitori/count-pendenti`).then(r => setOrdiniPendenti(r.data.count || 0)).catch(() => {});
    fetch_count();
    const timer = setInterval(fetch_count, 30000);
    // Aggiornamento immediato su eventi ordine
    const onOrdineUpdate = () => fetch_count();
    window.addEventListener("ordini_pendenti_update", onOrdineUpdate);
    return () => { clearInterval(timer); window.removeEventListener("ordini_pendenti_update", onOrdineUpdate); };
  }, []);

  // Caricamento iniziale — mostra SUBITO l'app, i dati arrivano in background
  // (ogni sezione gestisce il proprio stato di caricamento). Apertura immediata.
  useEffect(() => {
    setLoading(false);
    fetchStats();
    fetchRicette();
    fetchLotti();
    fetchFornitori();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshAll = () =>
    Promise.all([fetchStats(), fetchRicette(), fetchLotti(), fetchFornitori()]);

  if (loading) {
    return (
      <div className="g-loading-screen">
        <div className="g-loading-logo">
          <FileText color="#fff" size={28} />
        </div>
        <div className="g-loading-spinner" />
        <p className="g-loading-text">Caricamento gestionale…</p>
      </div>
    );
  }

  // Stato e callback condivisi con le pagine (router/pages.jsx)
  const ctx = {
    stats, refreshAll, setActiveTab, handleTabChange,
    fornitori, fetchFornitori,
    lotti, notifyLottiChanged,
    searchLotti, setSearchLotti,
    filtroDataDaLotti, setFiltroDataDaLotti,
    filtroDataALotti, setFiltroDataALotti,
    filtroSoloScaduti, setFiltroSoloScaduti,
  };

  return (
    <>
      <Toaster position="top-right" richColors />
      <ConfermaHost />
      <AppLayout
        activeTab={activeTab}
        onTabChange={handleTabChange}
        ordiniPendenti={ordiniPendenti}
        onSupervisoreNavigate={(route, alertId) => {
          if (route?.startsWith("tablet/")) { window.location.hash = route; return; }
          if (route) handleTabChange(route);
          if (route === "lotti" && alertId === "A3") setFiltroSoloScaduti(true);
          else setFiltroSoloScaduti(false);
        }}
      >
        {renderPagina(activeTab, ctx)}
      </AppLayout>
      {/* Tour guidato passo-passo */}
      {tourOpen && (
        <TourInterattivo
          onNavigate={(tab) => setActiveTab(tab)}
          onClose={() => setTourOpen(false)}
        />
      )}
      {!tourOpen && (
        <button
          onClick={() => setTourOpen(true)}
          title="Tour guidato"
          aria-label="Avvia il tour guidato"
          style={{
            // Su #ordini c'è la barra Compra/Carrello/Da inviare fissa in basso:
            // il bottone si alza per non coprire il tab "Compra" (audit 24/07/2026).
            position: "fixed", left: 16, bottom: activeTab === "ordini" ? 84 : 16, zIndex: 3500,
            width: 46, height: 46, borderRadius: "50%", border: "none", cursor: "pointer",
            background: "linear-gradient(135deg,#3f5a4e,#5b7a6b)", color: "#fff",
            fontSize: 20, fontWeight: 800, boxShadow: "0 8px 22px rgba(63,90,78,.45)",
          }}
        >
          ?
        </button>
      )}
    </>
  );
}

// Radice esportata: router kiosk/app (AppComponent come prop per evitare
// l'import circolare AppRouter ↔ App)
export default function Root() {
  return <AppRouter AppComponent={App} />;
}
