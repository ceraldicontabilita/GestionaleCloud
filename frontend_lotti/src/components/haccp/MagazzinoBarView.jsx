import React, { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { apiError } from "../../utils/apiError";
import { norm } from "../../utils/textNormalize";
import PinKeypad from "./shared/PinKeypad";
import {
  actionAuthorizationStillValid,
  getTabletSession,
  markTabletActionAuthorized,
} from "../../utils/tabletSession";

const API = process.env.REACT_APP_LOTTI_BACKEND_URL + "/api";

function getOperatore() {
  return getTabletSession() || {};
}

function asList(data) {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.prodotti)) return data.prodotti;
  if (Array.isArray(data?.items)) return data.items;
  if (Array.isArray(data?.righe)) return data.righe;
  return [];
}

function MessageBox({ title, text, onRetry }) {
  return (
    <div style={{ textAlign: "center", color: "#94a3b8", padding: "48px 18px" }}>
      <div style={{ fontSize: 22, fontWeight: 900, color: "#e5e7eb", marginBottom: 10 }}>{title}</div>
      <div style={{ fontSize: 14, lineHeight: 1.45, marginBottom: 18 }}>{text}</div>
      {onRetry ? (
        <button onClick={onRetry} style={{ border: "1px solid #475569", background: "#1e293b", color: "#fff", borderRadius: 14, padding: "11px 18px", fontWeight: 900 }}>
          Riprova
        </button>
      ) : null}
    </div>
  );
}

// Tastierino numerico a schermo (richiesta Enzo 23/07/2026): sul tablet il
// campo quantità apre QUESTO popup coi tasti grandi, niente tastiera di sistema.
function KeypadPopup({ titolo, value, onChange, onClose }) {
  const premi = (t) => {
    if (t === "⌫") onChange(String(value).slice(0, -1));
    else if (t === ",") { if (!String(value).includes(",") && !String(value).includes(".")) onChange(String(value) + ","); }
    else onChange((String(value) === "0" ? "" : String(value)) + t);
  };
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 4000, background: "rgba(0,0,0,.6)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#1e293b", borderRadius: 22, padding: 18, width: "100%", maxWidth: 320, boxShadow: "0 20px 60px rgba(0,0,0,.5)" }}>
        <div style={{ color: "#94a3b8", fontSize: 13, fontWeight: 800, marginBottom: 6, textAlign: "center" }}>{titolo}</div>
        <div style={{ background: "#0f172a", color: "#fff", borderRadius: 14, padding: "14px", fontSize: 30, fontWeight: 900, textAlign: "center", marginBottom: 12, minHeight: 40 }}>
          {String(value) || "0"}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8 }}>
          {["1","2","3","4","5","6","7","8","9",",","0","⌫"].map(t => (
            <button key={t} onClick={() => premi(t)}
              style={{ border: "none", borderRadius: 14, padding: "16px 0", fontSize: 22, fontWeight: 900, background: "#334155", color: "#fff", cursor: "pointer" }}>
              {t}
            </button>
          ))}
        </div>
        <button onClick={onClose}
          style={{ width: "100%", marginTop: 12, border: "none", borderRadius: 14, padding: "14px 0", fontSize: 17, fontWeight: 900, background: "#5b7a6b", color: "#fff", cursor: "pointer" }}>
          ✓ OK
        </button>
      </div>
    </div>
  );
}

