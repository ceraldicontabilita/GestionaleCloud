/**
 * CatalogoFornitoreView — Mini-catalogo per SAIMA o MEPA con:
 *   - Griglia categorie (card con immagine)
 *   - Lista prodotti con immagine, nome, codice articolo, descrizione
 *   - Ricerca full-text
 *   - Modal dettaglio prodotto (immagine grande, codice, confezione, descrizione, link esterno)
 *   - Importa nel dizionario ingredienti (collegamento a food cost)
 *   - Trigger scraping / aggiornamento catalogo
 *
 * Props:
 *   fornitore: "saima" | "mepa"
 *   nome: "SAIMA S.p.a." | "MEPA Alimentari"
 *   colore: es. "blue" | "green"
 */
import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Search, RefreshCw, Package, ChevronRight, Home, Download, Tag, LayoutGrid, List, ExternalLink, Check, Plus, Trash2, X, Info, ZoomIn, ShoppingCart } from "lucide-react";
import { API } from "../../utils/constants";
import PrezzoFornitoreEditor from "./PrezzoFornitoreEditor";

// Carrello UNIFICATO con il libro ordini (OrdiniSmartView usa la stessa chiave):
// così "aggiungi dal catalogo" compare direttamente negli Ordini e diventa un
// ordine al fornitore del catalogo. Niente più carrello separato e scollegato.
// Esportati (richiesta Enzo 03/07/2026, pagina unica cataloghi fornitori):
// riusati anche da CatalogoGenericoView.jsx per Alfa/Il Pasticcere/Tre Marie/
// Sammontana, invece di duplicare la stessa logica localStorage.
export const CART_KEY = "ordini_smart_carrello";
export function leggiCarrello() { try { return JSON.parse(localStorage.getItem(CART_KEY) || "[]"); } catch { return []; } }
export function salvaCarrello(items, persistente = true) {
  localStorage.setItem(CART_KEY, JSON.stringify(items));
  window.dispatchEvent(new Event("ordini_smart_cart_update"));
  if (persistente) {
    axios.put(`${API}/ordini-fornitori/carrello-sospesi`, { righe: items }).catch(() => {
      toast.error("Carrello salvato sul dispositivo, sincronizzazione server non riuscita");
    });
  }
}

export function aggiornaPrezzoNelCarrello(prodotto, prezzo, prezzoFonte = "comunicato_dal_fornitore") {
  const id = prodotto?.id || `ext_${(prodotto?.nome || "").toLowerCase().replace(/\s+/g, "_").slice(0, 40)}`;
  const corrente = leggiCarrello();
  let modificato = false;
  const aggiornato = corrente.map(item => {
    if (item.id !== id) return item;
    modificato = true;
    return {
      ...item,
      prezzo: Number(prezzo) || 0,
      prezzo_fonte: prezzoFonte,
      prezzo_iva_esclusa: true,
    };
  });
  if (modificato) salvaCarrello(aggiornato);
}

export function prezzoFatturaProdotto(p) {
  if (!p?.gia_acquistato) return 0;
  return Number(
    p.prezzo_fattura || p.prezzo_listino || p.prezzo_acquisto_confezione || p.prezzo_singolo || 0
  ) || 0;
}

// Regola acquisti: dopo una fattura XML prevale l'ultimo prezzo realmente
// pagato; prima dell'acquisto si usa il prezzo netto comunicato dal fornitore.
export function prezzoProdotto(p) {
  const prezzoFattura = prezzoFatturaProdotto(p);
  if (prezzoFattura > 0) return prezzoFattura;
  return Number(
    p.prezzo_fornitore || p.prezzoFornitore || p.prezzo_kg || p.prezzo || 0
  ) || 0;
}

export function useCart(fornitoreNome) {
  const [cart, setCart] = useState(leggiCarrello);
  useEffect(() => {
    const sync = () => setCart(leggiCarrello());
    window.addEventListener("ordini_smart_cart_update", sync);
    return () => window.removeEventListener("ordini_smart_cart_update", sync);
  }, []);
  useEffect(() => {
    axios.get(`${API}/ordini-fornitori/carrello-sospesi`).then((response) => {
      const remoti = response.data?.righe || [];
      const locali = leggiCarrello();
      const uniti = Array.from(new Map([...remoti, ...locali].map(item => [item.id, item])).values());
      salvaCarrello(uniti, JSON.stringify(remoti) !== JSON.stringify(uniti));
      setCart(uniti);
    }).catch(() => {});
  }, []);
  const aggiungi = useCallback((p) => {
    const current = leggiCarrello();
    const id = p.id || `ext_${(p.nome || "").toLowerCase().replace(/\s+/g, "_").slice(0, 40)}`;
    if (current.some(c => c.id === id)) { toast("Già nel carrello ordini"); return; }
    // Formato compatibile con OrdiniSmartView (id, nome, fornitore, prezzo, quantita, ...)
    const item = {
      id,
      nome:            p.nome_display || p.nome || id,
      codici:          p.codice_articolo ? [p.codice_articolo] : [],
      fornitore:       fornitoreNome,
      prezzo:          prezzoProdotto(p),   // 0 se mai acquistato → ordinabile lo stesso
      prezzo_fonte:    prezzoFatturaProdotto(p) > 0 ? "fattura_xml" : Number(p.prezzo_fornitore || p.prezzoFornitore || 0) > 0 ? "comunicato_dal_fornitore" : "non_disponibile",
      prezzo_iva_esclusa: true,
      unita_misura:    p.unita_confezione || "pz",
      quantita:        1,
      note:            "",
      sospeso:         false,
      aumento_pct:     null,
      prezzo_precedente: null,
      fonte:           p.fonte || fornitoreNome.toLowerCase(),
    };
    const updated = [...current, item];
    salvaCarrello(updated);
    setCart(updated);
    toast.success(prezzoProdotto(p) > 0
      ? `"${item.nome.slice(0, 32)}" aggiunto agli ordini`
      : `"${item.nome.slice(0, 28)}" aggiunto (prodotto nuovo, senza prezzo)`);

    // Confronto con cataloghi esterni (richiesta Enzo 04/07/2026): se un
    // catalogo aggiunto in "Cataloghi fornitori (web)" (es. offerte
    // settimanali) ha lo STESSO prodotto a un prezzo migliore, avviso —
    // non sostituisco nulla automaticamente, decide sempre l'operatore.
    if (item.prezzo > 0) {
      axios.get(`${API}/fonti-catalogo/confronta`, { params: { nome: item.nome, prezzo_attuale: item.prezzo } })
        .then((r) => {
          const d = r.data;
          if (d?.conviene && d.migliore_offerta) {
            toast.warning(
              `${d.migliore_offerta.fornitore}: stesso prodotto a €${Number(d.migliore_offerta.prezzo).toFixed(2)} (risparmi €${Number(d.risparmio).toFixed(2)})`,
              {
                description: item.nome,
                duration: 12000,
                action: d.migliore_offerta.link_prodotto
                  ? { label: "Vedi offerta", onClick: () => window.open(d.migliore_offerta.link_prodotto, "_blank") }
                  : undefined,
              }
            );
          }
        })
        .catch(() => {});
    }
  }, [fornitoreNome]);
  return { cart, aggiungi, isInCart: (id) => cart.some(c => c.id === id) };
}

