import { useState, useEffect, useCallback, useMemo } from "react";
import { apiError } from "../../utils/apiError";
import axios from "axios";
import { toast } from "sonner";
import {
  FileText, Search, ExternalLink, Check, Trash2, Plus, X, AlertCircle, Bell,
} from "lucide-react";
import { API } from "../../utils/constants";

const NAVY = "#3f5a4e";
const SAGE = "#5b7a6b";
const CREAM = "#faf7f0";
const CARD = "#fffefb";
const LINE = "#e6e0d4";

const INPUT = {
  width: "100%", padding: "10px 12px", border: `1px solid ${LINE}`,
  borderRadius: 9, fontSize: 14, fontFamily: "inherit", outline: "none", boxSizing: "border-box",
  background: CARD,
};
const btn = (bg, color, extra = {}) => ({
  padding: "9px 15px", background: bg, color, border: "none", borderRadius: 9,
  fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "inherit",
  display: "flex", alignItems: "center", gap: 6, justifyContent: "center", ...extra,
});

function ModalScheda({ prodotto, onClose, onSaved }) {
  const [url, setUrl] = useState("");
  const [tipo, setTipo] = useState("tecnica");
  const [googleUrl, setGoogleUrl] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    axios.get(`${API}/schede-tecniche/query-ricerca?nome=${encodeURIComponent(prodotto.nome)}`)
      .then((r) => setGoogleUrl(r.data?.google_url || ""))
      .catch(() => {});
  }, [prodotto.nome]);

  const salva = async () => {
    if (!url.trim()) { toast.error("Incolla il link della scheda"); return; }
    setSaving(true);
    try {
      await axios.post(`${API}/schede-tecniche/salva`, {
        prodotto_key: prodotto.prodotto_key,
        nome_prodotto: prodotto.nome,
        url: url.trim(),
        tipo,
        verificato: true,
      });
      toast.success("Scheda salvata");
      onSaved();
      onClose();
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(42,51,41,0.5)", backdropFilter: "blur(3px)", zIndex: 320, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }} onClick={onClose}>
      <div style={{ background: CARD, borderRadius: 16, width: "100%", maxWidth: 480, maxHeight: "92vh", display: "flex", flexDirection: "column", overflow: "hidden" }} onClick={(e) => e.stopPropagation()}>
        <div style={{ padding: "16px 20px", borderBottom: `1px solid ${LINE}`, display: "flex", alignItems: "center", gap: 10 }}>
          <FileText size={18} color={SAGE} />
          <span style={{ fontWeight: 600, fontSize: 16, flex: 1, color: NAVY, fontFamily: "'Fraunces', Georgia, serif" }}>Scheda tecnica</span>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "#9aa593" }}><X size={22} /></button>
        </div>
        <div style={{ padding: 20, overflowY: "auto" }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: NAVY, marginBottom: 4 }}>{prodotto.nome}</div>
          {prodotto.fornitore && <div style={{ fontSize: 12, color: "#9aa593", marginBottom: 16 }}>{prodotto.fornitore}</div>}

          <div style={{ background: "#e8efe9", borderRadius: 10, padding: 14, marginBottom: 16 }}>
            <div style={{ fontSize: 12, color: NAVY, marginBottom: 8, fontWeight: 600 }}>
              1. Cerca la scheda sul web
            </div>
            <a href={googleUrl} target="_blank" rel="noreferrer" style={{ ...btn(SAGE, "#fff", { textDecoration: "none", width: "100%" }) }}>
              <Search size={15} /> Cerca su Google
            </a>
            <div style={{ fontSize: 11, color: "#6b7669", marginTop: 8, lineHeight: 1.4 }}>
              Si apre Google con la ricerca pronta. Trova il PDF ufficiale (preferibilmente del produttore), copia il link e incollalo qui sotto.
            </div>
          </div>

          <div style={{ fontSize: 12, color: NAVY, marginBottom: 8, fontWeight: 600 }}>2. Incolla il link e salva</div>
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://...scheda.pdf" style={{ ...INPUT, marginBottom: 10 }} autoFocus />
          <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            <button onClick={() => setTipo("tecnica")} style={btn(tipo === "tecnica" ? SAGE : CREAM, tipo === "tecnica" ? "#fff" : "#6b7669", { flex: 1, border: `1px solid ${LINE}` })}>Tecnica</button>
            <button onClick={() => setTipo("sicurezza")} style={btn(tipo === "sicurezza" ? SAGE : CREAM, tipo === "sicurezza" ? "#fff" : "#6b7669", { flex: 1, border: `1px solid ${LINE}` })}>Sicurezza</button>
          </div>

          <button onClick={salva} disabled={saving} style={btn(SAGE, "#fff", { width: "100%", opacity: saving ? 0.6 : 1 })}>
            <Check size={15} /> {saving ? "Salvataggio..." : "Salva scheda"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function SchedeTecnicheView() {
  const [prodotti, setProdotti] = useState([]);
  const [proposte, setProposte] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filtro, setFiltro] = useState("tutti");
  const [modalProd, setModalProd] = useState(null);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const [prod, prop] = await Promise.all([
        axios.get(`${API}/schede-tecniche/prodotti?limit=2000`),
        axios.get(`${API}/schede-tecniche/da-proporre?giorni=30`),
      ]);
      setProdotti(prod.data?.prodotti || []);
      setProposte(prop.data?.proposte || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const elimina = async (key, tipo) => {
    try {
      await axios.delete(`${API}/schede-tecniche/elimina?prodotto_key=${encodeURIComponent(key)}&tipo=${tipo}`);
      toast.success("Scheda rimossa");
      carica();
    } catch {
      toast.error("Errore rimozione");
    }
  };

  const filtrati = useMemo(() => {
    let l = prodotti;
    if (filtro === "con") l = l.filter((p) => p.ha_scheda);
    if (filtro === "senza") l = l.filter((p) => !p.ha_scheda);
    if (search) l = l.filter((p) => p.nome.toLowerCase().includes(search.toLowerCase()));
    return l;
  }, [prodotti, filtro, search]);

  const stats = useMemo(() => ({
    tot: prodotti.length,
    con: prodotti.filter((p) => p.ha_scheda).length,
  }), [prodotti]);

  return (
    <div style={{ fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif", color: NAVY, maxWidth: 700, margin: "0 auto" }}>
      {/* Titolo nell'intestazione uniforme di pagina */}

      {/* Proposte nuovi prodotti */}
      {proposte.length > 0 && (
        <div style={{ background: "#f7ecdc", border: "1px solid #ecd6b8", borderRadius: 12, padding: 14, marginBottom: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <Bell size={16} color="#9c6a32" />
            <span style={{ fontSize: 13, fontWeight: 700, color: "#7d5526" }}>
              {proposte.length} nuovo/i prodotto/i senza scheda
            </span>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {proposte.slice(0, 8).map((p, i) => (
              <button key={i} onClick={() => setModalProd(p)} style={btn("#fff", "#7d5526", { fontSize: 12, padding: "6px 10px", border: "1px solid #ecd6b8" })}>
                <Plus size={13} /> {p.nome.length > 30 ? p.nome.slice(0, 30) + "…" : p.nome}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Stats + filtri */}
      <div style={{ display: "flex", gap: 10, marginBottom: 12, flexWrap: "wrap", alignItems: "center" }}>
        <div style={{ background: CARD, border: `1px solid ${LINE}`, borderRadius: 10, padding: "8px 14px" }}>
          <span style={{ fontWeight: 800, fontSize: 18, color: SAGE }}>{stats.con}</span>
          <span style={{ fontSize: 12, color: "#6b7669" }}> / {stats.tot} con scheda</span>
        </div>
        <div style={{ display: "flex", gap: 5 }}>
          {[{ id: "tutti", l: "Tutti" }, { id: "con", l: "Con scheda" }, { id: "senza", l: "Senza" }].map((f) => (
            <button key={f.id} onClick={() => setFiltro(f.id)} style={{ padding: "6px 12px", fontSize: 12, fontWeight: 600, background: filtro === f.id ? SAGE : CREAM, color: filtro === f.id ? "#fff" : "#6b7669", border: `1px solid ${LINE}`, borderRadius: 20, cursor: "pointer", fontFamily: "inherit" }}>{f.l}</button>
          ))}
        </div>
      </div>

      <div style={{ position: "relative", marginBottom: 14 }}>
        <Search size={15} style={{ position: "absolute", left: 11, top: "50%", transform: "translateY(-50%)", color: "#9aa593" }} />
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cerca prodotto..." style={{ ...INPUT, paddingLeft: 34 }} />
      </div>

      {loading && <div style={{ textAlign: "center", color: "#9aa593", padding: 40 }}>Caricamento prodotti...</div>}

      <div style={{ display: "grid", gap: 8 }}>
        {!loading && filtrati.map((p) => (
          <div key={p.prodotto_key} style={{ background: CARD, border: `1px solid ${LINE}`, borderRadius: 12, padding: "12px 14px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: NAVY }}>{p.nome}</div>
                {p.fornitore && <div style={{ fontSize: 11, color: "#9aa593" }}>{p.fornitore}</div>}
              </div>
              {p.ha_scheda ? (
                <span style={{ fontSize: 11, fontWeight: 700, color: "#3d8168", background: "#e2efe8", padding: "3px 10px", borderRadius: 20, display: "flex", alignItems: "center", gap: 4 }}>
                  <Check size={12} /> {p.schede.length} scheda{p.schede.length > 1 ? "e" : ""}
                </span>
              ) : (
                <button onClick={() => setModalProd(p)} style={btn(SAGE, "#fff", { fontSize: 12, padding: "7px 12px" })}>
                  <Plus size={13} /> Aggiungi
                </button>
              )}
            </div>
            {p.ha_scheda && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                {p.schede.map((s, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 4, background: CREAM, border: `1px solid ${LINE}`, borderRadius: 8, padding: "4px 8px" }}>
                    <a href={s.url} target="_blank" rel="noreferrer" style={{ fontSize: 12, color: SAGE, fontWeight: 600, textDecoration: "none", display: "flex", alignItems: "center", gap: 4 }}>
                      <ExternalLink size={12} /> {s.tipo === "sicurezza" ? "Sicurezza" : "Tecnica"}
                    </a>
                    <button onClick={() => elimina(p.prodotto_key, s.tipo)} style={{ background: "none", border: "none", cursor: "pointer", color: "#c7cfc2", padding: 0, display: "flex" }}>
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
                <button onClick={() => setModalProd(p)} style={btn(CREAM, SAGE, { fontSize: 11, padding: "4px 8px", border: `1px solid ${LINE}` })}>
                  <Plus size={11} /> Altra
                </button>
              </div>
            )}
          </div>
        ))}
        {!loading && filtrati.length === 0 && (
          <div style={{ textAlign: "center", color: "#9aa593", padding: 30 }}>
            <AlertCircle size={32} style={{ opacity: 0.3, marginBottom: 8 }} />
            <p style={{ fontSize: 14 }}>Nessun prodotto</p>
          </div>
        )}
      </div>

      {modalProd && (
        <ModalScheda prodotto={modalProd} onClose={() => setModalProd(null)} onSaved={carica} />
      )}
    </div>
  );
}
