import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { API } from "../../../utils/constants";
import SchedaRicettaKiosk from "./SchedaRicettaKiosk";

export default function RicetteKioskView({ onBack }) {
  const [ricette, setRicette] = useState([]);
  const [cerca, setCerca] = useState("");
  const [scelta, setScelta] = useState(null);
  const [errore, setErrore] = useState("");
  const [caricando, setCaricando] = useState(true);

  useEffect(() => {
    let attivo = true;
    axios.get(`${API}/ricette`)
      .then(({ data }) => { if (attivo) setRicette(Array.isArray(data) ? data : []); })
      .catch(() => { if (attivo) setErrore("Non riesco a caricare le ricette."); })
      .finally(() => { if (attivo) setCaricando(false); });
    return () => { attivo = false; };
  }, []);

  const visibili = useMemo(() => ricette
    .filter((r) => r.visibile_tablet !== false && r.sola_lettura !== true)
    .filter((r) => r.visibile_tablet === true || !(r.ricettario_saima_id || r.ricettario_mepa_id || r.ricettario_acquaviva_id || r.ricettario_fornitore_id))
    .filter((r) => !r.acquistato && !r.rivendita && !r.fornitore_rivendita)
    .filter((r) => (r.nome || "").toLocaleLowerCase("it").includes(cerca.toLocaleLowerCase("it")))
    .sort((a, b) => (a.nome || "").localeCompare(b.nome || "", "it")), [ricette, cerca]);

  return <div style={{ minHeight: "100vh", background: "#faf7f0" }}>
    <header style={{ position: "sticky", top: 0, zIndex: 40, background: "#4f6d5f", color: "white", padding: "12px 16px", display: "flex", alignItems: "center", gap: 12 }}>
      <button onClick={onBack} style={{ minHeight: 44, border: 0, borderRadius: 10, padding: "0 14px", background: "#ffffff2e", color: "white", fontWeight: 800 }}>← Reparti</button>
      <strong>Ricette</strong>
    </header>
    <main style={{ maxWidth: 900, margin: "auto", padding: 16 }}>
      <input aria-label="Cerca ricetta" placeholder="Cerca ricetta…" value={cerca} onChange={(e) => setCerca(e.target.value)}
        style={{ width: "100%", boxSizing: "border-box", padding: 14, fontSize: 17, border: "1px solid #cfc6b4", borderRadius: 12, marginBottom: 16 }} />
      {caricando && <p>Carico le ricette…</p>}
      {errore && <p role="alert">{errore}</p>}
      {!caricando && !errore && visibili.length === 0 && <p>Nessuna ricetta trovata.</p>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(180px,1fr))", gap: 12 }}>
        {visibili.map((r) => <button key={r.id} onClick={() => setScelta(r)}
          style={{ padding: 18, minHeight: 92, textAlign: "left", border: "1px solid #e6e0d4", borderRadius: 14, background: "white", color: "#2a3329", fontSize: 16, fontWeight: 800 }}>
          {r.nome}
        </button>)}
      </div>
    </main>
    {scelta && <SchedaRicettaKiosk ricettaId={scelta.id} nome={scelta.nome} onClose={() => setScelta(null)} />}
  </div>;
}