const COLORI = {
  saima: { bg: "bg-[#5b7a6b]", light: "bg-[#f2f6f3]", border: "border-[#cfdfd5]", text: "text-[#5b7a6b]", badge: "bg-[#e8efe9] text-[#5b7a6b]" },
  mepa: { bg: "bg-green-700", light: "bg-green-50", border: "border-green-200", text: "text-green-700", badge: "bg-green-100 text-green-700" },
  acquaviva: { bg: "bg-amber-600", light: "bg-amber-50", border: "border-amber-200", text: "text-amber-700", badge: "bg-amber-100 text-amber-700" },
};

const numeroTecnico = (value) => {
  const n = Number(String(value ?? "").replace(",", ".").match(/[\d.]+/)?.[0]);
  return Number.isFinite(n) && n > 0 ? n : 0;
};

const datiTecnici = (prodotto, dettaglio) => {
  const tutto = { ...(prodotto || {}), ...(dettaglio || {}) };
  const specifiche = { ...(prodotto?.specifiche || {}), ...(dettaglio?.specifiche || {}) };
  const pezzi = numeroTecnico(tutto.pz_confezione || tutto.qty_cartone || tutto.pezzi_cartone || specifiche["PZ CONF"] || specifiche["PZ CONF."]);
  const grammi = numeroTecnico(tutto.peso_g || tutto.grammi || tutto.peso_pezzo_g || specifiche.GRAMMI);
  const pesoTotale = numeroTecnico(tutto.peso_totale_cartone_g) || (pezzi && grammi ? pezzi * grammi : 0);
  return { specifiche, pezzi, grammi, pesoTotale };
};

