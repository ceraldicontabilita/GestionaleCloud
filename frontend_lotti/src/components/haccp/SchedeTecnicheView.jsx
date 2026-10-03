import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { apiError } from "../../utils/apiError";
import axios from "axios";
import { toast } from "sonner";
import {
  FileText, Search, ExternalLink, Check, Trash2, Plus, X, AlertCircle, Bell, Upload,
} from "lucide-react";
import { API } from "../../utils/constants";
import { apriDocumentoAutenticato } from "../../auth";

const SALVIA = "#3f5a4e";
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
          <span style={{ fontWeight: 600, fontSize: 16, flex: 1, color: SALVIA, fontFamily: "\'Plus Jakarta Sans\', -apple-system, BlinkMacSystemFont, \'Segoe UI\', system-ui, sans-serif" }}>Scheda tecnica</span>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "#9aa593" }}><X size={22} /></button>
        </div>
        <div style={{ padding: 20, overflowY: "auto" }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: SALVIA, marginBottom: 4 }}>{prodotto.nome}</div>
          {prodotto.fornitore && <div style={{ fontSize: 12, color: "#9aa593", marginBottom: 16 }}>{prodotto.fornitore}</div>}

          <div style={{ background: "#e8efe9", borderRadius: 10, padding: 14, marginBottom: 16 }}>
            <div style={{ fontSize: 12, color: SALVIA, marginBottom: 8, fontWeight: 600 }}>
              1. Cerca la scheda sul web
            </div>
            <a href={googleUrl} target="_blank" rel="noreferrer" style={{ ...btn(SAGE, "#fff", { textDecoration: "none", width: "100%" }) }}>
              <Search size={15} /> Cerca su Google
            </a>
            <div style={{ fontSize: 11, color: "#6b7669", marginTop: 8, lineHeight: 1.4 }}>
              Si apre Google con la ricerca pronta. Trova il PDF ufficiale (preferibilmente del produttore), copia il link e incollalo qui sotto.
            </div>
          </div>

          <div style={{ fontSize: 12, color: SALVIA, marginBottom: 8, fontWeight: 600 }}>2. Incolla il link e salva</div>
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

const ETICHETTE_NUTRIZIONE = [
  ["energia_kcal", "Energia", "kcal"], ["grassi_g", "Grassi", "g"], ["grassi_saturi_g", "di cui saturi", "g"],
  ["carboidrati_g", "Carboidrati", "g"], ["zuccheri_g", "di cui zuccheri", "g"], ["fibre_g", "Fibre", "g"],
  ["proteine_g", "Proteine", "g"], ["sale_g", "Sale", "g"],
];

const NOMI_ALLERGENI = {
  glutine: "glutine", crostacei: "crostacei", uova: "uova", pesce: "pesce", arachidi: "arachidi",
  soia: "soia", latte: "latte", frutta_guscio: "frutta a guscio", sedano: "sedano", senape: "senape",
  sesamo: "sesamo", solfiti: "solfiti", lupini: "lupini", molluschi: "molluschi",
};
const nomiAllergeni = (ids) => ids.map((a) => NOMI_ALLERGENI[a] || a).join(", ");