function ProductCard({ p, onReload, authorizeAction }) {
  const [qty, setQty] = useState("1");
  const [busy, setBusy] = useState(false);
  const [keypad, setKeypad] = useState(false);
  const nome = p.nome || p.name || "Prodotto";
  const stock = Number(p.stock ?? p.giacenza ?? p.quantita ?? 0);
  const unita = p.unita || p.um || "pz";
  const source = p.source || p.origine || "bar";

  const scarica = () => authorizeAction(async (operatoreNome) => {
    const q = Number(String(qty).replace(",", "."));
    if (!Number.isFinite(q) || q <= 0) { toast.error("Quantita non valida"); return; }
    setBusy(true);
    try {
      await axios.post(`${API}/magazzino/scarico`, {
        prodotto_id: p.id,
        source,
        quantita: q,
        operatore_nome: operatoreNome,
        nota: "scarico tablet"
      }, { timeout: 15000 });
      toast.success("Scarico registrato");
      onReload();
    } catch (e) {
      toast.error(apiError(e, "Errore scarico"));
    } finally {
      setBusy(false);
    }
  });

  return (
    <div style={{ background: "#fff", color: "#111827", borderRadius: 18, padding: 14, border: "1px solid #e5e7eb" }}>
      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 11, fontWeight: 900, color: source === "fornitori" ? "#8a6f47" : "#047857", marginBottom: 4 }}>{String(source).toUpperCase()}</div>
          <div style={{ fontSize: 15, fontWeight: 900, lineHeight: 1.25 }}>{nome}</div>
          <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>{p.categoria || p.fornitore || "Magazzino"}</div>
        </div>
        <div style={{ textAlign: "right", minWidth: 72 }}>
          <div style={{ fontSize: 23, fontWeight: 900, color: stock <= 0 ? "#dc2626" : "#047857" }}>{stock}</div>
          <div style={{ fontSize: 11, color: "#6b7280" }}>{unita}</div>
          {p.pezzi_per_collo > 1 && p.colli != null && (
            <div style={{ fontSize: 10, color: "#9ca3af", fontWeight: 700 }}>
              = {Math.round(p.colli * 100) / 100} cartoni da {p.pezzi_per_collo}
            </div>
          )}
        </div>
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        {/* Tocca la quantità → tastierino a schermo (niente tastiera di sistema) */}
        <button onClick={() => setKeypad(true)}
          style={{ width: 80, border: "1px solid #d1d5db", background: "#fff", borderRadius: 12, padding: "10px", fontWeight: 900, textAlign: "center", fontSize: 16, cursor: "pointer" }}>
          {qty || "0"}
        </button>
        <button onClick={scarica} disabled={busy || stock <= 0} style={{ flex: 1, border: "none", borderRadius: 12, padding: "10px", fontWeight: 900, color: "#fff", background: busy || stock <= 0 ? "#9ca3af" : "#5b7a6b" }}>
          {busy ? "Salvo..." : "Scarica"}
        </button>
      </div>
      {keypad && (
        <KeypadPopup titolo={`Quanti ${unita.toLowerCase()} prelevi di ${nome}?`}
          value={qty} onChange={setQty} onClose={() => setKeypad(false)} />
      )}
    </div>
  );
}