// Modal dettaglio prodotto
const ModalDettaglioProdotto = ({ prodotto, fornitore, onClose, onImporta, onRimuovi, giaNelDizionario, onCarrello, inCart, onPrezzoSalvato }) => {
  const colore = fornitore === "saima" ? "saima" : fornitore === "acquaviva" ? "acquaviva" : "mepa";
  const [dettaglio, setDettaglio] = useState(null);
  const [loadingDet, setLoadingDet] = useState(false);
  const [imgErr, setImgErr] = useState(false);
  const [importando, setImportando] = useState(false);
  const [rimuovendo, setRimuovendo] = useState(false);

  useEffect(() => {
    const caricaDettaglio = async () => {
      setLoadingDet(true);
      try {
        let res;
        if (fornitore === "saima" && prodotto.codice_articolo) {
          res = await axios.get(`${API}/saima/dettaglio-prodotto`, {
            params: { codice: prodotto.codice_articolo }, timeout: 5000,
          });
        } else if (fornitore === "mepa" && prodotto.link_prodotto) {
          res = await axios.get(`${API}/mepa/dettaglio-prodotto`, {
            params: { url: prodotto.link_prodotto }, timeout: 5000,
          });
        } else if (fornitore === "acquaviva" && prodotto.link_prodotto) {
          res = await axios.get(`${API}/acquaviva/dettaglio-prodotto`, {
            params: { url: prodotto.link_prodotto }, timeout: 5000,
          });
        }
        if (res?.data) setDettaglio(res.data);
      } catch { /* silenzioso, mostra dati base */ }
      finally { setLoadingDet(false); }
    };
    caricaDettaglio();
  }, [prodotto, fornitore]);

  // Immagine migliore disponibile: immagine specifica prodotto > immagine URL scraper > categoria
  const imgUrl = dettaglio?.immagine_prodotto || prodotto.immagine_url || prodotto.immagine_categoria || "";
  const isCatImg = imgUrl === prodotto.immagine_categoria && !dettaglio?.immagine_prodotto;

  const descrizione = dettaglio?.descrizione_lunga || dettaglio?.descrizione || prodotto.descrizione || "";
  const confezione = dettaglio?.unita_confezione || prodotto.unita_confezione || "";
  const codice = dettaglio?.codice_verificato || dettaglio?.codice_articolo || prodotto.codice_articolo || "";
  const linkProd = prodotto.link_prodotto || dettaglio?.link_prodotto || "";
  const tecnici = datiTecnici(prodotto, dettaglio);

  const handleImporta = async () => {
    setImportando(true);
    try {
      await onImporta(prodotto);
    } catch { toast.error("Errore importazione"); }
    finally { setImportando(false); }
  };

  const handleRimuovi = async () => {
    setRimuovendo(true);
    try {
      await onRimuovi(prodotto);
    } catch { toast.error("Errore rimozione"); }
    finally { setRimuovendo(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className={`${COLORI[colore].bg} text-white p-4 rounded-t-2xl flex items-start justify-between gap-3`}>
          <div className="flex-1 min-w-0">
            <p className="text-xs opacity-70 font-medium uppercase tracking-wider mb-0.5">
              {prodotto.categoria || (fornitore === "saima" ? "SAIMA S.p.a." : fornitore === "acquaviva" ? "Dolciaria Acquaviva" : "MEPA Alimentari")}
            </p>
            <h3 className="text-base font-bold leading-snug">{prodotto.nome_display || prodotto.nome}</h3>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-white/20 flex-shrink-0">
            <X size={18} />
          </button>
        </div>

        {/* Corpo */}
        <div className="p-5 space-y-4">
          {/* Immagine prodotto */}
          {imgUrl && !imgErr && (
            <div className={`h-52 ${isCatImg ? COLORI[colore].light : "bg-gray-50"} rounded-xl flex items-center justify-center overflow-hidden border border-gray-100`}>
              <img
                src={imgUrl}
                alt={prodotto.nome}
                onError={() => setImgErr(true)}
                className="max-h-full max-w-full object-contain p-3"
              />
            </div>
          )}
          {(!imgUrl || imgErr) && (
            <div className={`h-32 ${COLORI[colore].light} rounded-xl flex items-center justify-center`}>
              <Package size={40} className={COLORI[colore].text + " opacity-30"} />
            </div>
          )}
          {loadingDet && (
            <div className="flex items-center gap-2 text-xs text-gray-400" aria-live="polite">
              <RefreshCw size={13} className="animate-spin" />
              Aggiornamento dettagli dal sito del fornitore…
            </div>
          )}

          {/* Dati prodotto */}
          <div className="space-y-2">
            {codice && (
              <div className="flex items-center gap-2">
                <span className={`text-xs font-bold uppercase ${COLORI[colore].text}`}>Codice</span>
                <span className="text-sm font-mono text-gray-700 bg-gray-100 px-2 py-0.5 rounded">{codice}</span>
              </div>
            )}
            {(prodotto.codice_aqv_2025 || prodotto.codice_aqv_2026) && (
              <div className="grid grid-cols-2 gap-2 rounded-xl bg-amber-50 p-3 text-xs">
                <div><strong className="block text-amber-800">Codice Acquaviva precedente</strong>{prodotto.codice_aqv_2025 || "—"}</div>
                <div><strong className="block text-amber-800">Codice Vandemoortele attuale</strong>{prodotto.codice_aqv_2026 || prodotto.codice_articolo || "—"}</div>
              </div>
            )}
            {confezione && (
              <div className="flex items-center gap-2">
                <span className={`text-xs font-bold uppercase ${COLORI[colore].text}`}>Confezione</span>
                <span className="text-sm text-gray-700">{confezione}</span>
              </div>
            )}
            {prodotto.fornitore_marchio && (
              <div className="flex items-center gap-2">
                <span className={`text-xs font-bold uppercase ${COLORI[colore].text}`}>Marchio</span>
                <span className="text-sm text-gray-700">{prodotto.fornitore_marchio}</span>
              </div>
            )}
            {descrizione && (
              <div className="pt-1">
                <span className={`text-xs font-bold uppercase ${COLORI[colore].text} block mb-1`}>Descrizione</span>
                <p className="text-sm text-gray-600 leading-relaxed">{descrizione}</p>
              </div>
            )}
            {(tecnici.pezzi || tecnici.grammi || tecnici.pesoTotale) && (
              <div className="grid grid-cols-3 gap-2 pt-1">
                <div className="rounded-xl bg-gray-50 p-2 text-center"><strong className="block text-sm text-gray-800">{tecnici.pezzi || "—"}</strong><span className="text-[10px] text-gray-500">pezzi/cartone</span></div>
                <div className="rounded-xl bg-gray-50 p-2 text-center"><strong className="block text-sm text-gray-800">{tecnici.grammi ? `${tecnici.grammi} g` : "—"}</strong><span className="text-[10px] text-gray-500">peso pezzo</span></div>
                <div className="rounded-xl bg-gray-50 p-2 text-center"><strong className="block text-sm text-gray-800">{tecnici.pesoTotale ? `${(tecnici.pesoTotale / 1000).toFixed(2)} kg` : "—"}</strong><span className="text-[10px] text-gray-500">peso cartone</span></div>
              </div>
            )}
            {Object.keys(tecnici.specifiche).length > 0 && (
              <div className="rounded-xl border border-gray-100 p-3"><span className={`mb-2 block text-xs font-bold uppercase ${COLORI[colore].text}`}>Dati dalla scheda online</span><dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">{Object.entries(tecnici.specifiche).map(([k, v]) => <div key={k} className="contents"><dt className="font-semibold text-gray-500">{k}</dt><dd className="text-right text-gray-800">{String(v || "—")}</dd></div>)}</dl></div>
            )}
          </div>

          {/* Riga prezzo / stato acquisto: comunica se è già stato comprato */}
          <div className={`rounded-xl px-3 py-2 text-xs font-medium ${prezzoProdotto(prodotto) > 0 ? "bg-green-50 text-green-700" : "bg-amber-50 text-amber-700"}`}>
            {Number(prodotto.prezzo_fornitore || 0) > 0
              ? `Prezzo comunicato dal fornitore · €${prezzoProdotto(prodotto).toFixed(2)}`
              : prezzoProdotto(prodotto) > 0
              ? `Già acquistato · ultimo prezzo €${prezzoProdotto(prodotto).toFixed(2)} (da fattura)`
              : "Mai acquistato · puoi ordinarlo lo stesso (prodotto nuovo)"}
          </div>

          <PrezzoFornitoreEditor prodotto={prodotto} fonte={fornitore} onSaved={onPrezzoSalvato} />

          {/* Azione principale: aggiungi all'ordine (sempre disponibile, con o senza prezzo) */}
          <button
            onClick={() => { onCarrello && onCarrello(prodotto); }}
            disabled={inCart}
            className={`w-full py-2.5 rounded-xl text-sm font-bold flex items-center justify-center gap-2 transition-colors ${inCart ? "bg-green-100 text-green-700" : "bg-amber-500 text-white hover:bg-amber-600"}`}>
            <ShoppingCart size={15} />
            {inCart ? "✓ Già nel carrello ordini" : "Aggiungi all'ordine"}
          </button>

          {/* Azioni secondarie */}
          <div className="flex gap-2 pt-1">
            {linkProd && (
              <a href={linkProd} target="_blank" rel="noopener noreferrer"
                className="flex-1 py-2 rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors">
                <ExternalLink size={13} /> Vedi sul sito
              </a>
            )}
            {giaNelDizionario ? (
              <button onClick={handleRimuovi} disabled={rimuovendo}
                className="flex-1 py-2 rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 bg-red-50 text-red-600 hover:bg-red-100 transition-colors">
                {rimuovendo ? <RefreshCw size={13} className="animate-spin" /> : <Trash2 size={13} />}
                Non usare in ricette
              </button>
            ) : (
              <button onClick={handleImporta} disabled={importando}
                className={`flex-1 py-2 rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 ${COLORI[colore].bg} text-white hover:opacity-90 transition-opacity`}>
                {importando ? <RefreshCw size={13} className="animate-spin" /> : <Plus size={13} />}
                Usa in ricette
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

// Card categoria
const CardCategoria = ({ cat, onClick, colore }) => {
  const [imgErr, setImgErr] = useState(false);
  return (
    <div onClick={onClick}
      className={`group cursor-pointer bg-white border border-gray-100 rounded-2xl overflow-hidden shadow-sm hover:shadow-md transition-all hover:-translate-y-0.5`}>
      <div className={`h-28 ${COLORI[colore].light} flex items-center justify-center overflow-hidden`}>
        {cat.img && !imgErr ? (
          <img src={cat.img} alt={cat.nome}
            onError={() => setImgErr(true)}
            className="h-full w-full object-contain p-3 group-hover:scale-105 transition-transform" />
        ) : (
          <Package size={36} className={COLORI[colore].text + " opacity-40"} />
        )}
      </div>
      <div className="p-3">
        <p className="text-xs font-semibold text-gray-700 leading-tight line-clamp-2">{cat.nome}</p>
      </div>
    </div>
  );
};

// Card prodotto — clic apre il modal dettaglio
const CardProdotto = ({ prodotto, colore, fornitore, onDettaglio, giaNelDizionario, onCarrello, inCart, preferitoColazione, onTogglePreferito, onToggleRicette, onPrezzoSalvato }) => {
  const [imgErr, setImgErr] = useState(false);
  const imgUrl = prodotto.immagine_url || "";

  return (
    <div
      onClick={() => onDettaglio(prodotto)}
      className={`bg-white border border-gray-100 rounded-xl overflow-hidden shadow-sm hover:shadow-md transition-all group cursor-pointer ${prodotto.gia_acquistato ? "ring-2 ring-emerald-400" : giaNelDizionario ? "ring-1 ring-green-300" : ""}`}>
      {/* Immagine */}
      <div className={`h-32 ${COLORI[colore].light} flex items-center justify-center overflow-hidden relative`}>
        {imgUrl && !imgErr ? (
          <img src={imgUrl} alt={prodotto.nome}
            onError={() => setImgErr(true)}
            className="h-full w-full object-contain p-2 group-hover:scale-105 transition-transform" />
        ) : (
          <Package size={28} className={COLORI[colore].text + " opacity-25"} />
        )}
        {giaNelDizionario && (
          <div className="absolute top-1.5 right-1.5 bg-green-500 text-white rounded-full p-0.5">
            <Check size={9} />
          </div>
        )}
        {prodotto.gia_acquistato && (
          <div className="absolute bottom-1.5 right-1.5 rounded-full bg-emerald-600 px-2 py-1 text-[9px] font-black uppercase text-white shadow-sm">
            Già acquistato
          </div>
        )}
        {/* Preferito colazione ("l'asterisco", richiesta Enzo 03/07/2026):
            va in tutte e 4 le stagioni, indipendente dal carrello ordini. */}
        <button
          onClick={(e) => { e.stopPropagation(); onTogglePreferito(prodotto); }}
          title={preferitoColazione ? "Preferito colazione — tocca per togliere" : "Segna come preferito colazione (va in tutte le stagioni)"}
          className={`absolute top-1.5 left-1.5 w-5 h-5 rounded-full flex items-center justify-center text-xs ${
            preferitoColazione ? "bg-white text-amber-500" : "bg-black/35 text-white"
          }`}>
          {preferitoColazione ? "★" : "☆"}
        </button>
        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors flex items-center justify-center opacity-0 group-hover:opacity-100">
          <ZoomIn size={20} className="text-white drop-shadow" />
        </div>
      </div>
      {/* Banner carrello — sotto foto, sopra testo */}
      <button
        data-testid={`cart-btn-${prodotto.id || prodotto.nome?.slice(0,10)}`}
        onClick={(e) => { e.stopPropagation(); onCarrello(prodotto); }}
        className={`w-full py-1.5 text-[10px] font-bold flex items-center justify-center gap-1 transition-colors border-t border-b ${
          inCart
            ? "bg-green-100 text-green-700 border-green-200"
            : "bg-amber-50 text-amber-700 border-amber-100 hover:bg-amber-100"
        }`}
      >
        <ShoppingCart size={10} />
        {inCart ? "✓ Nel carrello" : "+ Aggiungi all'ordine"}
      </button>
      <button onClick={(e) => { e.stopPropagation(); onToggleRicette(prodotto, giaNelDizionario); }} className={`w-full py-1.5 text-[10px] font-black flex items-center justify-center gap-1 border-b ${giaNelDizionario ? "bg-green-50 text-green-700 border-green-100" : "bg-[#f2f6f3] text-[#4c6b5c] border-[#dce8e0]"}`}>
        {giaNelDizionario ? <Check size={10} /> : <Plus size={10} />}{giaNelDizionario ? "Usato nelle ricette" : "Usa in ricetta"}
      </button>
      {/* Info */}
      <div className="p-2.5 space-y-1">
        <p className="text-xs font-semibold text-gray-800 line-clamp-2 leading-tight">{prodotto.nome_display || prodotto.nome}</p>
        {prodotto.codice_articolo && (
          <div className="flex items-center gap-1">
            <Tag size={9} className="text-gray-400 flex-shrink-0" />
            <span className="text-[10px] text-gray-400 font-mono truncate">{prodotto.codice_articolo}</span>
          </div>
        )}
        {prodotto.descrizione && (
          <p className="text-[10px] text-gray-500 line-clamp-3 leading-snug">{prodotto.descrizione}</p>
        )}
        {(prezzoProdotto(prodotto) > 0) && (
          <p className={`text-xs font-bold ${prezzoFatturaProdotto(prodotto) > 0 ? "text-green-700" : "text-blue-700"}`}>
            €{prezzoProdotto(prodotto).toFixed(2)} · {prezzoFatturaProdotto(prodotto) > 0 ? "ultima fattura" : "netto fornitore"}
          </p>
        )}
        <PrezzoFornitoreEditor
          prodotto={prodotto}
          fonte={fornitore}
          fornitore={fornitore}
          codiceArticolo={prodotto.codice_articolo || prodotto.codice}
          compatto
          onSaved={onPrezzoSalvato}
        />
        <div className={`text-[10px] font-medium flex items-center gap-0.5 ${COLORI[colore].text} opacity-60 group-hover:opacity-100`}>
          <Info size={9} /> Clicca per dettagli
        </div>
      </div>
    </div>
  );
};

// Riga prodotto (vista lista) — clic apre modal
const RigaProdotto = ({ prodotto, colore, fornitore, onDettaglio, giaNelDizionario, onCarrello, inCart, preferitoColazione, onTogglePreferito, onToggleRicette, onPrezzoSalvato }) => {
  const [imgErr, setImgErr] = useState(false);
  const imgUrl = prodotto.immagine_url || "";

  return (
    <div className={`flex items-center gap-3 px-4 py-3 border-b hover:bg-gray-50 ${prodotto.gia_acquistato ? "border-emerald-200 bg-emerald-50/70" : giaNelDizionario ? "border-gray-50 bg-green-50/30" : "border-gray-50"}`}>
      <div onClick={() => onDettaglio(prodotto)} className="cursor-pointer flex items-center gap-3 flex-1 min-w-0">
        <div className={`w-12 h-12 rounded-lg ${COLORI[colore].light} flex items-center justify-center overflow-hidden flex-shrink-0`}>
          {imgUrl && !imgErr ? (
            <img src={imgUrl} alt={prodotto.nome} onError={() => setImgErr(true)} className="w-full h-full object-contain p-1" />
          ) : (
            <Package size={18} className={COLORI[colore].text + " opacity-25"} />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-gray-800 truncate">{prodotto.nome_display || prodotto.nome}</p>
          <p className="text-xs text-gray-400">{prodotto.codice_articolo || ""}{prodotto.unita_confezione ? ` · ${prodotto.unita_confezione}` : ""}</p>
          {prodotto.gia_acquistato && <p className="text-[10px] font-black uppercase text-emerald-700">Già acquistato · da fattura XML</p>}
          {prodotto.descrizione && <p className="text-xs text-gray-500 truncate">{prodotto.descrizione}</p>}
        </div>
      </div>
      <div className="w-44 flex-shrink-0">
        <PrezzoFornitoreEditor
          prodotto={prodotto}
          fonte={fornitore}
          fornitore={fornitore}
          codiceArticolo={prodotto.codice_articolo || prodotto.codice}
          compatto
          onSaved={onPrezzoSalvato}
        />
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <button onClick={() => onToggleRicette(prodotto, giaNelDizionario)} className={`px-2 py-1 rounded-lg text-[10px] font-bold ${giaNelDizionario ? "bg-green-100 text-green-700" : "bg-[#edf4ef] text-[#4c6b5c]"}`}>{giaNelDizionario ? "✓ Ricette" : "+ Ricette"}</button>
        {(prezzoProdotto(prodotto) > 0) && (
          <span className="text-xs font-bold text-gray-600">€{prezzoProdotto(prodotto).toFixed(2)}</span>
        )}
        <button
          onClick={(e) => { e.stopPropagation(); onTogglePreferito(prodotto); }}
          title={preferitoColazione ? "Preferito colazione — tocca per togliere" : "Segna come preferito colazione"}
          className={`px-1.5 py-1 rounded-lg text-xs ${preferitoColazione ? "text-amber-500" : "text-gray-300 hover:text-amber-400"}`}
        >
          {preferitoColazione ? "★" : "☆"}
        </button>
        <button
          data-testid={`cart-btn-lista-${prodotto.id || prodotto.nome?.slice(0,10)}`}
          onClick={(e) => { e.stopPropagation(); onCarrello(prodotto); }}
          className={`px-2 py-1 rounded-lg text-[10px] font-bold flex items-center gap-1 transition-colors ${
            inCart ? "bg-green-100 text-green-700" : "bg-amber-50 text-amber-700 hover:bg-amber-100 border border-amber-200"
          }`}
        >
          <ShoppingCart size={10} />
          {inCart ? "✓" : "+"}
        </button>
      </div>
    </div>
  );
};

// ── URL helpers ──────────────────────────────────────────────────────────────
/** "PANE E PANIFICATI" → "pane-e-panificati" */
const toSlug = (s) => (s || "").toLowerCase().trim().replace(/\s+/g, "-").replace(/[^a-z0-9\-àèéìòùç]/g, "");
/** Trova la categoria originale dal suo slug */
const fromSlug = (slug, cats) => cats.find(c => toSlug(c.nome) === slug)?.nome || null;

/** Legge il segmento categoria dall'hash: #prodotti/saima/canditi → "canditi" */
const getCatFromHash = () => window.location.hash.replace("#", "").split("/")[2] || null;

/** Aggiorna hash a livello categoria: #prodotti/saima/canditi */
const setHashCategoria = (fornitore, catSlug) => {
  const base = `prodotti/${fornitore}`;
  window.location.hash = catSlug ? `${base}/${catSlug}` : base;
};

// Componente principale
export const CatalogoFornitoreView = ({ fornitore, nome, logoUrl }) => {
  const colore = fornitore === "saima" ? "saima" : fornitore === "acquaviva" ? "acquaviva" : "mepa";
  const [categorie, setCategorie] = useState([]);
  const [prodotti, setProdotti] = useState([]);
  // Inizializza categoria dall'URL se presente (slug → nome reale dopo caricamento categorie)
  const [categoriaAttiva, setCategoriaAttivaState] = useState(null);
  const [pendingSlug, setPendingSlug] = useState(() => getCatFromHash());
  const [loading, setLoading] = useState(false);
  const [loadingProd, setLoadingProd] = useState(false);
  const [statoScraping, setStatoScraping] = useState(null);
  const [scrapingInCorso, setScrapingInCorso] = useState(false);
  const [search, setSearch] = useState("");
  const [vistaGriglia, setVistaGriglia] = useState(true);
  const { aggiungi: aggiungiCarrello, isInCart } = useCart(nome);
  const [dizionarioIds, setDizionarioIds] = useState(new Set());
  const [prodottoSelezionato, setProdottoSelezionato] = useState(null);
  // Preferiti colazione (richiesta Enzo 03/07/2026, "l'asterisco ovunque"):
  // stessa stella/meccanismo già costruito per Acquaviva/ricette — marca un
  // prodotto Saima/MePA come da inserire SEMPRE in tutte e 4 le stagioni.
  const [preferitiColazione, setPreferitiColazione] = useState(new Set());
  const autoAvvioTentato = useRef(false);

  /** Wrapper: aggiorna stato + URL */
  const setCategoriaAttiva = useCallback((catNome) => {
    setCategoriaAttivaState(catNome);
    setHashCategoria(fornitore, catNome ? toSlug(catNome) : null);
  }, [fornitore]);

  // Definita PRIMA di caricaCategorie per evitare temporal dead zone
  const caricaProdotti = useCallback(async (categoria = null, q = "") => {
    setLoadingProd(true);
    try {
      const params = { limit: 200 };
      if (categoria) params.categoria = categoria;
      if (q) params.q = q;
      const r = await axios.get(`${API}/${fornitore}/prodotti`, { params });
      const p = fornitore === "mepa" ? (r.data.prodotti || []) : (r.data || []);
      setProdotti(p);
    } catch { toast.error("Errore caricamento prodotti"); }
    finally { setLoadingProd(false); }
  }, [fornitore]);

  // Ref stabile per usare caricaProdotti dentro listener/callback senza deps circolari
  const caricaProdottiRef = useRef(caricaProdotti);
  useEffect(() => { caricaProdottiRef.current = caricaProdotti; }, [caricaProdotti]);

  const caricaCategorie = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/${fornitore}/categorie`);
      const cats = (r.data || []).map(cat => typeof cat === "string" ? { nome: cat, img: "" } : cat);
      setCategorie(cats);
      // Ripristina categoria da slug URL (es. #prodotti/saima/canditi)
      const slug = pendingSlug || getCatFromHash();
      if (slug) {
        const nomeReale = fromSlug(slug, cats);
        if (nomeReale) {
          setCategoriaAttivaState(nomeReale);
          caricaProdottiRef.current(nomeReale, "");
        }
        setPendingSlug(null);
      }
    } catch { toast.error("Errore caricamento categorie"); }
    finally { setLoading(false); }
  }, [fornitore, pendingSlug]); // eslint-disable-line

  // Listener hashchange: tasto indietro/avanti del browser
  useEffect(() => {
    const onHash = () => {
      const slug = getCatFromHash();
      if (!slug) { setCategoriaAttivaState(null); setProdotti([]); return; }
      setCategorie(prev => {
        const nomeReale = fromSlug(slug, prev);
        if (nomeReale) {
          setCategoriaAttivaState(nomeReale);
          caricaProdottiRef.current(nomeReale, "");
        }
        return prev;
      });
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const caricaStato = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/${fornitore}/scraping/stato`);
      setStatoScraping(r.data);
    } catch {}
  }, [fornitore]);

  const caricaDizionario = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/food-cost/dizionario`, {
        params: { limit: 2000, escludi_fornitori: false, proponi_canonici: false },
      });
      const lista = r.data?.prodotti || r.data || [];
      const ids = new Set(
        lista
          .filter(d => d.fonte === fornitore && d.attivo !== false)
          .map(d => d.id)
      );
      setDizionarioIds(ids);
    } catch {}
  }, [fornitore]);

  const caricaPreferitiColazione = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/colazione-acquaviva/preferiti`);
      setPreferitiColazione(new Set(r.data || []));
    } catch {}
  }, []);

  useEffect(() => {
    caricaCategorie();
    caricaStato();
    caricaDizionario();
    caricaPreferitiColazione();
  }, [caricaCategorie, caricaStato, caricaDizionario, caricaPreferitiColazione]);

  // Se il DB e' nuovo, l'amministratore non deve prima trovare e premere un
  // pulsante: avvia una sola volta il popolamento. Durante lo scraping vengono
  // mostrati subito i prodotti gia' persistiti e lo stato si aggiorna da solo.
  useEffect(() => {
    if (!statoScraping || autoAvvioTentato.current) return;
    if (Number(statoScraping.prodotti_nel_db || 0) === 0 && statoScraping.stato !== "in_corso") {
      autoAvvioTentato.current = true;
      axios.post(`${API}/${fornitore}/scraping/avvia`).then(() => {
        setStatoScraping(prev => ({ ...(prev || {}), stato: "in_corso" }));
      }).catch(() => {});
    }
  }, [statoScraping, fornitore]);

  useEffect(() => {
    if (statoScraping?.stato !== "in_corso") return undefined;
    const timer = window.setInterval(async () => {
      await Promise.all([caricaStato(), caricaCategorie()]);
      if (categoriaAttiva || search) caricaProdotti(categoriaAttiva, search);
    }, 7000);
    return () => window.clearInterval(timer);
  }, [statoScraping?.stato, caricaStato, caricaCategorie, caricaProdotti, categoriaAttiva, search]);

  const togglePreferitoColazione = async (prodotto) => {
    const eraPreferito = preferitiColazione.has(prodotto.id);
    setPreferitiColazione(prev => {
      const s = new Set(prev);
      eraPreferito ? s.delete(prodotto.id) : s.add(prodotto.id);
      return s;
    });
    try {
      const res = await axios.post(`${API}/colazione-acquaviva/preferito`, {
        prodotto_id: prodotto.id,
        prodotto_nome: prodotto.nome_display || prodotto.nome,
        foto_url: prodotto.immagine_url || null,
        categoria: prodotto.categoria || null,
        prezzo_vendita: prezzoProdotto(prodotto),
        fonte: prodotto.fonte || fornitore,
      });
      toast.success(res.data.preferito
        ? `⭐ ${prodotto.nome_display || prodotto.nome} aggiunto a tutte e 4 le stagioni`
        : `${prodotto.nome_display || prodotto.nome} tolto dai preferiti`);
    } catch (e) {
      toast.error("Errore preferiti colazione");
      setPreferitiColazione(prev => {
        const s = new Set(prev);
        eraPreferito ? s.add(prodotto.id) : s.delete(prodotto.id);
        return s;
      });
    }
  };

  useEffect(() => {
    if (!search && !categoriaAttiva) { setProdotti([]); return; }
    const t = setTimeout(() => caricaProdotti(categoriaAttiva, search), 400);
    return () => clearTimeout(t);
  }, [search, categoriaAttiva, caricaProdotti]);

  const prodSlug = (p) => {
    const nome = (p?.nome_display || p?.nome || p?.id || "").toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9\-]/g, "").slice(0, 60);
    return nome || p?.id || "";
  };

  const apriProdotto = (p) => {
    setProdottoSelezionato(p);
    const segs = window.location.hash.replace("#", "").split("/");
    segs[3] = prodSlug(p);
    window.location.hash = segs.slice(0, 4).join("/");
  };

  const chiudiProdotto = () => {
    setProdottoSelezionato(null);
    const segs = window.location.hash.replace("#", "").split("/");
    window.location.hash = segs.slice(0, 3).join("/");
  };

  const handleSelectCategoria = (cat) => {
    setCategoriaAttiva(cat.nome);   // aggiorna stato + URL
    setSearch("");
    caricaProdotti(cat.nome, "");
  };

  const handleAvviaScraping = async () => {
    setScrapingInCorso(true);
    try {
      await axios.post(`${API}/${fornitore}/scraping/avvia`);
      toast.success(`Aggiornamento ${nome} avviato in background: puoi continuare a lavorare`, { duration: 6000 });
      setStatoScraping(prev => ({ ...(prev || {}), stato: "in_corso" }));
    } catch { toast.error("Errore avvio scraping"); }
    finally { setTimeout(() => setScrapingInCorso(false), 5000); }
  };

  const handleImportaProdotto = async (prodotto) => {
    if (fornitore === "acquaviva") {
      await axios.post(`${API}/acquaviva/prodotti/${prodotto.id}/usa-in-ricette`);
    } else {
      await axios.patch(`${API}/food-cost/dizionario/${prodotto.id}/aggiorna`, {
        attivo: true,
        [`is_${fornitore}`]: true,
      });
    }
    setDizionarioIds(prev => new Set([...prev, prodotto.id]));
    toast.success(`"${prodotto.nome_display || prodotto.nome}" aggiunto alle ricette`);
  };

  const handleRimuoviProdotto = async (prodotto) => {
    await axios.patch(`${API}/food-cost/dizionario/${prodotto.id}/aggiorna`, {
      attivo: false,
      [`is_${fornitore}`]: false,
    }).catch(() => {});
    setDizionarioIds(prev => {
      const s = new Set(prev);
      s.delete(prodotto.id);
      return s;
    });
    toast.success(`"${prodotto.nome_display || prodotto.nome}" rimosso`);
  };

  const handleToggleRicette = async (prodotto, attivo) => {
    try {
      if (attivo) await handleRimuoviProdotto(prodotto);
      else await handleImportaProdotto(prodotto);
    } catch {
      toast.error("Non riesco ad aggiornare l'uso nelle ricette");
    }
  };

  const prodottiFiltrati = useMemo(() => {
    if (!search) return prodotti;
    const q = search.toLowerCase();
    return prodotti.filter(p =>
      (p.nome || "").toLowerCase().includes(q) ||
      (p.codice_articolo || "").toLowerCase().includes(q) ||
      (p.descrizione || "").toLowerCase().includes(q)
    );
  }, [prodotti, search]);

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* Modal dettaglio */}
      {prodottoSelezionato && (
        <ModalDettaglioProdotto
          prodotto={prodottoSelezionato}
          fornitore={fornitore}
          onClose={() => chiudiProdotto()}
          onImporta={handleImportaProdotto}
          onRimuovi={handleRimuoviProdotto}
          giaNelDizionario={dizionarioIds.has(prodottoSelezionato.id)}
          onCarrello={aggiungiCarrello}
          inCart={isInCart(prodottoSelezionato.id || `ext_${(prodottoSelezionato.nome || "").toLowerCase().replace(/\s+/g, "_").slice(0, 40)}`)}
          onPrezzoSalvato={(dati) => {
            const aggiornato = { ...prodottoSelezionato, ...dati };
            setProdottoSelezionato(aggiornato);
            setProdotti(prev => prev.map(p => p.id === aggiornato.id ? { ...p, ...dati } : p));
            aggiornaPrezzoNelCarrello(aggiornato, dati.prezzo_fornitore);
          }}
        />
      )}

      {/* Header */}
      <div className={`${COLORI[colore].bg} text-white rounded-2xl p-4`}>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h2 className="text-xl font-bold">{nome}</h2>
            <p className="text-sm opacity-80">
              {statoScraping?.prodotti_nel_db > 0
                ? `${statoScraping.prodotti_nel_db} prodotti nel catalogo`
                : statoScraping?.stato === "in_corso" ? "Catalogo in preparazione automatica" : "Catalogo in preparazione automatica"}
              {statoScraping?.ultimo_scraping && (
                <span className="ml-2 opacity-60 text-xs">
                  Aggiornato: {new Date(statoScraping.ultimo_scraping.data).toLocaleDateString("it-IT")}
                </span>
              )}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={handleAvviaScraping} disabled={scrapingInCorso}
              className="flex items-center gap-2 px-4 py-2 bg-white/20 hover:bg-white/30 text-white rounded-xl text-sm font-semibold disabled:opacity-50 transition-all">
              <RefreshCw size={14} className={scrapingInCorso ? "animate-spin" : ""} />
              {scrapingInCorso || statoScraping?.stato === "in_corso" ? "Aggiornamento in background" : "Aggiorna in background"}
            </button>
          </div>
        </div>
      </div>

      {/* Breadcrumb + Ricerca */}
      <div className="flex items-center gap-3">
        {categoriaAttiva && (
          <button onClick={() => { setCategoriaAttiva(null); setProdotti([]); setSearch(""); }}
            className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700">
            <Home size={14} /> Categorie
            <ChevronRight size={14} />
            <span className={`${COLORI[colore].text} font-semibold`}>{categoriaAttiva}</span>
          </button>
        )}
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={14} />
          <input type="text" placeholder={`Cerca in ${categoriaAttiva || "tutto il catalogo"}...`}
            value={search} onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-xl text-sm focus:ring-2 focus:ring-offset-0 focus:outline-none bg-white" />
        </div>
        <div className="flex gap-1 bg-gray-100 rounded-xl p-1">
          <button onClick={() => setVistaGriglia(true)} className={`p-1.5 rounded-lg ${vistaGriglia ? "bg-white shadow-sm" : "text-gray-400"}`}><LayoutGrid size={14} /></button>
          <button onClick={() => setVistaGriglia(false)} className={`p-1.5 rounded-lg ${!vistaGriglia ? "bg-white shadow-sm" : "text-gray-400"}`}><List size={14} /></button>
        </div>
      </div>

      {/* Contenuto */}
      <div className="flex-1 overflow-y-auto">
        {/* Vista categorie */}
        {!categoriaAttiva && !search && (
          loading ? (
            <div className="flex items-center justify-center py-16 text-gray-400">
              <RefreshCw className="animate-spin mr-2" size={18} /> Caricamento categorie...
            </div>
          ) : categorie.length === 0 ? (
            <div className="text-center py-16 text-gray-400">
              <Package size={48} className="mx-auto mb-3 opacity-20" />
              <p className="font-medium">Catalogo in preparazione automatica</p>
              <p className="text-sm mt-1">Puoi continuare a usare l'app: i prodotti compariranno automaticamente.</p>
              <button onClick={handleAvviaScraping} disabled={scrapingInCorso}
                className={`mt-4 px-6 py-2.5 ${COLORI[colore].bg} text-white rounded-xl text-sm font-semibold hover:opacity-90 flex items-center gap-2 mx-auto`}>
                <Download size={16} /> Riprova ora
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
              {categorie.map(cat => (
                <CardCategoria key={cat.nome} cat={cat} onClick={() => handleSelectCategoria(cat)} colore={colore} />
              ))}
            </div>
          )
        )}

        {/* Vista prodotti */}
        {(categoriaAttiva || search) && (
          loadingProd ? (
            <div className="flex items-center justify-center py-16 text-gray-400">
              <RefreshCw className="animate-spin mr-2" size={18} /> Caricamento...
            </div>
          ) : prodottiFiltrati.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <Package size={36} className="mx-auto mb-2 opacity-20" />
              <p className="text-sm">
                {statoScraping?.prodotti_nel_db === 0
                  ? "Catalogo in preparazione automatica: i prodotti compariranno qui"
                  : "Nessun prodotto trovato per questa ricerca"}
              </p>
            </div>
          ) : vistaGriglia ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
              {prodottiFiltrati.map(p => (
                <CardProdotto key={p.id} prodotto={p} colore={colore} fornitore={fornitore}
                  onDettaglio={apriProdotto}
                  giaNelDizionario={dizionarioIds.has(p.id)}
                  onCarrello={aggiungiCarrello}
                  inCart={isInCart(p.id || `ext_${(p.nome||"").toLowerCase().replace(/\s+/g,"_").slice(0,40)}`)}
                  preferitoColazione={preferitiColazione.has(p.id)}
                  onTogglePreferito={togglePreferitoColazione}
                  onToggleRicette={handleToggleRicette}
                  onPrezzoSalvato={(dati) => {
                    const aggiornato = { ...p, ...dati };
                    setProdotti(prev => prev.map(item => item.id === p.id ? aggiornato : item));
                    aggiornaPrezzoNelCarrello(aggiornato, dati.prezzo_fornitore);
                  }} />
              ))}
            </div>
          ) : (
            <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden">
              {prodottiFiltrati.map(p => (
                <RigaProdotto key={p.id} prodotto={p} colore={colore} fornitore={fornitore}
                  onDettaglio={apriProdotto}
                  giaNelDizionario={dizionarioIds.has(p.id)}
                  onCarrello={aggiungiCarrello}
                  inCart={isInCart(p.id || `ext_${(p.nome||"").toLowerCase().replace(/\s+/g,"_").slice(0,40)}`)}
                  preferitoColazione={preferitiColazione.has(p.id)}
                  onTogglePreferito={togglePreferitoColazione}
                  onToggleRicette={handleToggleRicette}
                  onPrezzoSalvato={(dati) => {
                    const aggiornato = { ...p, ...dati };
                    setProdotti(prev => prev.map(item => item.id === p.id ? aggiornato : item));
                    aggiornaPrezzoNelCarrello(aggiornato, dati.prezzo_fornitore);
                  }} />
              ))}
            </div>
          )
        )}
      </div>
    </div>
  );
};

export default CatalogoFornitoreView;
