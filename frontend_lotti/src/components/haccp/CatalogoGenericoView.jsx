/**
 * CatalogoGenericoView — catalogo semplice riusabile (richiesta Enzo
 * 03/07/2026, "un'unica pagina" per tutti i fornitori): griglia con
 * ricerca, stella "preferito colazione" e "aggiungi al carrello ordini"
 * (stesso carrello di CatalogoFornitoreView, condiviso con Ordini).
 *
 * A differenza di CatalogoFornitoreView (Saima/MePA: scraping live +
 * collegamento dizionario ingredienti), questo componente NON ha uno
 * scraper: legge prodotti già presenti nel DB (importati da PDF/listino,
 * es. Il Pasticcere/Tre Marie) o da un endpoint esistente (es. Alfa senza
 * glutine). Per fornitori senza ancora nessun dato mostra uno stato vuoto
 * onesto invece di inventare prodotti.
 *
 * Props:
 *   titolo: es. "Tre Marie"
 *   fetchUrl: endpoint GET che ritorna la lista prodotti (o {prodotti:[]})
 *   mapItem: (raw) => {id, nome, foto_url, categoria, prezzo, codice,
 *     giaAcquistato, quantitaFattura, grammi, pezziCartone} — prezzo e
 *     giaAcquistato arrivano SOLO dalle fatture XML (motore unico in
 *     routers/utils.py): prezzo visibile = prodotto già comprato davvero.
 *   emojiVuoto/messaggioVuoto: mostrati quando non ci sono ancora prodotti
 *   coloreAccento: classe Tailwind, es. "amber" | "rose" | "sky"
 */
import { useState, useEffect, useCallback, useMemo } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Search, Package, ShoppingCart, Tag, RefreshCw, Check, Plus, Info, ExternalLink, X, TrendingDown } from "lucide-react";
import { API, fotoSrc } from "../../utils/constants";
import { dataIt, euro, euroPezzo } from "../../utils/confrontoFornitori";
import { aggiornaPrezzoNelCarrello, useCart } from "./CatalogoFornitoreView";
import PrezzoFornitoreEditor from "./PrezzoFornitoreEditor";
import CardCatalogo, { GRIGLIA_CARD, rigaConfronto } from "./CardCatalogo";

const COLORI = {
  amber: { light: "bg-amber-50", text: "text-amber-700", border: "border-amber-200" },
  rose: { light: "bg-rose-50", text: "text-rose-700", border: "border-rose-200" },
  orange: { light: "bg-orange-50", text: "text-orange-700", border: "border-orange-200" },
  yellow: { light: "bg-yellow-50", text: "text-yellow-700", border: "border-yellow-200" },
  sage: { light: "bg-[#f2f6f3]", text: "text-[#5b7a6b]", border: "border-[#cfdfd5]" },
};

// Un prezzo solo per card: il listino se c'e', altrimenti l'ultima fattura XML,
// il netto comunicato dal fornitore o il prezzo di catalogo.
export function prezzoDaMostrare(p) {
  if (p.prezzoListino > 0) {
    return { prezzo: euro(p.prezzoListino), nota: p.unitaVendita ? `× ${p.unitaVendita} · listino` : "listino" };
  }
  if (p.giaAcquistato && p.prezzoFattura > 0) return { prezzo: euro(p.prezzoFattura), nota: "ultima fattura" };
  if (p.prezzoFornitore > 0) return { prezzo: euro(p.prezzoFornitore), nota: "netto fornitore" };
  if (p.prezzo > 0) return { prezzo: euro(p.prezzo), nota: p.giaAcquistato ? "già comprato" : "" };
  return { prezzo: "", nota: "" };
}

