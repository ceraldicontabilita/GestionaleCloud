// App principale — dopo la fase 2 della ristrutturazione (24/07/2026) qui
// restano SOLO: inizializzazione, stato condiviso (import fatture, dati),
// aggancio del router e provider globali (toast, conferme, tour).
// La navigazione vive in config/ + hooks/useAppNavigation, il layout in
// layouts/, le pagine in router/pages.jsx, il kiosk in layouts/KioskLayout.
import { EVENTO_RICERCA_LOTTI } from "./utils/apriLotti";
import { useState, useEffect } from "react";
import axios from "axios";
import { API } from "./utils/constants";
import JSZip from "jszip";
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

// ── Barra di importazione globale (fissa, persiste cambiando pagina) ────────
function BarraImport({ imp, onClose, onVai, onAnnulla }) {
  const [apri, setApri] = useState(false);
  if (!imp || (!imp.running && !imp.finished)) return null;
  const pct = imp.total ? Math.min(100, Math.round((imp.done / imp.total) * 100)) : (imp.running ? 6 : 100);
  const nErr = (imp.errori || []).length;
  const btn = { background: "rgba(255,255,255,.14)", border: "none", color: "#fff", padding: "7px 12px", borderRadius: 8, fontWeight: 700, fontSize: 12, cursor: "pointer" };
  return (
    <div style={{ position: "fixed", left: 0, right: 0, bottom: 0, zIndex: 10000, background: "#4a3f33", color: "#fff", boxShadow: "0 -2px 14px rgba(0,0,0,.28)" }}>
      <div style={{ height: 4, background: "rgba(255,255,255,.18)" }}>
        <div style={{ height: "100%", width: pct + "%", background: imp.running ? "#8a6f47" : (nErr ? "#c4894a" : "#3d8168"), transition: "width .3s" }} />
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 170 }}>
          <div style={{ fontWeight: 800, fontSize: 14 }}>
            {imp.running ? "Importazione fatture in corso…" : (nErr ? "Importazione completata con avvisi" : "Importazione completata")}
          </div>
          <div style={{ fontSize: 12, opacity: .85 }}>
            {imp.total ? `${imp.done}/${imp.total} file · ${imp.ok} salvate${imp.running && imp.fase ? ` · ${imp.fase}` : (nErr ? ` · ${nErr} avvisi` : "")}` : (imp.fase || "Lettura file…")}
          </div>
        </div>
        {imp.running && <div style={{ fontWeight: 800, fontSize: 16 }}>{pct}%</div>}
        {imp.running && (
          <button onClick={onAnnulla} style={{ ...btn, background: "#d35f4e", fontWeight: 800 }}>Annulla</button>
        )}
        {!imp.running && (
          <>
            {nErr > 0 && <button onClick={() => setApri(v => !v)} style={btn}>{apri ? "Nascondi avvisi" : "Vedi avvisi"}</button>}
            <button onClick={onVai} style={btn}>Vai alle fatture</button>
            <button onClick={onClose} style={{ ...btn, background: "#8a6f47", fontWeight: 800 }}>Chiudi</button>
          </>
        )}
      </div>
      {!imp.running && apri && nErr > 0 && (
        <div style={{ maxHeight: 160, overflowY: "auto", background: "rgba(0,0,0,.18)", padding: "8px 14px", fontSize: 11.5, lineHeight: 1.5 }}>
          {(imp.errori || []).slice(0, 300).map((e, i) => <div key={i} style={{ opacity: .9 }}>• {e}</div>)}
        </div>
      )}
    </div>
  );
}

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

  // ── Importazione fatture in background (continua anche cambiando pagina) ──
  const [imp, setImp] = useState({ running: false, total: 0, done: 0, ok: 0, errori: [], finished: false, fase: "" });

  function pollJob(jobId, onDone) {
    const base = process.env.REACT_APP_LOTTI_BACKEND_URL + "/api";
    const tick = async () => {
      let r = null;
      try {
        r = (await axios.get(`${base}/fatture/importa-job/${jobId}`, { timeout: 30000 })).data;
      } catch (e) { setTimeout(tick, 4000); return; }
      if (!r) { setTimeout(tick, 4000); return; }
      const fin = r.stato && r.stato !== "in_corso";
      setImp(s => ({
        ...s, jobId,
        total: r.total || s.total,
        done: r.processed || 0,
        ok: r.ok || 0,
        errori: (r.errori && r.errori.length) ? r.errori : s.errori,
        running: !fin,
        finished: !!fin,
        fase: fin ? (r.stato === "errore" ? "Errore sul server" : "Completato") : "Elaborazione sul server…",
      }));
      if (fin) { if (onDone) { try { onDone(); } catch (e) {} } return; }
      setTimeout(tick, 3000);
    };
    tick();
  }

  const startImport = async (fileList, onDone) => {
    const base = process.env.REACT_APP_LOTTI_BACKEND_URL + "/api";
    setImp({ running: true, total: 0, done: 0, ok: 0, errori: [], finished: false, fase: "Avvio del server…" });
    await axios.get(`${base}/fatture/stato-sync`, { timeout: 90000 }).catch(() => {});
    setImp(s => ({ ...s, fase: "Lettura file…" }));
    const xmls = [];
    for (const f of Array.from(fileList || [])) {
      const nl = (f.name || "").toLowerCase();
      if (nl.endsWith(".zip")) {
        try {
          const z = await JSZip.loadAsync(f);
          for (const path of Object.keys(z.files)) {
            const ent = z.files[path];
            const pl = path.toLowerCase();
            if (ent.dir || !(pl.endsWith(".xml") || pl.endsWith(".p7m"))) continue;
            const blob = await ent.async("blob");
            xmls.push(new File([blob], path.split("/").pop(), { type: "application/octet-stream" }));
          }
        } catch (e) { xmls.push(f); }
      } else {
        xmls.push(f);
      }
    }
    if (!xmls.length) { setImp(s => ({ ...s, running: false, finished: true, fase: "Nessun file XML trovato" })); return; }
    setImp(s => ({ ...s, total: xmls.length, fase: "Invio al server…" }));
    let jobId = null;
    try {
      const fd = new FormData();
      xmls.forEach(x => fd.append("files", x));
      const res = await axios.post(`${base}/fatture/importa-async`, fd, { timeout: 300000 });
      jobId = res.data && res.data.job_id;
    } catch (e) {
      setImp(s => ({ ...s, running: false, finished: true, fase: "Errore invio", errori: [...s.errori, "Invio al server fallito: " + ((e && e.message) || "")] }));
      return;
    }
    if (!jobId) { setImp(s => ({ ...s, running: false, finished: true, fase: "Errore avvio" })); return; }
    setImp(s => ({ ...s, jobId, fase: "Elaborazione sul server…" }));
    pollJob(jobId, onDone);
  };

  // Riprende la barra se un import è già in corso sul server (dopo reload o ritorno da background)
  useEffect(() => {
    const base = process.env.REACT_APP_LOTTI_BACKEND_URL + "/api";
    axios.get(`${base}/fatture/importa-job-attivo`, { timeout: 30000 }).then(r => {
      const j = r.data;
      if (j && j.id && j.stato === "in_corso") {
        setImp(s => ({ ...s, running: true, finished: false, jobId: j.id, total: j.total || 0, done: j.processed || 0, ok: j.ok || 0, errori: j.errori || [], fase: "Elaborazione sul server…" }));
        pollJob(j.id);
      }
    }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // Modalità Laboratorio rimossa: la produzione veloce e ora dentro le card del kiosk tablet.
  // Pulizia per eventuali utenti rimasti col flag attivo in localStorage.
  if (localStorage.getItem("modo_laboratorio") === "1") localStorage.setItem("modo_laboratorio", "0");

  const { stats, fetchStats } = useStats();
  const { fetchRicette } = useRicette();
  const {
    lotti, searchLotti, setSearchLotti,
    filtroDataDaLotti, setFiltroDataDaLotti,
    filtroDataALotti, setFiltroDataALotti,
    fetchLotti, handleDeleteLotto,
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
    imp, startImport,
    onImportComplete: () => Promise.all([fetchStats(), fetchFornitori()]),
    fornitori, fetchFornitori,
    lotti, handleDeleteLotto,
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
      <BarraImport imp={imp}
        onClose={() => setImp(s => ({ ...s, finished: false }))}
        onVai={() => handleTabChange("fatture")}
        onAnnulla={async () => {
          try { await axios.post(`${API}/fatture/importa-annulla`); } catch { /* ignore */ }
          setImp(s => ({ ...s, running: false, finished: false, fase: "Import annullato" }));
        }} />

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
