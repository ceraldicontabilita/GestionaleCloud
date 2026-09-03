import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { API } from "../../../utils/constants";
import { apiError } from "../../../utils/apiError";
import { stampaDoc } from "../../../utils/stampa";

// DOSE DI OGGI (richiesta Enzo 25/07/2026)
// Il pasticciere non tocca la ricetta ufficiale (bloccata): qui dice quanto
// ingrediente base usa oggi — 6,5 kg di farina per i cornetti, 3 kg di riso
// per gli arancini, 2 l di latte per la crema — e tutti gli altri ingredienti
// si adeguano da soli. Nessun salvataggio: è il conto per il banco di lavoro.

const PRESET_KG = [0.5, 1, 2, 3, 5, 6.5, 8, 10, 15, 20];

const fmt = (n) => {
  const v = Number(n) || 0;
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/\.?0+$/, "");
};

export default function DoseProduzioneView({ onBack }) {
  const [ricette, setRicette] = useState([]);
  const [caricando, setCaricando] = useState(true);
  const [cerca, setCerca] = useState("");
  const [sel, setSel] = useState(null);      // ricetta scelta
  const [qta, setQta] = useState(1);
  const [unita, setUnita] = useState("kg");
  const [esito, setEsito] = useState(null);  // {base, fattore, ingredienti, porzioni_stimate}
  const [calcolando, setCalcolando] = useState(false);

  useEffect(() => {
    axios.get(`${API}/ricette`)
      .then(r => setRicette((r.data || []).filter(x => (x.ingredienti_dettaglio || []).length)))
      .catch(() => toast.error("Non riesco a caricare le ricette"))
      .finally(() => setCaricando(false));
  }, []);

  const calcola = async (ricetta, quantita, um) => {
    if (!ricetta) return;
    setCalcolando(true);
    try {
      const r = await axios.post(`${API}/food-cost/ricetta/${ricetta.id}/dose-produzione`,
        { quantita_base: Number(quantita) || 0, unita: um });
      setEsito(r.data);
    } catch (e) {
      setEsito(null);
      toast.error(apiError(e, "Non riesco a calcolare la dose"));
    } finally { setCalcolando(false); }
  };

  const scegli = (r) => {
    setSel(r); setEsito(null); setQta(1); setUnita("kg");
    calcola(r, 1, "kg");
  };

  const cambiaQta = (nuova) => {
    const v = Math.max(0.1, Math.round(Number(nuova) * 100) / 100);
    setQta(v);
    calcola(sel, v, unita);
  };

  const stampaScheda = () => {
    if (!sel || !esito) return;
    const righe = esito.ingredienti
      .map(i => `<tr><td>${i.nome}</td><td style="text-align:right;font-weight:700">${fmt(i.quantita)} ${i.unita || i.unita_misura || "g"}</td></tr>`)
      .join("");
    const html = `<h2 style="font-family:sans-serif">${sel.nome}</h2>
      <p style="font-family:sans-serif">Dose di oggi: <b>${fmt(qta)} ${unita} di ${esito.base}</b>
      — circa ${esito.porzioni_stimate} pezzi</p>
      <table style="font-family:sans-serif;border-collapse:collapse;width:100%">${righe}</table>
      <p style="font-family:sans-serif;font-size:12px">Stampato il ${new Date().toLocaleString("it-IT")}</p>`;
    stampaDoc({ categoria: "manuale", html, formato: "html", titolo: `Dose ${sel.nome}` })
      .catch(() => toast.error("Stampa non riuscita"));
  };

  const filtrate = ricette
    .filter(r => !cerca || (r.nome || "").toLowerCase().includes(cerca.toLowerCase()))
    .sort((a, b) => (a.nome || "").localeCompare(b.nome || "", "it"));

  return (
    <div style={{ minHeight: "100vh", background: "#faf7f0" }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 12, padding: "12px 16px",
        background: "linear-gradient(135deg,#6f9180,#4f6d5f)", color: "#fff",
        boxShadow: "0 4px 16px rgba(0,0,0,.18)", position: "sticky", top: 0, zIndex: 40,
      }}>
        <button onClick={() => (sel ? (setSel(null), setEsito(null)) : onBack?.())}
          style={{ background: "rgba(255,255,255,.18)", border: "none", borderRadius: 10,
            padding: "8px 14px", color: "#fff", fontWeight: 800, fontSize: 14, cursor: "pointer", fontFamily: "inherit" }}>
          ← {sel ? "Ricette" : "Reparti"}
        </button>
        <span style={{ fontWeight: 900, fontSize: 16 }}>{sel ? sel.nome : "Dose di oggi"}</span>
      </div>

      <div style={{ padding: 14, maxWidth: 480, margin: "0 auto" }}>
        {!sel && (
          <>
            <p style={{ fontSize: 13, color: "#5c564a", margin: "0 0 12px" }}>
              Scegli cosa produci oggi: dirai quanto ingrediente principale usi
              e tutte le altre dosi si adeguano da sole.
            </p>
            <input value={cerca} onChange={e => setCerca(e.target.value)}
              placeholder="Cerca ricetta…"
              style={{ width: "100%", padding: "12px 14px", fontSize: 15, borderRadius: 12,
                border: "2px solid #e6e0d4", background: "#fffefb", boxSizing: "border-box", marginBottom: 12 }} />
            {caricando && <p style={{ textAlign: "center", color: "#7a7266" }}>Carico…</p>}
            {!caricando && filtrate.length === 0 && (
              <p style={{ textAlign: "center", color: "#7a7266" }}>Nessuna ricetta con le dosi.</p>
            )}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 12 }}>
              {filtrate.map(r => (
                <button key={r.id} onClick={() => scegli(r)}
                  style={{ minHeight: 88, padding: 12, borderRadius: 16, border: "1px solid #e6e0d4",
                    background: "#fffefb", boxShadow: "0 2px 10px rgba(63,90,78,.06)", cursor: "pointer",
                    textAlign: "left", fontFamily: "inherit" }}>
                  <div style={{ fontWeight: 800, fontSize: 14, color: "#2a3329", textTransform: "capitalize" }}>{r.nome}</div>
                  <div style={{ fontSize: 11, color: "#7a7266", marginTop: 4 }}>
                    {(r.ingredienti_dettaglio || []).length} ingredienti
                  </div>
                </button>
              ))}
            </div>
          </>
        )}

        {sel && (
          <>
            <div style={{ background: "#fffefb", border: "1px solid #e6e0d4", borderRadius: 16, padding: 14, marginBottom: 12 }}>
              <div style={{ fontSize: 12, fontWeight: 800, color: "#5c564a", marginBottom: 8 }}>
                {esito?.base
                  ? `${esito.base} — quanta ne usi oggi?`
                  : "Quanto ingrediente base usi oggi?"}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <button onClick={() => cambiaQta(qta - (qta > 1 ? 0.5 : 0.1))}
                  style={{ width: 48, height: 48, borderRadius: 12, border: "2px solid #e6e0d4",
                    background: "#faf7f0", fontSize: 22, fontWeight: 800, cursor: "pointer" }}>−</button>
                <input type="number" min="0.1" step="0.1" value={qta}
                  onChange={e => cambiaQta(e.target.value)}
                  style={{ flex: 1, minWidth: 0, padding: "10px 0", fontSize: 26, fontWeight: 800,
                    textAlign: "center", border: "2px solid #cfc6b4", borderRadius: 12, color: "#2a3329" }} />
                <select value={unita} onChange={e => { setUnita(e.target.value); calcola(sel, qta, e.target.value); }}
                  style={{ padding: "12px 8px", fontSize: 16, fontWeight: 700, borderRadius: 12,
                    border: "2px solid #e6e0d4", background: "#fffefb" }}>
                  <option value="kg">kg</option>
                  <option value="g">g</option>
                  <option value="l">l</option>
                </select>
                <button onClick={() => cambiaQta(qta + (qta >= 1 ? 0.5 : 0.1))}
                  style={{ width: 48, height: 48, borderRadius: 12, border: "2px solid #e6e0d4",
                    background: "#faf7f0", fontSize: 22, fontWeight: 800, cursor: "pointer" }}>+</button>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 5 }}>
                {PRESET_KG.map(v => (
                  <button key={v} onClick={() => { setUnita("kg"); setQta(v); calcola(sel, v, "kg"); }}
                    style={{ padding: "8px 2px", borderRadius: 8, fontSize: 12, fontWeight: 700, cursor: "pointer",
                      border: `2px solid ${qta === v && unita === "kg" ? "#5b7a6b" : "#e6e0d4"}`,
                      background: qta === v && unita === "kg" ? "#e8efe9" : "#faf7f0",
                      color: qta === v && unita === "kg" ? "#3f5a4e" : "#7a7266" }}>{v}kg</button>
                ))}
              </div>
            </div>

            {calcolando && <p style={{ textAlign: "center", color: "#7a7266" }}>Calcolo…</p>}

            {esito && !calcolando && (
              <div style={{ background: "#fffefb", border: "1px solid #e6e0d4", borderRadius: 16, padding: 14 }}>
                <div style={{ fontSize: 12, color: "#5c564a", marginBottom: 10 }}>
                  Riferimento: <b>{esito.base}</b> · dose ×{fmt(esito.fattore)} ·
                  circa <b>{esito.porzioni_stimate}</b> pezzi
                </div>
                {esito.ingredienti.map((i, k) => (
                  <div key={k} style={{ display: "flex", justifyContent: "space-between", gap: 10,
                    padding: "10px 0", borderBottom: k < esito.ingredienti.length - 1 ? "1px solid #f0ebe0" : "none" }}>
                    <span style={{ fontSize: 15, color: "#2a3329", textTransform: "capitalize" }}>{i.nome}</span>
                    <span style={{ fontSize: 16, fontWeight: 800, color: "#3f5a4e", whiteSpace: "nowrap" }}>
                      {fmt(i.quantita)} {i.unita || i.unita_misura || "g"}
                    </span>
                  </div>
                ))}
                <button onClick={stampaScheda}
                  style={{ width: "100%", marginTop: 14, padding: 14, borderRadius: 12, border: "none",
                    background: "linear-gradient(135deg,#5b7a6b,#3f5a4e)", color: "#fff",
                    fontWeight: 800, fontSize: 15, cursor: "pointer", fontFamily: "inherit" }}>
                  Stampa la dose di oggi
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