export default function CatalogoGenericoView({
  titolo, sourceKey, fetchUrl, mapItem, emojiVuoto = "📦",
  messaggioVuoto = "Nessun prodotto ancora caricato.", coloreAccento = "sage",
  importaPrecaricatoUrl = null, importaPrecaricatoLabel = "Importa dal catalogo PDF",
  confrontoPrezzi = false,
}) {
  // quanti articoli si disegnano: un listino ha migliaia di righe, si cresce con «Mostra altri»
  const PASSO = 120;
  const [visibili, setVisibili] = useState(PASSO);
  // confronto con gli altri fornitori (fatture XML e listini): codice → sintesi
  const [confronto, setConfronto] = useState({});
  const [filtroPrezzo, setFiltroPrezzo] = useState("tutti"); // tutti | qui | altrove
  const colore = COLORI[coloreAccento] || COLORI.sage;
  const [prodotti, setProdotti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [preferiti, setPreferiti] = useState(new Set());
  const [importando, setImportando] = useState(false);
  const [selezionato, setSelezionato] = useState(null);
  const { aggiungi: aggiungiCarrello, isInCart } = useCart(titolo);
  const pesoCartone = (p) => {
    const grammi = Number(String(p?.grammi || "").replace(",", ".").match(/[\d.]+/)?.[0] || 0);
    const pezzi = Number(String(p?.pezziCartone || "").replace(",", ".").match(/[\d.]+/)?.[0] || 0);
    return grammi > 0 && pezzi > 0 ? (grammi * pezzi / 1000).toFixed(2) : "";
  };

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const [resProd, resPref] = await Promise.all([
        fetchUrl ? axios.get(`${API}${fetchUrl}`) : Promise.resolve({ data: [] }),
        axios.get(`${API}/colazione-acquaviva/preferiti`).catch(() => ({ data: [] })),
      ]);
      const raw = Array.isArray(resProd.data) ? resProd.data : (resProd.data?.prodotti || []);
      setProdotti(raw.map(mapItem));
      setPreferiti(new Set(resPref.data || []));
    } catch {
      toast.error(`Errore caricamento ${titolo}`);
    } finally {
      setLoading(false);
    }
  }, [fetchUrl, mapItem, titolo]);

  useEffect(() => { carica(); }, [carica]);

  useEffect(() => {
    if (!confrontoPrezzi || !sourceKey) return;
    axios.get(`${API}/confronto-fornitori/per-catalogo`, { params: { fornitore: sourceKey } })
      .then(r => setConfronto(r.data?.articoli || {}))
      .catch(() => setConfronto({}));
  }, [confrontoPrezzi, sourceKey]);

  useEffect(() => { setVisibili(PASSO); }, [search, filtroPrezzo]);

  const togglePreferito = async (prod) => {
    const eraPreferito = preferiti.has(prod.id);
    setPreferiti(prev => {
      const s = new Set(prev);
      eraPreferito ? s.delete(prod.id) : s.add(prod.id);
      return s;
    });
    try {
      const res = await axios.post(`${API}/colazione-acquaviva/preferito`, {
        prodotto_id: prod.id,
        prodotto_nome: prod.nome,
        foto_url: prod.foto_url || null,
        categoria: prod.categoria || null,
        prezzo_vendita: prod.prezzo || 0,
        fonte: sourceKey,
      });
      toast.success(res.data.preferito
        ? `⭐ ${prod.nome} aggiunto a tutte e 4 le stagioni`
        : `${prod.nome} tolto dai preferiti`);
    } catch {
      toast.error("Errore preferiti colazione");
      setPreferiti(prev => {
        const s = new Set(prev);
        eraPreferito ? s.add(prod.id) : s.delete(prod.id);
        return s;
      });
    }
  };

  const importaPrecaricato = async () => {
    setImportando(true);
    try {
      const res = await axios.post(`${API}${importaPrecaricatoUrl}`);
      toast.success(`${res.data.importati} prodotti importati dal catalogo PDF`);
      await carica();
    } catch {
      toast.error("Errore importazione catalogo");
    } finally {
      setImportando(false);
    }
  };

  const toggleRicette = async (prod) => {
    try {
      if (sourceKey === "alpha") {
        if (prod.inRicette) await axios.patch(`${API}/food-cost/dizionario/${prod.id}/aggiorna`, { attivo: false, is_alpha: false });
        else await axios.post(`${API}/acquaviva/prodotti/${prod.id}/usa-in-ricette`);
      } else {
        const url = `${API}/catalogo-forno/prodotti/${encodeURIComponent(sourceKey)}/${encodeURIComponent(prod.codice)}/usa-in-ricette`;
        if (prod.inRicette) await axios.delete(url); else await axios.post(url);
      }
      setProdotti(prev => prev.map(p => p.id === prod.id ? { ...p, inRicette: !prod.inRicette } : p));
      setSelezionato(prev => prev?.id === prod.id ? { ...prev, inRicette: !prod.inRicette } : prev);
      toast.success(prod.inRicette ? `${prod.nome} rimosso dalle ricette` : `${prod.nome} disponibile nelle ricette`);
    } catch { toast.error("Non riesco ad aggiornare l'uso nelle ricette"); }
  };

  const filtrati = useMemo(() => {
    let lista = prodotti;
    if (filtroPrezzo !== "tutti") {
      lista = lista.filter(p => {
        const c = confronto[p.codice];
        if (!c || !c.migliore) return false;
        return filtroPrezzo === "qui" ? c.questo_migliore : !c.questo_migliore;
      });
    }
    if (!search) return lista;
    const parole = search.toLowerCase().split(/\s+/).filter(Boolean);
    return lista.filter(p => {
      const testo = `${p.nome || ""} ${p.nomeFornitore || ""} ${p.codice || ""} ${p.descrizione || ""} ${p.ean || ""} ${p.categoria || ""} ${p.sottocategoria || ""}`.toLowerCase();
      return parole.every(w => testo.includes(w));
    });
  }, [prodotti, search, filtroPrezzo, confronto]);
  const conConfronto = useMemo(() => Object.values(confronto).filter(c => c.migliore), [confronto]);

  return (
    <div>
      {selezionato && <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/55 p-4" onClick={() => setSelezionato(null)}><div className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-2xl bg-white shadow-2xl" onClick={e => e.stopPropagation()}><div className="flex items-start justify-between gap-3 border-b border-gray-100 p-4"><div><p className={`m-0 text-[10px] font-black uppercase tracking-widest ${colore.text}`}>{titolo}</p><h3 className="m-0 mt-1 text-xl font-black text-gray-900">{selezionato.nome}</h3></div><button onClick={() => setSelezionato(null)} className="rounded-lg p-2 text-gray-500 hover:bg-gray-100"><X size={18}/></button></div><div className="space-y-4 p-5"><div className={`flex h-52 items-center justify-center overflow-hidden rounded-xl ${colore.light}`}>{selezionato.foto_url ? <img src={fotoSrc(selezionato.foto_url)} alt={selezionato.nome} className="h-full w-full object-contain p-3"/> : <Package size={42} className={`${colore.text} opacity-30`}/>}</div><dl className="grid grid-cols-2 gap-3 text-sm"><div><dt className="text-xs font-bold text-gray-400">Codice</dt><dd className="m-0 font-mono">{selezionato.codice || "—"}</dd></div><div><dt className="text-xs font-bold text-gray-400">Categoria</dt><dd className="m-0">{selezionato.categoria || "—"}</dd></div><div><dt className="text-xs font-bold text-gray-400">Peso singolo</dt><dd className="m-0">{selezionato.grammi || "—"}</dd></div><div><dt className="text-xs font-bold text-gray-400">Quantità cartone</dt><dd className="m-0">{selezionato.pezziCartone || "—"}</dd></div><div><dt className="text-xs font-bold text-gray-400">Peso totale cartone</dt><dd className="m-0">{pesoCartone(selezionato) ? `${pesoCartone(selezionato)} kg` : "—"}</dd></div>{selezionato.ean && <div><dt className="text-xs font-bold text-gray-400">EAN</dt><dd className="m-0 font-mono">{selezionato.ean}</dd></div>}{selezionato.prezzoListino > 0 && <div><dt className="text-xs font-bold text-gray-400">Prezzo di listino</dt><dd className="m-0">{euro(selezionato.prezzoListino)}{selezionato.unitaVendita ? ` per ${selezionato.unitaVendita}` : ""}{selezionato.dataListino ? ` · ${dataIt(selezionato.dataListino)}` : ""} · IVA esclusa</dd></div>}</dl>{selezionato.descrizione && <p className="rounded-xl bg-gray-50 p-3 text-sm leading-6 text-gray-600">{selezionato.descrizione}</p>}{selezionato.link_prodotto && <a href={selezionato.link_prodotto} target="_blank" rel="noreferrer" className={`flex items-center gap-2 text-sm font-bold ${colore.text}`}><ExternalLink size={15}/> Apri la scheda originale del fornitore</a>}<PrezzoFornitoreEditor prodotto={selezionato} fonte={sourceKey} fornitore={selezionato.fornitore || sourceKey} codiceArticolo={selezionato.codice} onSaved={(dati) => { const aggiornato = { ...selezionato, prezzoFornitore: dati.prezzo_fornitore, prezzo_fornitore: dati.prezzo_fornitore, prezzo: selezionato.prezzoFattura > 0 ? selezionato.prezzoFattura : dati.prezzo_fornitore }; setProdotti(prev => prev.map(item => item.id === selezionato.id ? aggiornato : item)); setSelezionato(aggiornato); aggiornaPrezzoNelCarrello(aggiornato, aggiornato.prezzo, selezionato.prezzoFattura > 0 ? "fattura_xml" : "comunicato_dal_fornitore"); }} /><button onClick={() => togglePreferito(selezionato)} className="flex w-full items-center justify-center gap-2 rounded-xl border border-[#e6e0d4] py-3 text-sm font-bold text-[#3f5a4e]">{preferiti.has(selezionato.id) ? "★ Preferito colazione" : "☆ Segna come preferito colazione"}</button><button onClick={() => toggleRicette(selezionato)} className={`flex w-full items-center justify-center gap-2 rounded-xl py-3 text-sm font-black ${selezionato.inRicette ? "bg-green-100 text-green-700" : "bg-[#5b7a6b] text-white"}`}>{selezionato.inRicette ? <Check size={16}/> : <Plus size={16}/>} {selezionato.inRicette ? "Usato nelle ricette" : "Usa in ricetta"}</button></div></div></div>}
      <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
        <p className="text-xs font-semibold text-gray-500 uppercase">{filtrati.length} prodotti {titolo}</p>
        {importaPrecaricatoUrl && (
          <button onClick={importaPrecaricato} disabled={importando}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#f2f6f3] border border-[#cfdfd5] text-[#5b7a6b] rounded-lg text-xs font-medium hover:bg-[#dce8e0] disabled:opacity-50">
            <RefreshCw size={12} className={importando ? "animate-spin" : ""} />
            {importando ? "Importazione..." : importaPrecaricatoLabel}
          </button>
        )}
      </div>
      <div className="relative mb-4">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input type="text" placeholder={`Cerca in ${titolo}...`} value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full pl-9 pr-3 py-2.5 rounded-xl border-2 border-gray-200 text-sm outline-none focus:border-gray-300" />
      </div>
      {confrontoPrezzi && conConfronto.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          {[
            { id: "tutti", label: "Tutti" },
            { id: "qui", label: `Più conveniente qui (${conConfronto.filter(c => c.questo_migliore).length})` },
            { id: "altrove", label: `Costa meno altrove (${conConfronto.filter(c => !c.questo_migliore).length})` },
          ].map(f => (
            <button key={f.id} type="button" onClick={() => setFiltroPrezzo(f.id)} aria-pressed={filtroPrezzo === f.id}
              className={`min-h-[44px] rounded-full border px-4 text-sm font-bold ${filtroPrezzo === f.id ? "border-[#5b7a6b] bg-[#5b7a6b] text-white" : "border-[#e6e0d4] bg-[#fffefb] text-[#3f5a4e]"}`}>
              {f.label}
            </button>
          ))}
          <span className="text-[12px] text-[#8a7f70]">Confronto al pezzo con le fatture XML e gli altri listini.</span>
        </div>
      )}

      {loading ? (
        <div className="text-center py-16 text-gray-400 text-sm">Caricamento...</div>
      ) : filtrati.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <p className="text-3xl mb-2">{emojiVuoto}</p>
          <p className="text-sm">{search ? "Nessun risultato per questa ricerca" : messaggioVuoto}</p>
        </div>
      ) : (
        <div className={GRIGLIA_CARD}>
          {filtrati.slice(0, visibili).map(p => {
            const { prezzo, nota } = prezzoDaMostrare(p);
            return (
              <CardCatalogo
                key={p.id}
                testId={`card-${p.id}`}
                nome={p.nome}
                foto={p.foto_url ? fotoSrc(p.foto_url) : ""}
                prezzo={prezzo}
                notaPrezzo={nota}
                confronto={rigaConfronto(confronto[p.codice], euroPezzo)}
                colore={coloreAccento}
                inCart={isInCart(p.id)}
                inRicette={!!p.inRicette}
                preferito={preferiti.has(p.id)}
                onApri={() => setSelezionato(p)}
                onCarrello={() => aggiungiCarrello(p)}
                onRicetta={() => toggleRicette(p)}
                onPreferito={() => togglePreferito(p)}
              />
            );
          })}
        </div>
      )}
      {filtrati.length > visibili && (
        <div className="mt-4 flex justify-center">
          <button type="button" onClick={() => setVisibili(v => v + PASSO)}
            className="min-h-[44px] rounded-xl border border-[#e6e0d4] bg-[#fffefb] px-5 text-sm font-bold text-[#3f5a4e]">
            Mostra altri ({filtrati.length - visibili} ancora)
          </button>
        </div>
      )}
    </div>
  );
}
