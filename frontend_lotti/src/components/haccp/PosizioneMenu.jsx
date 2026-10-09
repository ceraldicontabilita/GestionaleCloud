// Posizione della ricetta nel Menu: categoria, sottocategoria e, se il prodotto c'è già, l'unione con quello del Menu.
// Si sceglie da tendine (le categorie sono quelle del Menu); «Nuova…» crea una categoria o una sottocategoria come eccezione.
// Salva su `PUT /ricette/{id}/destinazione-menu`: la ricetta prende il posto del prodotto scelto (stesso ID, nessun doppione).
import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Link2, Save } from "lucide-react";
import { API } from "../../utils/constants";
import { apiError } from "../../utils/apiError";
import { useCategorieMenu } from "../../hooks/useCategorieMenu";
import { nomeCategoria } from "../../utils/menuVetrina";

const LINEA = "#e6e0d4";
const CAMPO = "min-h-[44px] w-full rounded-xl border bg-white px-3 text-sm font-bold text-stone-800";

const intero = (v) => {
  const n = Number.parseInt(v, 10);
  return Number.isFinite(n) && n > 0 ? n : "";
};

export default function PosizioneMenu({ ricetta, onSaved }) {
  const { dati, errore, ricarica } = useCategorieMenu();
  const [categoria, setCategoria] = useState(intero(ricetta.menu_categoria_id));
  const [sotto, setSotto] = useState(intero(ricetta.menu_sottocategoria_id));
  const [prodotto, setProdotto] = useState(intero(ricetta.menu_prodotto_id));
  const [prodotti, setProdotti] = useState(null);
  const [filtro, setFiltro] = useState("");
  const [nuova, setNuova] = useState("");
  const [salvando, setSalvando] = useState(false);

  const categorie = dati?.categorie || [];
  const sottocategorie = useMemo(
    () => categorie.find((c) => c.id === Number(categoria))?.sottocategorie || [],
    [categorie, categoria],
  );

  useEffect(() => {
    let vivo = true;
    axios.get(`${API}/ricette/${encodeURIComponent(ricetta.id)}/menu-prodotti`, { timeout: 60000 })
      .then((r) => { if (vivo) setProdotti(r.data?.prodotti || []); })
      .catch(() => { if (vivo) setProdotti([]); });
    return () => { vivo = false; };
  }, [ricetta.id]);

  const visibili = useMemo(() => {
    const t = filtro.trim().toLowerCase();
    return (prodotti || []).filter((p) => !t || String(p.nome || "").toLowerCase().includes(t)).slice(0, 80);
  }, [prodotti, filtro]);

  const creaSotto = async () => {
    const nome = nuova.trim();
    if (!nome || !categoria) return;
    try {
      const r = await axios.post(`${API}/menu-categorie/${categoria}/sottocategorie`, { nome });
      await ricarica();
      setSotto(r.data?.sottocategoria?.id || "");
      setNuova("");
    } catch (e) {
      toast.error(apiError(e, "Sottocategoria non creata"));
    }
  };

  const salva = async () => {
    if (Boolean(categoria) !== Boolean(sotto)) { toast.error("Scegli categoria e sottocategoria insieme"); return; }
    setSalvando(true);
    try {
      await axios.put(`${API}/ricette/${encodeURIComponent(ricetta.id)}/destinazione-menu`, {
        categoria_id: Number(categoria) || 0, sottocategoria_id: Number(sotto) || 0, prodotto_id: Number(prodotto) || 0,
      }, { timeout: 60000 });
      toast.success("Posizione nel Menu salvata");
      onSaved?.();
    } catch (e) {
      toast.error(apiError(e, "Posizione non salvata"));
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="space-y-3" data-testid="posizione-menu">
      {errore && <p role="alert" className="m-0 text-sm font-bold text-red-700">{errore}</p>}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <label className="block text-xs font-bold text-stone-500">Categoria
          <select className={CAMPO} style={{ borderColor: LINEA }} value={categoria} data-testid="menu-categoria"
            onChange={(e) => { setCategoria(e.target.value); setSotto(""); }}>
            <option value="">Automatica (dal reparto)</option>
            {categorie.map((c) => <option key={c.id} value={c.id}>{nomeCategoria(c)}</option>)}
          </select>
        </label>
        <label className="block text-xs font-bold text-stone-500">Sottocategoria
          <select className={CAMPO} style={{ borderColor: LINEA }} value={sotto} disabled={!categoria} data-testid="menu-sottocategoria"
            onChange={(e) => setSotto(e.target.value)}>
            <option value="">{categoria ? "Scegli la sottocategoria" : "—"}</option>
            {sottocategorie.map((s) => <option key={s.id} value={s.id}>{nomeCategoria(s)}</option>)}
          </select>
        </label>
      </div>
      {categoria && (
        <div className="flex gap-2">
          <input className={CAMPO} style={{ borderColor: LINEA }} value={nuova} placeholder="Nuova sottocategoria (eccezione)"
            aria-label="Nuova sottocategoria" onChange={(e) => setNuova(e.target.value)} />
          <button type="button" onClick={creaSotto} disabled={!nuova.trim()}
            className="min-h-[44px] rounded-xl border px-4 text-sm font-black disabled:opacity-40" style={{ borderColor: LINEA }}>Crea</button>
        </div>
      )}

      <div className="rounded-xl border p-2" style={{ borderColor: LINEA }}>
        <p className="m-0 mb-2 flex items-center gap-2 text-xs font-black uppercase tracking-wide text-stone-500">
          <Link2 size={14} aria-hidden="true" /> Unisci a un prodotto già nel Menu
        </p>
        {prodotti === null ? <p className="m-0 text-sm text-stone-400">Carico i prodotti…</p> : (<>
          <input className={CAMPO} style={{ borderColor: LINEA }} value={filtro} placeholder="Cerca per nome"
            aria-label="Cerca un prodotto del Menu" onChange={(e) => setFiltro(e.target.value)} />
          <select className={`${CAMPO} mt-2`} style={{ borderColor: LINEA }} value={prodotto} data-testid="menu-prodotto"
            onChange={(e) => setProdotto(e.target.value)} aria-label="Prodotto del Menu a cui unire la ricetta">
            <option value="">Nessuno: la ricetta è un prodotto nuovo</option>
            {visibili.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}{p.prezzo ? ` · ${p.prezzo}` : ""}{p.categoria ? ` · ${p.categoria}` : ""}{p.codice ? ` · ${p.codice}` : ""}
              </option>
            ))}
          </select>
          <p className="m-0 mt-2 text-xs text-stone-500">
            La ricetta prende il posto del prodotto: stesso ID, stesso codice, nessun doppione. Da quel momento si modifica solo da Lotti.
          </p>
        </>)}
      </div>

      <button type="button" onClick={salva} disabled={salvando} data-testid="menu-posizione-salva"
        className="flex min-h-[44px] items-center gap-2 rounded-xl px-5 text-sm font-black text-white disabled:opacity-50" style={{ background: "#5b7a6b" }}>
        <Save size={16} aria-hidden="true" /> {salvando ? "Salvo…" : "Salva posizione"}
      </button>
    </div>
  );
}
