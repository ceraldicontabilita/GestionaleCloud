// Scheda prodotto: tutta la catena del piatto sotto il suo ID prodotto unico (PRD-000123), lo stesso in Menu e B&B.
// Piatto, prezzo, reparto, ingredienti, allergeni, varianti, aggiunte/rimozioni, costo, food cost, disponibilità,
// foto, valori nutrizionali, vendita sala/delivery e QR. Si legge dal server (`GET /prodotti/{id}/scheda`);
// canali, esaurito, aggiunte e rimozioni si scelgono con tocchi e si salvano su `PUT /ricette/{id}/scheda-vendita`.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { QRCodeSVG } from "qrcode.react";
import { Check, Plus, RefreshCw, Save, X } from "lucide-react";
import { API } from "../../utils/constants";
import { apiError } from "../../utils/apiError";

const SALVIA = "#5b7a6b";
const SALVIA_SCURO = "#3f5a4e";
const LINEA = "#e6e0d4";
const AGGIUNTE_PRONTE = ["Panna", "Crema", "Cioccolato", "Granella", "Senza lattosio"];

const euro = (v) => (v == null ? "—" : `€ ${String(v).replace(".", ",")}`);
const num = (v) => (v == null || v === "" ? "—" : String(v).replace(".", ","));

function Blocco({ titolo, children }) {
  return (
    <section className="rounded-2xl border bg-white p-3" style={{ borderColor: LINEA }}>
      <h4 className="m-0 mb-2 text-xs font-black uppercase tracking-wide text-stone-500">{titolo}</h4>
      {children}
    </section>
  );
}

function Interruttore({ attivo, onClick, children, testid }) {
  return (
    <button type="button" role="switch" aria-checked={attivo} onClick={onClick} data-testid={testid}
      className="flex min-h-[44px] items-center gap-2 rounded-xl border px-4 text-sm font-black"
      style={{ borderColor: attivo ? SALVIA_SCURO : LINEA, background: attivo ? SALVIA : "#fffefb", color: attivo ? "#fff" : "#2a3329" }}>
      {attivo ? <Check size={16} aria-hidden="true" /> : null}{children}
    </button>
  );
}