// Allergeni e valori letti dal PDF del fornitore: solo quelli scritti, mai dedotti.
export function DatiScheda({ s }) {
  const nutrizione = s.valori_nutrizionali_100g || {};
  const valori = ETICHETTE_NUTRIZIONE.filter(([k]) => nutrizione[k]);
  return (
    <div style={{ marginTop: 8, fontSize: 12, color: "#2a3329", background: "#faf7f0", border: "1px solid #e6e0d4", borderRadius: 8, padding: "6px 10px" }}>
      <div>
        <strong>Allergeni: </strong>
        {s.allergeni_stato === "da_verificare"
          ? <span style={{ color: "#c4894a", fontWeight: 700 }}>da verificare sul PDF</span>
          : (s.allergeni || []).length ? nomiAllergeni(s.allergeni) : "nessuno dichiarato"}
        {(s.allergeni_tracce || []).length > 0 && <span> · può contenere tracce di {nomiAllergeni(s.allergeni_tracce)}</span>}
      </div>
      {valori.length > 0 ? (
        <div style={{ marginTop: 2 }}>
          <strong>Per 100 g: </strong>
          {valori.map(([k, lab, um]) => `${lab} ${nutrizione[k]} ${um}`).join(" · ")}
        </div>
      ) : (
        <div style={{ marginTop: 2, color: "#c4894a" }}>Valori nutrizionali da verificare sul PDF</div>
      )}
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
  const [filesImport, setFilesImport] = useState([]);
  const [previewImport, setPreviewImport] = useState(null);
  const [importando, setImportando] = useState(false);
  const importLock = useRef(false);

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

  const preparaImport = async (scelti) => {
    const files = Array.from(scelti || []);
    if (!files.length || importLock.current) return;
    importLock.current = true;
    setImportando(true);
    setFilesImport(files);
    setPreviewImport(null);
    try {
      const form = new FormData();
      files.forEach((file) => form.append("files", file));
      const risposta = await axios.post(`${API}/schede-tecniche/importa/anteprima`, form);
      setPreviewImport({
        ...risposta.data,
        schede: (risposta.data?.schede || []).map((scheda) => ({
          ...scheda,
          associazione_confermata: scheda.associazione?.stato === "proposta_certa" ? scheda.associazione.nome : "",
        })),
      });
    } catch (e) {
      setFilesImport([]);
      toast.error("Anteprima non riuscita: " + apiError(e));
    } finally {
      importLock.current = false;
      setImportando(false);
    }
  };

  const confermaImport = async () => {
    if (!previewImport || filesImport.length !== previewImport.schede?.length || importLock.current) return;
    importLock.current = true;
    setImportando(true);
    try {
      const form = new FormData();
      filesImport.forEach((file) => form.append("files", file));
      previewImport.schede.forEach((scheda) => form.append("preview_tokens", scheda.preview_token));
      previewImport.schede.forEach((scheda) => form.append("associazioni_confermate", scheda.associazione_confermata || ""));
      const risposta = await axios.post(`${API}/schede-tecniche/importa/conferma`, form);
      toast.success(`${risposta.data?.nuovi_originali || 0} nuovi originali archiviati`);
      setFilesImport([]);
      setPreviewImport(null);
      await carica();
    } catch (e) {
      toast.error("Import non riuscito: " + apiError(e));
    } finally {
      importLock.current = false;
      setImportando(false);
    }
  };

  const aggiornaAssociazioneImport = (indice, nome) => {
    setPreviewImport((corrente) => ({
      ...corrente,
      schede: corrente.schede.map((scheda, i) => (
        i === indice ? { ...scheda, associazione_confermata: nome } : scheda
      )),
    }));
  };

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
    <div style={{ fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif", color: SALVIA, maxWidth: 700, margin: "0 auto" }}>
      {/* Titolo nell'intestazione uniforme di pagina */}

      <div style={{ background: CARD, border: `1px solid ${LINE}`, borderRadius: 12, padding: 14, marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <Upload size={17} color={SAGE} />
          <strong style={{ fontSize: 14 }}>Carica schede PDF</strong>
        </div>
        <div style={{ fontSize: 12, color: "#6b7669", lineHeight: 1.45, marginBottom: 10 }}>
          Seleziona più file. Prima vedrai SHA-256, dati letti, duplicati e associazioni; nessun originale viene archiviato senza conferma.
        </div>
        <input
          type="file" accept="application/pdf,.pdf" multiple disabled={importando}
          onChange={(e) => preparaImport(e.target.files)}
          style={{ ...INPUT, padding: 8 }}
        />
        <datalist id="prodotti-schede-tecniche">
          {prodotti.map((p) => <option key={p.prodotto_key} value={p.nome} />)}
        </datalist>
        {importando && <div style={{ fontSize: 12, color: "#6b7669", marginTop: 8 }}>Lettura in corso…</div>}
        {previewImport && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>
              {previewImport.files_ricevuti} file · {previewImport.originali_unici} originali unici
            </div>
            <div style={{ display: "grid", gap: 7, maxHeight: 360, overflowY: "auto" }}>
              {previewImport.schede.map((s, i) => (
                <div key={`${s.sha256}-${i}`} style={{ border: `1px solid ${LINE}`, borderRadius: 9, padding: 9, fontSize: 11, color: "#2a3329" }}>
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <strong style={{ flex: 1, overflowWrap: "anywhere" }}>{s.filename}</strong>
                    {s.duplicato_nel_lotto && <span style={{ color: "#9c6a32", fontWeight: 700 }}>copia identica</span>}
                  </div>
                  <div style={{ fontFamily: "monospace", overflowWrap: "anywhere", color: "#6b7669", marginTop: 3 }}>SHA-256 {s.sha256}</div>
                  <div style={{ marginTop: 4 }}>
                    Codice: {s.codice_fornitore || "non disponibile"} · Prodotto nel PDF: {s.nome_dichiarato || "da verificare"}
                  </div>
                  {s.metadati_tecnici?.produttore_dichiarato && <div>Produttore: {s.metadati_tecnici.produttore_dichiarato}</div>}
                  {(s.metadati_tecnici?.revisione_dichiarata || s.metadati_tecnici?.data_documento_dichiarata) && (
                    <div>
                      Documento: {s.metadati_tecnici.revisione_dichiarata || "revisione non dichiarata"}
                      {s.metadati_tecnici.data_documento_dichiarata ? ` · data ${s.metadati_tecnici.data_documento_dichiarata}` : ""}
                    </div>
                  )}
                  <div>
                    Allergeni: {(s.allergeni || []).length ? nomiAllergeni(s.allergeni) : "nessuno letto"}
                    {(s.allergeni_tracce || []).length ? ` · tracce: ${nomiAllergeni(s.allergeni_tracce)}` : ""}
                    {s.allergeni_stato === "da_verificare" ? " · DA VERIFICARE" : ""}
                  </div>
                  <div style={{ color: s.associazione?.stato === "proposta_certa" ? "#3d8168" : "#c4894a", fontWeight: 700 }}>
                    {s.associazione?.stato === "proposta_certa"
                      ? `Associazione esatta: ${s.associazione.nome}`
                      : `Associazione DA VERIFICARE: ${s.associazione?.motivo || "nessuna prova"}`}
                  </div>
                  <label style={{ display: "block", marginTop: 6, fontWeight: 700 }}>
                    Associazione confermata (nome esatto già presente)
                    <input
                      list="prodotti-schede-tecniche"
                      value={s.associazione_confermata || ""}
                      onChange={(e) => aggiornaAssociazioneImport(i, e.target.value)}
                      placeholder="Lascia vuoto per conservare DA VERIFICARE"
                      style={{ ...INPUT, padding: "6px 8px", fontSize: 11, marginTop: 3 }}
                    />
                  </label>
                </div>
              ))}
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
              <button onClick={() => { setPreviewImport(null); setFilesImport([]); }} disabled={importando} style={btn(CREAM, "#6b7669", { flex: 1, border: `1px solid ${LINE}` })}>Annulla</button>
              <button onClick={confermaImport} disabled={importando} style={btn(SAGE, "#fff", { flex: 1 })}>
                <Check size={14} /> Conferma originali
              </button>
            </div>
          </div>
        )}
      </div>

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
                <div style={{ fontSize: 14, fontWeight: 600, color: SALVIA }}>{p.nome}</div>
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
                    <a href={s.url} target="_blank" rel="noreferrer" onClick={s.url?.startsWith("/lotti/api/") ? (e) => { e.preventDefault(); apriDocumentoAutenticato(s.url); } : undefined} style={{ fontSize: 12, color: SAGE, fontWeight: 600, textDecoration: "none", display: "flex", alignItems: "center", gap: 4 }}>
                      <ExternalLink size={12} /> {s.fonte === "email_fornitore" ? "PDF del fornitore" : s.tipo === "sicurezza" ? "Sicurezza" : "Tecnica"}
                    </a>
                    {/* l'originale arrivato dal fornitore è la prova per l'ASL: non si toglie da qui */}
                    {s.fonte !== "email_fornitore" && (
                      <button onClick={() => elimina(p.prodotto_key, s.tipo)} aria-label="Elimina scheda" style={{ background: "none", border: "none", cursor: "pointer", color: "#c7cfc2", padding: 0, display: "flex" }}>
                        <Trash2 size={12} />
                      </button>
                    )}
                  </div>
                ))}
                <button onClick={() => setModalProd(p)} style={btn(CREAM, SAGE, { fontSize: 11, padding: "4px 8px", border: `1px solid ${LINE}` })}>
                  <Plus size={11} /> Altra
                </button>
              </div>
            )}
            {p.schede.filter((s) => s.allergeni_stato).map((s, i) => (
              <DatiScheda key={`dati-${i}`} s={s} />
            ))}
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
