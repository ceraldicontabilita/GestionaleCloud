// Scelta della categoria Menu di una ricetta (19/09/2026).
//
// Il titolare: «la categoria dove inserirla, che recuperi da Menu o si creano
// in Lotti». Le categorie arrivano da `GET /api/menu-categorie`: si vedono
// tutte, ma si possono scegliere solo quelle di Lotti — quelle di Qromo
// restano disabilitate con il loro motivo, perché la sincronizzazione Qromo le
// cancella e le ricrea a ogni giro.
//
// Mani sporche: qui si sceglie da due tendine. La tastiera serve solo quando
// una categoria proprio non esiste e va creata (e in quel caso il campo si apre
// su richiesta, non sta sempre lì aperto).
import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { FolderPlus, Loader2, RefreshCw, Tags } from "lucide-react";
import { indicizzaCategorie, nomeCategoria } from "../../../utils/menuVetrina";

const API = process.env.REACT_APP_LOTTI_BACKEND_URL + "/api";

const messaggioErrore = (e, fallback) => {
  const d = e?.response?.data?.detail;
  if (typeof d === "string" && d) return d;
  if (e?.response?.status === 503) return "Menu digitale non configurato su questo ambiente";
  return fallback;
};

/** Carica le categorie del Menu una sola volta e le tiene pronte. */
export function useCategorieMenu() {
  const [dati, setDati] = useState(null);
  const [caricando, setCaricando] = useState(true);
  const [errore, setErrore] = useState("");

  const carica = useCallback(async () => {
    setCaricando(true);
    try {
      const r = await axios.get(`${API}/menu-categorie`);
      setDati(r.data || { categorie: [] });
      setErrore("");
    } catch (e) {
      setDati({ categorie: [] });
      setErrore(messaggioErrore(e, "Categorie del Menu non raggiungibili"));
    } finally {
      setCaricando(false);
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  // L'indice è una coppia di Map: ricrearlo a ogni render farebbe ricalcolare
  // tutta la vetrina a vuoto (è nelle dipendenze dei useMemo di chi lo usa).
  const indice = useMemo(() => indicizzaCategorie(dati), [dati]);

  return { dati, indice, caricando, errore, ricarica: carica };
}

const lbl = {
  fontSize: 12, fontWeight: 800, color: "var(--text-2)", textTransform: "uppercase",
  letterSpacing: ".05em", display: "block", marginBottom: 6,
};
const campo = {
  width: "100%", minHeight: 44, padding: "11px 12px", border: "1.5px solid var(--border)",
  borderRadius: 10, fontSize: 15, fontFamily: "var(--font)", boxSizing: "border-box",
  background: "var(--card)", color: "var(--text)",
};
const bottoneTenue = {
  display: "inline-flex", alignItems: "center", gap: 6, minHeight: 44,
  padding: "10px 14px", borderRadius: 10, border: "1.5px solid var(--border)",
  background: "var(--card)", color: "var(--text-2)", fontFamily: "var(--font)",
  fontSize: 13, fontWeight: 800, cursor: "pointer",
};

/**
 * @param {number|null} categoriaId       menu_category_id salvato sulla ricetta
 * @param {number|null} sottocategoriaId  menu_subcategory_id salvato sulla ricetta
 * @param {(cat:number|null, sub:number|null) => void} onChange
 * @param {boolean} adminAbilitato        chi non è amministratore non crea categorie
 */
export default function SceltaCategoriaMenu({
  categoriaId, sottocategoriaId, onChange, avviso, adminAbilitato = true,
}) {
  const { dati, indice, caricando, errore, ricarica } = useCategorieMenu();
  const [nuovaCat, setNuovaCat] = useState(null);      // null = campo chiuso
  const [nuovaSub, setNuovaSub] = useState(null);
  const [creando, setCreando] = useState("");
  const [esito, setEsito] = useState("");

  const categorie = dati?.categorie || [];
  const scelta = categoriaId == null ? null : indice.perId.get(Number(categoriaId));
  const sceltaValida = !!scelta && scelta.selezionabile === true;
  const sottocategorie = sceltaValida
    ? (scelta.sottocategorie || []).filter((s) => s.selezionabile !== false)
    : [];

  const cambiaCategoria = (valore) => {
    setEsito("");
    onChange(valore === "" ? null : Number(valore), null);
  };

  const creaCategoria = async () => {
    const nome = (nuovaCat || "").trim();
    if (!nome) return;
    setCreando("cat");
    try {
      const r = await axios.post(`${API}/menu-categorie`, { nome });
      const creata = r.data?.categoria;
      await ricarica();
      if (creata?.id) onChange(Number(creata.id), null);
      setNuovaCat(null);
      setEsito(r.data?.creata ? `Categoria «${nome}» creata` : `«${nome}» esisteva già: l'ho selezionata`);
    } catch (e) {
      setEsito(messaggioErrore(e, "Categoria non creata"));
    } finally {
      setCreando("");
    }
  };

  const creaSottocategoria = async () => {
    const nome = (nuovaSub || "").trim();
    if (!nome || !sceltaValida) return;
    setCreando("sub");
    try {
      const r = await axios.post(`${API}/menu-categorie/${scelta.id}/sottocategorie`, { nome });
      const creata = r.data?.sottocategoria;
      await ricarica();
      onChange(Number(scelta.id), creata?.id ? Number(creata.id) : null);
      setNuovaSub(null);
      setEsito(r.data?.creata ? `Sezione «${nome}» creata` : `«${nome}» esisteva già: l'ho selezionata`);
    } catch (e) {
      setEsito(messaggioErrore(e, "Sezione non creata"));
    } finally {
      setCreando("");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 10 }}>
        <div>
          <label style={lbl} htmlFor="menu-categoria">Categoria nel Menu</label>
          <select
            id="menu-categoria"
            value={categoriaId == null ? "" : String(categoriaId)}
            onChange={(e) => cambiaCategoria(e.target.value)}
            disabled={caricando}
            style={campo}
          >
            <option value="">Categoria predefinita (Produzione Ceraldi)</option>
            {categorie.map((c) => (
              <option
                key={c.id}
                value={String(c.id)}
                disabled={c.selezionabile !== true}
                title={c.motivo || undefined}
              >
                {nomeCategoria(c)}{c.selezionabile !== true ? " — non disponibile (categoria Qromo)" : ""}
              </option>
            ))}
            {categoriaId != null && !scelta && !caricando && (
              <option value={String(categoriaId)}>Categoria {categoriaId} — non esiste più</option>
            )}
          </select>
        </div>

        <div>
          <label style={lbl} htmlFor="menu-sottocategoria">Sezione dentro la categoria</label>
          <select
            id="menu-sottocategoria"
            value={sottocategoriaId == null ? "" : String(sottocategoriaId)}
            onChange={(e) => onChange(
              categoriaId == null ? null : Number(categoriaId),
              e.target.value === "" ? null : Number(e.target.value),
            )}
            disabled={caricando || !sceltaValida}
            style={{ ...campo, opacity: sceltaValida ? 1 : 0.6 }}
          >
            <option value="">
              {sceltaValida ? "Sezione del reparto (automatica)" : "Scegli prima una categoria"}
            </option>
            {sottocategorie.map((s) => (
              <option key={s.id} value={String(s.id)}>{nomeCategoria(s)}</option>
            ))}
          </select>
        </div>
      </div>

      {caricando && (
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 700, color: "var(--text-2)" }}>
          <Loader2 size={14} aria-hidden="true" /> Leggo le categorie del Menu…
        </div>
      )}

      {!caricando && errore && (
        <div style={{
          display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
          fontSize: 12, fontWeight: 700, color: "var(--danger-text)",
          background: "var(--danger-soft)", border: "1.5px solid var(--danger-border)",
          borderRadius: 10, padding: "8px 10px",
        }}>
          <span>{errore}</span>
          <button type="button" onClick={ricarica} style={{ ...bottoneTenue, minHeight: 36, padding: "6px 10px" }}>
            <RefreshCw size={14} aria-hidden="true" /> Riprova
          </button>
        </div>
      )}

      {!caricando && !errore && categoriaId == null && (
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)" }}>
          Lasciando vuoto, la ricetta va nella categoria predefinita «Produzione Ceraldi»,
          nella sezione del suo reparto.
        </div>
      )}

      {!caricando && !errore && categoriaId != null && !sceltaValida && (
        <div style={{
          fontSize: 12, fontWeight: 700, color: "var(--danger-text)",
          background: "var(--danger-soft)", border: "1.5px solid var(--danger-border)",
          borderRadius: 10, padding: "8px 10px",
        }}>
          {scelta?.motivo
            || "La categoria salvata non è più agganciabile: la ricetta ricade nella categoria predefinita. Scegline un'altra o creane una qui."}
        </div>
      )}

      {avviso}

      {adminAbilitato && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          {nuovaCat === null ? (
            <button type="button" onClick={() => { setNuovaCat(""); setEsito(""); }} style={bottoneTenue}>
              <FolderPlus size={16} aria-hidden="true" /> Crea una categoria
            </button>
          ) : (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", flex: "1 1 240px" }}>
              <input
                value={nuovaCat}
                onChange={(e) => setNuovaCat(e.target.value)}
                placeholder="Nome categoria (es. Colazioni)"
                maxLength={60}
                style={{ ...campo, flex: "1 1 160px", width: "auto" }}
              />
              <button
                type="button" onClick={creaCategoria} disabled={creando === "cat" || !nuovaCat.trim()}
                style={{
                  ...bottoneTenue, border: "none", background: "var(--primary)", color: "#fff",
                  opacity: nuovaCat.trim() ? 1 : 0.5,
                }}
              >
                {creando === "cat" ? "Creo…" : "Crea"}
              </button>
              <button type="button" onClick={() => setNuovaCat(null)} style={bottoneTenue}>Annulla</button>
            </div>
          )}

          {sceltaValida && (nuovaSub === null ? (
            <button type="button" onClick={() => { setNuovaSub(""); setEsito(""); }} style={bottoneTenue}>
              <Tags size={16} aria-hidden="true" /> Crea una sezione qui dentro
            </button>
          ) : (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", flex: "1 1 240px" }}>
              <input
                value={nuovaSub}
                onChange={(e) => setNuovaSub(e.target.value)}
                placeholder="Nome sezione (es. Sfogliate)"
                maxLength={60}
                style={{ ...campo, flex: "1 1 160px", width: "auto" }}
              />
              <button
                type="button" onClick={creaSottocategoria} disabled={creando === "sub" || !nuovaSub.trim()}
                style={{
                  ...bottoneTenue, border: "none", background: "var(--primary)", color: "#fff",
                  opacity: nuovaSub.trim() ? 1 : 0.5,
                }}
              >
                {creando === "sub" ? "Creo…" : "Crea"}
              </button>
              <button type="button" onClick={() => setNuovaSub(null)} style={bottoneTenue}>Annulla</button>
            </div>
          ))}
        </div>
      )}

      {esito && (
        <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-2)" }}>{esito}</div>
      )}
    </div>
  );
}
