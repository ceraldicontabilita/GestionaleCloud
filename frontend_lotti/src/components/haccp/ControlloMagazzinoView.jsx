import React, { useEffect, useState, useCallback, useRef } from "react";
import axios from "axios";
import { API } from "../../utils/constants";

// Colori sistema
const VIOLA = "#5b7a6b";
const VIOLA2 = "#5b7a6b";
const NAVY = "#2a3329";

const todayISO = () => new Date().toISOString().slice(0, 10);
const daysAgoISO = (n) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
};

function fmtData(s) {
  if (!s) return "";
  const d = new Date(s);
  if (isNaN(d)) return s;
  return d.toLocaleString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function MovRow({ m }) {
  const scarico = m.tipo === "scarico";
  const colore = scarico ? VIOLA2 : "#047857";
  const sfondo = scarico ? "#e8efe9" : "#ecfdf5";
  return (
    <div
      style={{
        background: "#fff",
        border: "1px solid #e5e7eb",
        borderRadius: 16,
        padding: 14,
        marginBottom: 10,
        boxShadow: "0 1px 6px rgba(20,30,40,.05)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 900, fontSize: 16, color: NAVY, lineHeight: 1.2 }}>
            {m.prodotto_nome || "Prodotto"}
          </div>
          <div style={{ marginTop: 4, fontWeight: 800, color: VIOLA, fontSize: 14 }}>
            {m.operatore_nome || "—"}
          </div>
        </div>
        <div style={{ textAlign: "right", whiteSpace: "nowrap" }}>
          <span
            style={{
              display: "inline-block",
              background: sfondo,
              color: colore,
              borderRadius: 999,
              padding: "4px 12px",
              fontWeight: 900,
              fontSize: 12,
              textTransform: "uppercase",
            }}
          >
            {scarico ? "Prelievo" : "Carico"}
          </span>
          <div style={{ marginTop: 6, fontWeight: 950, fontSize: 18, color: colore }}>
            {scarico ? "−" : "+"}
            {m.quantita} <span style={{ fontSize: 13, fontWeight: 800, color: "#6b7280" }}>{m.unita || "pz"}</span>
          </div>
        </div>
      </div>
      <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 8, fontSize: 12, color: "#6b7280", fontWeight: 700 }}>
        <span>{fmtData(m.data)}</span>
        <span style={{ color: "#9ca3af" }}>•</span>
        <span>{m.fonte === "fornitori" ? "Materie prime" : "Bar/Magazzino"}</span>
        {m.fornitore ? <><span style={{ color: "#9ca3af" }}>•</span><span>{m.fornitore}</span></> : null}
        {m.nota && m.nota !== "scarico tablet" ? <><span style={{ color: "#9ca3af" }}>•</span><span>{m.nota}</span></> : null}
      </div>
    </div>
  );
}

export default function ControlloMagazzinoView() {
  const [q, setQ] = useState("");
  const [operatore, setOperatore] = useState("");
  const [tipo, setTipo] = useState("tutti");
  const [dal, setDal] = useState(daysAgoISO(30));
  const [al, setAl] = useState(todayISO());
  const [movimenti, setMovimenti] = useState([]);
  const [operatori, setOperatori] = useState([]);
  const [tot, setTot] = useState({ totale: 0, n_scarico: 0, n_carico: 0 });
  const [loading, setLoading] = useState(true);
  const [errore, setErrore] = useState("");
  const debounce = useRef(null);

  const carica = useCallback(async () => {
    setLoading(true);
    setErrore("");
    try {
      const params = { dal, al, limit: 400 };
      if (q.trim()) params.q = q.trim();
      if (operatore) params.operatore = operatore;
      if (tipo !== "tutti") params.tipo = tipo;
      const r = await axios.get(`${API}/magazzino/movimenti`, { params });
      setMovimenti(r.data.movimenti || []);
      setTot({
        totale: r.data.totale || 0,
        n_scarico: r.data.n_scarico || 0,
        n_carico: r.data.n_carico || 0,
      });
      if ((r.data.operatori || []).length) setOperatori(r.data.operatori);
    } catch (e) {
      setErrore(
        e?.response?.status
          ? "Errore nel caricamento dei movimenti."
          : "Server in avvio, attendi qualche secondo e riprova."
      );
      setMovimenti([]);
    } finally {
      setLoading(false);
    }
  }, [q, operatore, tipo, dal, al]);

  // ricarica immediata sui filtri "secchi", con debounce sulla ricerca testo
  useEffect(() => {
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(carica, 350);
    return () => debounce.current && clearTimeout(debounce.current);
  }, [carica]);

  const chips = ["Aperol", "Caffè", "Tonno", "Farina", "Latte"];

  return (
    <div style={{ maxWidth: 820, margin: "0 auto", padding: "16px 14px 60px" }}>
      {/* Titolo nell'intestazione uniforme di pagina */}

      {/* Filtri */}
      <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 18, padding: 14, marginBottom: 14 }}>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Cerca prodotto (es. Aperol, caffè, tonno)…"
          style={{
            width: "100%",
            border: "2px solid #e5e7eb",
            borderRadius: 14,
            padding: "12px 14px",
            fontWeight: 700,
            fontSize: 16,
            outline: "none",
            boxSizing: "border-box",
          }}
        />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
          {chips.map((c) => (
            <button
              key={c}
              onClick={() => setQ(c)}
              style={{
                border: "2px solid #e8efe9",
                background: q === c ? VIOLA : "#f2f6f3",
                color: q === c ? "#fff" : VIOLA,
                borderRadius: 999,
                padding: "8px 14px",
                fontWeight: 900,
                fontSize: 13,
              }}
            >
              {c}
            </button>
          ))}
          {q ? (
            <button
              onClick={() => setQ("")}
              style={{ border: "none", background: "#f3f4f6", color: "#6b7280", borderRadius: 999, padding: "8px 14px", fontWeight: 900, fontSize: 13 }}
            >
              ✕ Pulisci
            </button>
          ) : null}
        </div>

        {/* minWidth:0 su colonne e campi: senza, i <select>/<input type=date>
            impongono la loro larghezza minima e la griglia sborda dalla card
            sugli smartphone da 360px (campi "Tipo" e "Al" tagliati) */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 8, marginTop: 12 }}>
          <div style={{ minWidth: 0 }}>
            <label style={{ fontSize: 11, fontWeight: 800, color: "#6b7280" }}>Operatore</label>
            <select
              value={operatore}
              onChange={(e) => setOperatore(e.target.value)}
              style={{ width: "100%", minWidth: 0, border: "2px solid #e5e7eb", borderRadius: 12, padding: "10px", fontWeight: 700, background: "#fff", marginTop: 4, boxSizing: "border-box" }}
            >
              <option value="">Tutti</option>
              {operatori.map((o) => (
                <option key={o} value={o}>{o}</option>
              ))}
            </select>
          </div>
          <div style={{ minWidth: 0 }}>
            <label style={{ fontSize: 11, fontWeight: 800, color: "#6b7280" }}>Tipo</label>
            <select
              value={tipo}
              onChange={(e) => setTipo(e.target.value)}
              style={{ width: "100%", minWidth: 0, border: "2px solid #e5e7eb", borderRadius: 12, padding: "10px", fontWeight: 700, background: "#fff", marginTop: 4, boxSizing: "border-box" }}
            >
              <option value="tutti">Tutti</option>
              <option value="scarico">Solo prelievi</option>
              <option value="carico">Solo carichi</option>
            </select>
          </div>
          <div style={{ minWidth: 0 }}>
            <label style={{ fontSize: 11, fontWeight: 800, color: "#6b7280" }}>Dal</label>
            <input type="date" value={dal} onChange={(e) => setDal(e.target.value)}
              style={{ width: "100%", minWidth: 0, border: "2px solid #e5e7eb", borderRadius: 12, padding: "10px 6px", fontWeight: 700, fontSize: 13, marginTop: 4, boxSizing: "border-box" }} />
          </div>
          <div style={{ minWidth: 0 }}>
            <label style={{ fontSize: 11, fontWeight: 800, color: "#6b7280" }}>Al</label>
            <input type="date" value={al} onChange={(e) => setAl(e.target.value)}
              style={{ width: "100%", minWidth: 0, border: "2px solid #e5e7eb", borderRadius: 12, padding: "10px 6px", fontWeight: 700, fontSize: 13, marginTop: 4, boxSizing: "border-box" }} />
          </div>
        </div>
      </div>

      {/* Riepilogo */}
      <div style={{ display: "flex", gap: 10, marginBottom: 14 }}>
        <div style={{ flex: 1, background: VIOLA, color: "#fff", borderRadius: 16, padding: "12px 14px" }}>
          <div style={{ fontSize: 26, fontWeight: 950 }}>{tot.n_scarico}</div>
          <div style={{ fontSize: 12, fontWeight: 800, opacity: 0.9 }}>Prelievi</div>
        </div>
        <div style={{ flex: 1, background: "#047857", color: "#fff", borderRadius: 16, padding: "12px 14px" }}>
          <div style={{ fontSize: 26, fontWeight: 950 }}>{tot.n_carico}</div>
          <div style={{ fontSize: 12, fontWeight: 800, opacity: 0.9 }}>Carichi</div>
        </div>
        <div style={{ flex: 1, background: "#3f5a4e", color: "#fff", borderRadius: 16, padding: "12px 14px" }}>
          <div style={{ fontSize: 26, fontWeight: 950 }}>{tot.totale}</div>
          <div style={{ fontSize: 12, fontWeight: 800, opacity: 0.9 }}>Totale</div>
        </div>
      </div>

      {/* Lista */}
      {loading ? (
        <div style={{ textAlign: "center", color: "#6b7280", padding: 40, fontWeight: 800 }}>Caricamento…</div>
      ) : errore ? (
        <div style={{ background: "#fff7ed", color: "#9a3412", border: "1px solid #fed7aa", borderRadius: 14, padding: 16, fontWeight: 800 }}>
          {errore}
        </div>
      ) : movimenti.length === 0 ? (
        <div style={{ textAlign: "center", color: "#6b7280", padding: 40, fontWeight: 800 }}>
          Nessun movimento trovato per i filtri scelti.
        </div>
      ) : (
        movimenti.map((m, i) => <MovRow key={m.id || i} m={m} />)
      )}
    </div>
  );
}