export default function SchedaProdottoModal({ ricetta, onClose, onSaved }) {
  const [scheda, setScheda] = useState(null);
  const [errore, setErrore] = useState("");
  const [vendita, setVendita] = useState({ sala: true, delivery: true, esaurito: false });
  const [aggiunte, setAggiunte] = useState([]);
  const [rimozioni, setRimozioni] = useState([]);
  const [nuova, setNuova] = useState({ nome: "", prezzo: "" });
  const [salvando, setSalvando] = useState(false);

  const carica = useCallback(async () => {
    setErrore("");
    try {
      const r = await axios.get(`${API}/prodotti/${encodeURIComponent(ricetta.id)}/scheda`, { timeout: 60000 });
      const s = r.data;
      setScheda(s);
      setVendita({ sala: s.vendita.sala, delivery: s.vendita.delivery, esaurito: s.disponibilita.esaurito });
      setAggiunte((s.aggiunte || []).map((a) => ({ nome: a.nome, prezzo: a.prezzo })));
      setRimozioni(s.rimozioni || []);
    } catch (e) {
      setErrore(apiError(e, "Scheda non disponibile"));
    }
  }, [ricetta.id]);

  useEffect(() => { carica(); }, [carica]);

  const aggiungi = (nome) => {
    const n = String(nome || "").trim();
    const prezzo = String(nuova.prezzo).replace(",", ".").trim();
    if (!n) return;
    if (prezzo === "" || Number.isNaN(Number(prezzo)) || Number(prezzo) < 0) { toast.error("Scrivi il prezzo dell'aggiunta (0 se gratis)"); return; }
    if (aggiunte.some((a) => a.nome.toLowerCase() === n.toLowerCase())) { toast.error("Aggiunta già presente"); return; }
    setAggiunte((l) => [...l, { nome: n, prezzo: Number(prezzo).toFixed(2) }]);
    setNuova({ nome: "", prezzo: "" });
  };

  const salva = async () => {
    setSalvando(true);
    try {
      await axios.put(`${API}/ricette/${encodeURIComponent(ricetta.id)}/scheda-vendita`, {
        vendita_sala: vendita.sala, vendita_delivery: vendita.delivery, esaurito: vendita.esaurito,
        aggiunte: aggiunte.map((a) => ({ nome: a.nome, prezzo: Number(a.prezzo) })), rimozioni,
      }, { timeout: 60000 });
      toast.success("Scheda salvata e aggiornata nel Menu");
      onSaved?.();
      await carica();
    } catch (e) {
      toast.error(apiError(e, "Scheda non salvata"));
    } finally {
      setSalvando(false);
    }
  };

  const copia = async (url) => {
    try { await navigator.clipboard.writeText(url); toast.success("Indirizzo copiato"); } catch { toast.error("Copia non riuscita"); }
  };

  const fc = scheda?.costo_ingredienti_e_food_cost;
  const disp = scheda?.disponibilita;
  const nutr = scheda?.valori_nutrizionali;

  return (
    <div onClick={onClose} className="fixed inset-0 z-[60] flex items-center justify-center bg-stone-900/60 p-2 sm:p-4" data-testid="scheda-prodotto">
      <div onClick={(e) => e.stopPropagation()} className="flex h-full max-h-[94vh] w-full max-w-3xl flex-col overflow-hidden rounded-3xl shadow-2xl" style={{ background: "#faf7f0" }}>
        <div className="flex items-center justify-between gap-3 border-b px-4 py-3" style={{ borderColor: LINEA, background: "#fffefb" }}>
          <div className="min-w-0">
            <h3 className="m-0 truncate text-base font-black text-stone-900">{ricetta.nome}</h3>
            <p className="m-0 text-xs font-bold tabular-nums" style={{ color: SALVIA_SCURO }} data-testid="scheda-codice">
              {scheda ? (scheda.codice_prodotto || "ID prodotto non ancora assegnato") : "…"}
            </p>
          </div>
          <button onClick={onClose} aria-label="Chiudi" className="grid h-11 w-11 place-items-center rounded-full bg-stone-100 text-stone-600 hover:bg-stone-200"><X size={18} /></button>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-3">
          {errore && <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-3 text-sm font-bold text-red-700">{errore} <button onClick={carica} className="ml-2 underline">Riprova</button></div>}
          {!scheda && !errore && <div className="grid place-items-center py-16 text-stone-400"><span className="flex items-center gap-2 text-sm font-bold"><RefreshCw className="animate-spin" size={16} /> Carico la scheda…</span></div>}

          {scheda && (<>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Blocco titolo="Prezzo e reparto">
                <p className="m-0 text-sm text-stone-700">Banco <b>{euro(scheda.prezzo.banco)}</b> · Tavolo <b>{euro(scheda.prezzo.tavolo)}</b></p>
                <p className="m-0 mt-1 text-sm text-stone-700">Reparto: <b>{scheda.reparto || "non assegnato"}</b></p>
              </Blocco>
              <Blocco titolo="Costo e food cost">
                <p className="m-0 text-sm text-stone-700">Ingredienti per porzione <b>{euro(fc.costo_porzione)}</b></p>
                <p className="m-0 mt-1 text-sm text-stone-700">Food cost <b>{fc.food_cost_percentuale == null ? "dato non disponibile" : `${num(fc.food_cost_percentuale)}%`}</b>{fc.motivo ? <span className="text-stone-400"> — {fc.motivo}</span> : null}</p>
              </Blocco>
            </div>

            <Blocco titolo="Ingredienti e allergeni">
              <p className="m-0 text-sm text-stone-700">{scheda.ingredienti.length ? scheda.ingredienti.map((i) => i.nome).join(", ") : "Nessun ingrediente inserito"}</p>
              <p className="m-0 mt-1 text-sm text-stone-700">Allergeni: <b>{scheda.allergeni.length ? scheda.allergeni.join(", ") : "nessuno dichiarato"}</b></p>
              {scheda.varianti.length > 0 && <p className="m-0 mt-1 text-sm text-stone-700">Varianti: {scheda.varianti.map((v) => `${v.nome}${v.codice_prodotto ? ` (${v.codice_prodotto})` : ""}`).join(", ")}</p>}
            </Blocco>

            <Blocco titolo="Si vende in">
              <div className="flex flex-wrap gap-2">
                <Interruttore attivo={vendita.sala} testid="canale-sala" onClick={() => setVendita((v) => ({ ...v, sala: !v.sala }))}>Sala</Interruttore>
                <Interruttore attivo={vendita.delivery} testid="canale-delivery" onClick={() => setVendita((v) => ({ ...v, delivery: !v.delivery }))}>Delivery</Interruttore>
                <Interruttore attivo={vendita.esaurito} testid="esaurito" onClick={() => setVendita((v) => ({ ...v, esaurito: !v.esaurito }))}>Esaurito oggi</Interruttore>
              </div>
              <p className="m-0 mt-2 text-xs text-stone-500">
                Giacenza: {disp.ingredienti_in_giacenza == null ? "non leggibile" : disp.ingredienti_in_giacenza ? "ingredienti in giacenza" : `mancano ${disp.ingredienti_mancanti.join(", ") || "alcuni ingredienti"}`}
              </p>
            </Blocco>

            <Blocco titolo="Aggiunte">
              <div className="flex flex-wrap gap-2">
                {aggiunte.map((a) => (
                  <button key={a.nome} type="button" onClick={() => setAggiunte((l) => l.filter((x) => x.nome !== a.nome))} aria-label={`Togli l'aggiunta ${a.nome}`}
                    className="min-h-[44px] rounded-xl border px-3 text-sm font-bold" style={{ borderColor: SALVIA_SCURO, background: "#e8efe9", color: SALVIA_SCURO }}>
                    {a.nome} +{euro(a.prezzo)} ×
                  </button>
                ))}
                {aggiunte.length === 0 && <span className="text-sm text-stone-400">Nessuna aggiunta</span>}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <input aria-label="Prezzo dell'aggiunta in euro" inputMode="decimal" placeholder="Prezzo €" value={nuova.prezzo}
                  onChange={(e) => setNuova((n) => ({ ...n, prezzo: e.target.value }))}
                  className="min-h-[44px] w-28 rounded-xl border px-3 text-sm" style={{ borderColor: LINEA }} />
                {AGGIUNTE_PRONTE.map((n) => (
                  <button key={n} type="button" onClick={() => aggiungi(n)} className="min-h-[44px] rounded-xl border bg-white px-3 text-sm font-bold" style={{ borderColor: LINEA }}><Plus size={13} className="mr-1 inline" aria-hidden="true" />{n}</button>
                ))}
                <input aria-label="Altra aggiunta" placeholder="Altro (scrivi tu)" value={nuova.nome}
                  onChange={(e) => setNuova((n) => ({ ...n, nome: e.target.value }))}
                  onKeyDown={(e) => { if (e.key === "Enter") aggiungi(nuova.nome); }}
                  className="min-h-[44px] w-40 rounded-xl border px-3 text-sm" style={{ borderColor: LINEA }} />
              </div>
            </Blocco>

            <Blocco titolo="Si può togliere">
              <div className="flex flex-wrap gap-2">
                {scheda.ingredienti.map((i) => {
                  const on = rimozioni.includes(i.nome);
                  return (
                    <button key={i.nome} type="button" aria-pressed={on} onClick={() => setRimozioni((l) => (on ? l.filter((x) => x !== i.nome) : [...l, i.nome]))}
                      className="min-h-[44px] rounded-xl border px-3 text-sm font-bold"
                      style={{ borderColor: on ? SALVIA_SCURO : LINEA, background: on ? SALVIA : "#fffefb", color: on ? "#fff" : "#2a3329" }}>
                      {i.nome}
                    </button>
                  );
                })}
              </div>
            </Blocco>

            <Blocco titolo="Valori nutrizionali (stima, non da laboratorio)">
              {nutr.per_porzione ? (
                <p className="m-0 text-sm text-stone-700 tabular-nums">
                  Per porzione: {num(nutr.per_porzione.kcal)} kcal · proteine {num(nutr.per_porzione.prot)} g · carboidrati {num(nutr.per_porzione.carb)} g · grassi {num(nutr.per_porzione.grassi)} g
                  <span className="text-stone-400"> — {nutr.ingredienti_coperti}/{nutr.ingredienti_totali} ingredienti coperti</span>
                </p>
              ) : <p className="m-0 text-sm text-stone-400">Dato non disponibile{nutr.motivo ? `: ${nutr.motivo}` : ""}</p>}
            </Blocco>

            <Blocco titolo="Foto e QR">
              <div className="flex flex-wrap items-start gap-4">
                {scheda.foto ? <img src={scheda.foto} alt={ricetta.nome} className="h-24 w-24 rounded-xl object-cover" /> : <span className="text-sm text-stone-400">Nessuna foto</span>}
                {scheda.qr.scheda ? ["scheda", "sala", "delivery"].map((k) => (
                  <div key={k} className="text-center">
                    <QRCodeSVG value={scheda.qr[k]} size={88} />
                    <button type="button" onClick={() => copia(scheda.qr[k])} className="mt-1 min-h-[44px] text-xs font-black underline" style={{ color: SALVIA_SCURO }}>
                      {k === "scheda" ? "Scheda" : k === "sala" ? "Carta sala" : "Carta delivery"}
                    </button>
                  </div>
                )) : <span className="text-sm text-stone-400">QR non disponibile: {scheda.qr.motivo || "ID prodotto non assegnato"}</span>}
              </div>
            </Blocco>
          </>)}
        </div>

        {scheda && (
          <div className="flex items-center justify-end gap-2 border-t px-4 py-3" style={{ borderColor: LINEA, background: "#fffefb" }}>
            <button onClick={onClose} className="min-h-[44px] rounded-xl border px-4 text-sm font-bold" style={{ borderColor: LINEA }}>Chiudi</button>
            <button onClick={salva} disabled={salvando} data-testid="salva-scheda" className="flex min-h-[44px] items-center gap-2 rounded-xl px-5 text-sm font-black text-white disabled:opacity-60" style={{ background: SALVIA }}>
              <Save size={16} aria-hidden="true" /> {salvando ? "Salvo…" : "Salva scheda"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