export default function MagazzinoBarView({ onBack, soloLavagna = false }) {
  const [op, setOp] = useState(() => getOperatore());
  const [showActionPin, setShowActionPin] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);
  const operatoreNome = op.nome || op.name || "Operatore";

  const authorizeAction = useCallback((azione) => {
    const session = getTabletSession();
    if (session && actionAuthorizationStillValid(session)) {
      azione(session.nome || "Operatore");
      return;
    }
    setPendingAction(() => azione);
    setShowActionPin(true);
  }, []);

  const actionPinOk = useCallback((operatore) => {
    const session = markTabletActionAuthorized(operatore, soloLavagna ? "lavagna" : "magazzino");
    setOp(session);
    setShowActionPin(false);
    const azione = pendingAction;
    setPendingAction(null);
    if (azione) azione(session.nome || "Operatore");
  }, [pendingAction, soloLavagna]);
  const [loading, setLoading] = useState(true);
  const [errore, setErrore] = useState("");
  const [prodotti, setProdotti] = useState([]);
  const [tab, setTab] = useState("rifornimenti");
  const [richieste, setRichieste] = useState([]);
  const [reqProd, setReqProd] = useState(null);
  const [reqQta, setReqQta] = useState(1);
  const [reqUnita, setReqUnita] = useState("collo");
  const [reqSearch, setReqSearch] = useState("");
  const [search, setSearch] = useState("");
  const [source, setSource] = useState("tutti");
  // Giacenze per anno di fatturazione (richiesta Enzo 23/07/2026)
  const [anno, setAnno] = useState("");
  const [anni, setAnni] = useState([]);
  useEffect(() => {
    axios.get(`${API}/fatture/anni`, { timeout: 30000 })
      .then(r => setAnni(Array.isArray(r.data) ? r.data : []))
      .catch(() => {});
  }, []);

  const carica = useCallback(async () => {
    setLoading(true);
    setErrore("");
    try {
      // timeout 45s: il primo colpo dopo lo spegnimento di Render può essere
      // lento (risveglio del server), 15s andava in "timeout exceeded"
      const r = await axios.get(`${API}/magazzino/prodotti-unificati`, {
        timeout: 45000, params: anno ? { anno } : {},
      });
      setProdotti(asList(r.data));
    } catch (e) {
      setErrore(apiError(e, "Errore caricamento magazzino"));
    } finally {
      setLoading(false);
    }
  }, [anno]);

  const caricaRichieste = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/magazzino-bar/richieste?stato=aperta`, { timeout: 15000 });
      setRichieste(r.data?.richieste || []);
    } catch { /* lavagna: niente popup, riprova al giro dopo */ }
  }, []);

  useEffect(() => { carica(); caricaRichieste(); }, [carica, caricaRichieste]);
  useEffect(() => {
    const t = setInterval(caricaRichieste, 12000); // la lavagna si aggiorna da sola
    return () => clearInterval(t);
  }, [caricaRichieste]);


  const inviaRichiesta = async () => {
    if (!reqProd) { toast.error("Scegli un prodotto"); return; }
    try {
      await axios.post(`${API}/magazzino-bar/richieste`, {
        prodotto_id: reqProd.id, quantita: Number(reqQta) || 1,
        unita_movimento: reqUnita, operatore_nome: operatoreNome,
      });
      toast.success(`Richiesta inviata: ${reqQta} ${reqUnita === "collo" ? "cartoni" : "pezzi"} di ${reqProd.nome}`);
      setReqProd(null); setReqQta(1); setReqSearch("");
      caricaRichieste();
    } catch (e) { toast.error(apiError(e, "Errore richiesta")); }
  };

  const okRichiesta = (r) => authorizeAction(async (nomeAutorizzato) => {
    try {
      const res = await axios.put(`${API}/magazzino-bar/richieste/${r.id}/ok?operatore_nome=${encodeURIComponent(nomeAutorizzato)}`);
      if (res.data?.avviso) toast.warning(res.data.avviso);
      else toast.success(`${r.prodotto_nome}: preso ✓ — stock aggiornato (${res.data?.stock_dopo ?? "?"})`);
      caricaRichieste(); carica();
    } catch (e) { toast.error(apiError(e, "Errore")); }
  });

  const annullaRichiesta = async (r) => {
    try { await axios.delete(`${API}/magazzino-bar/richieste/${r.id}`); caricaRichieste(); }
    catch (e) { toast.error(apiError(e, "Errore")); }
  };

  const barProds = prodotti.filter(p => p.id && (p.source || p.origine || "bar") === "bar");
  const reqMatches = reqSearch.trim().length >= 2
    ? barProds.filter(p => norm(p.nome).includes(norm(reqSearch))).slice(0, 6)
    : [];

  const filtrati = useMemo(() => {
    const q = norm(search);
    return prodotti.filter((p) => {
      const src = p.source || p.origine || "bar";
      if (source !== "tutti" && src !== source) return false;
      if (!q) return true;
      return norm(p.nome || p.name).includes(q)
        || norm(p.fornitore).includes(q)
        || norm(p.categoria).includes(q);
    });
  }, [prodotti, source, search]);

  const totBar = prodotti.filter((p) => (p.source || p.origine || "bar") === "bar").length;
  const totFornitori = prodotti.filter((p) => (p.source || p.origine) === "fornitori").length;

  return (
    <div style={{ minHeight: "100vh", background: "#0f172a", color: "#fff", fontFamily: "system-ui, sans-serif" }}>
      <div style={{ background: "linear-gradient(135deg,#3f5a4e,#5b7a6b)", padding: "18px 20px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div style={{ fontSize: 26, fontWeight: 900 }}>Magazzino</div>
          <div style={{ fontSize: 13, color: "#dcebe2" }}>{operatoreNome} - {totBar} bar - {totFornitori} fornitori</div>
        </div>
        <button onClick={onBack} style={{ border: "none", background: "rgba(255,255,255,.18)", color: "#fff", borderRadius: 18, padding: "12px 20px", fontWeight: 900 }}>← Reparti</button>
      </div>

      <div style={{ display: "flex", background: "#1e293b" }}>
        {(soloLavagna ? [["rifornimenti", `📺 Lavagna (${richieste.length})`]] : [["rifornimenti", `📺 Lavagna (${richieste.length})`], ["preleva", "🛒 Preleva"]]).map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)} style={{ flex: 1, padding: "14px 8px", border: "none", borderBottom: tab === id ? "4px solid #c59a5f" : "4px solid transparent", background: "transparent", color: tab === id ? "#c59a5f" : "#94a3b8", fontWeight: 900 }}>
            {label}
          </button>
        ))}
      </div>

      <div style={{ padding: 16 }}>
        {loading ? (
          <MessageBox title="Caricamento" text="Carico i dati del magazzino. Se il server non risponde, comparira un errore invece del blocco infinito." />
        ) : errore ? (
          <MessageBox title="Errore caricamento" text={errore} onRetry={carica} />
        ) : tab === "rifornimenti" ? (
          <>
            {/* Composer: il bar chiede */}
            <div style={{ background: "#1e293b", borderRadius: 18, padding: 14, marginBottom: 16 }}>
              <div style={{ fontWeight: 900, fontSize: 16, marginBottom: 10 }}>➕ Chiedi rifornimento (bar)</div>
              {reqProd ? (
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <div style={{ flex: 1, minWidth: 160, fontWeight: 900, fontSize: 16 }}>{reqProd.nome}</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <button onClick={() => setReqQta(q => Math.max(1, (Number(q) || 1) - 1))} style={{ width: 42, height: 42, borderRadius: 12, border: "none", background: "#334155", color: "#fff", fontSize: 22, fontWeight: 900 }}>−</button>
                    <div style={{ width: 36, textAlign: "center", fontSize: 20, fontWeight: 900 }}>{reqQta}</div>
                    <button onClick={() => setReqQta(q => (Number(q) || 1) + 1)} style={{ width: 42, height: 42, borderRadius: 12, border: "none", background: "#334155", color: "#fff", fontSize: 22, fontWeight: 900 }}>+</button>
                  </div>
                  <button onClick={() => setReqUnita(u => u === "collo" ? "pezzo" : "collo")} style={{ border: "1px solid #475569", background: "transparent", color: "#cbd5e1", borderRadius: 12, padding: "10px 12px", fontWeight: 900 }}>{reqUnita === "collo" ? "📦 Cartoni" : "🔢 Pezzi"}</button>
                  <button onClick={inviaRichiesta} style={{ border: "none", background: "#16a34a", color: "#fff", borderRadius: 12, padding: "12px 18px", fontWeight: 900, fontSize: 15 }}>📨 Invia</button>
                  <button onClick={() => { setReqProd(null); setReqSearch(""); }} style={{ border: "none", background: "transparent", color: "#94a3b8", fontWeight: 900 }}>✕</button>
                </div>
              ) : (
                <>
                  <input value={reqSearch} onChange={(e) => setReqSearch(e.target.value)} placeholder="Cerca il prodotto… (es. prosecco)" style={{ width: "100%", boxSizing: "border-box", padding: "13px 14px", borderRadius: 14, border: "1px solid #334155", background: "#0f172a", color: "#fff", fontSize: 16 }} />
                  {reqMatches.map(p => (
                    <button key={p.id} onClick={() => setReqProd(p)} style={{ display: "block", width: "100%", textAlign: "left", marginTop: 8, padding: "12px 14px", borderRadius: 12, border: "1px solid #334155", background: "#0b1220", color: "#fff", fontWeight: 800, fontSize: 15 }}>
                      {p.nome} <span style={{ color: "#64748b", fontWeight: 700 }}>· stock {p.stock ?? 0}</span>
                    </button>
                  ))}
                </>
              )}
            </div>

            {/* Lavagna: il magazzino vede ed evade */}
            <div style={{ fontWeight: 900, fontSize: 16, marginBottom: 10 }}>📺 Da prelevare ({richieste.length}) <span style={{ color: "#64748b", fontSize: 12, fontWeight: 800 }}>si aggiorna da sola</span></div>
            {richieste.length === 0 ? (
              <MessageBox title="Nessuna richiesta" text="Quando il bar chiede un rifornimento, compare qui in automatico." />
            ) : richieste.map(r => (
              <div key={r.id} style={{ background: "#1e293b", borderRadius: 18, padding: 14, marginBottom: 10, display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 900, fontSize: 17 }}>{r.quantita} {r.unita_movimento === "collo" ? (r.quantita > 1 ? "cartoni" : "cartone") : "pz"} · {r.prodotto_nome}</div>
                  <div style={{ color: "#94a3b8", fontSize: 12, fontWeight: 800, marginTop: 2 }}>chiesto da {r.richiesto_da || "bar"} · {String(r.created_at || "").slice(11, 16)}</div>
                </div>
                <button onClick={() => annullaRichiesta(r)} style={{ border: "none", background: "transparent", color: "#64748b", fontWeight: 900, fontSize: 18 }}>✕</button>
                <button onClick={() => okRichiesta(r)} style={{ border: "none", background: "#16a34a", color: "#fff", borderRadius: 14, padding: "14px 18px", fontWeight: 900, fontSize: 16, whiteSpace: "nowrap" }}>✓ OK preso</button>
              </div>
            ))}
          </>
        ) : tab === "preleva" ? (
          <>
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cerca prodotto o fornitore" style={{ width: "100%", boxSizing: "border-box", padding: "13px 14px", borderRadius: 16, border: "1px solid #334155", background: "#1e293b", color: "#fff", marginBottom: 12, fontSize: 16 }} />
            <div style={{ display: "flex", gap: 8, marginBottom: 14, overflowX: "auto", alignItems: "center" }}>
              {[["tutti", "Tutti"], ["bar", "Bar"], ["fornitori", "Fatture"]].map(([id, label]) => (
                <button key={id} onClick={() => setSource(id)} style={{ padding: "8px 16px", borderRadius: 999, border: "1px solid #334155", background: source === id ? "#c59a5f" : "#1e293b", color: source === id ? "#fff" : "#94a3b8", fontWeight: 900 }}>{label}</button>
              ))}
              {/* Giacenze per anno di fatturazione (solo lotti da fattura) */}
              <select value={anno} onChange={(e) => setAnno(e.target.value)}
                style={{ marginLeft: "auto", padding: "8px 12px", borderRadius: 999, border: "1px solid #334155", background: anno ? "#c59a5f" : "#1e293b", color: anno ? "#fff" : "#94a3b8", fontWeight: 900, flexShrink: 0 }}>
                <option value="">Tutti gli anni</option>
                {anni.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </div>
            {filtrati.length === 0 ? <MessageBox title="Nessun prodotto" text="Non ci sono prodotti da mostrare con questi filtri." /> : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10, paddingBottom: 70 }}>
                {filtrati.map((p, i) => <ProductCard key={`${p.source || p.origine || "bar"}-${p.id || i}`} p={p} onReload={carica} authorizeAction={authorizeAction} />)}
              </div>
            )}
          </>
        ) : null}
      </div>
      {showActionPin && (
        <PinKeypad
          titolo="Chi sta effettuando il prelievo?"
          sottotitolo="Conferma il tuo PIN. Le azioni successive restano autorizzate per 10 minuti."
          colore="#5b7a6b"
          maxLen={6}
          onSuccess={actionPinOk}
          onCancel={() => { setShowActionPin(false); setPendingAction(null); }}
        />
      )}
    </div>
  );
}
