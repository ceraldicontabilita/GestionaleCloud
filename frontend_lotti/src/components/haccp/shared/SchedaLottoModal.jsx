import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  X, Snowflake, Store, RotateCcw, ArrowLeftRight, Trash2, Printer, Clock, Layers, AlertTriangle,
  FileText, ChefHat, Search, ExternalLink,
} from "lucide-react";
import Button from "../../ui/Button";
import { API, withToken } from "../../../utils/constants";
import { apiError } from "../../../utils/apiError";
import { getOperatoreNome } from "../../../auth";
import { SceltaMotivo, MOTIVI } from "./SceltaMotivo";
import { apriLottiConRicerca } from "../../../utils/apriLotti";

// Semaforo scadenza — stesse 4 fasce calcolate lato backend
// (servizi/lotto_arricchimento_service.py), qui solo lo stile. Condiviso
// tra CosaUsareOggiView e LottiList: un solo posto per non farle divergere.
export const SEMAFORO = {
  rosso:     { badge: "bg-red-100 text-red-700",       bordo: "border-red-300",     puntino: "bg-red-500" },
  arancione: { badge: "bg-orange-100 text-orange-700", bordo: "border-orange-300",  puntino: "bg-orange-500" },
  giallo:    { badge: "bg-amber-100 text-amber-700",   bordo: "border-amber-300",   puntino: "bg-amber-400" },
  verde:     { badge: "bg-green-100 text-green-700",   bordo: "border-green-200",   puntino: "bg-green-500" },
  grigio:    { badge: "bg-gray-100 text-gray-600",      bordo: "border-gray-200",    puntino: "bg-gray-400" },
};

export const euro = (v) => (v === null || v === undefined) ? "—" : `€ ${Number(v).toFixed(2)}`;

export function posizioneLabel(lotto) {
  const p = lotto.posizione;
  if (p && p.tipo) {
    const nomi = { frigo: "Frigo", congelatore: "Congelatore", abbattitore: "Abbattitore", banco: "Banco", magazzino: "Magazzino" };
    return `${nomi[p.tipo] || p.tipo}${p.nome ? " · " + p.nome : ""}`;
  }
  if (lotto.frigo_numero) return lotto.frigo_numero;
  return "—";
}

// ── Modale azione unica (sposta / congela / recupera / banco / smalti) ──────
export function AzioneModal({ lotto, azione, attrezzature, onClose, onFatto }) {
  const [quantita, setQuantita] = useState(lotto.quantita || 0);
  const [tipoPos, setTipoPos] = useState("frigo");
  const [numero, setNumero] = useState("");
  const [reparto, setReparto] = useState("pasticceria");
  const [motivo, setMotivo] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  const opzioniPerTipo = tipoPos === "congelatore" ? attrezzature.congelatori : attrezzature.frigoriferi;

  const titoli = {
    sposta: "Sposta di posizione", congela: "Congela lotto", recupera: "Recupera in nuova produzione",
    banco: "Manda al banco", smalti: "Smaltisci lotto",
  };

  const conferma = async () => {
    setSaving(true);
    const operatore_nome = getOperatoreNome();
    try {
      if (azione === "sposta") {
        if (!numero.trim()) { toast.error("Indica il frigo/congelatore/reparto di destinazione"); setSaving(false); return; }
        await axios.post(`${API}/lotti/${lotto.id}/sposta-posizione`, null, {
          params: { tipo: tipoPos, numero, reparto, motivo, operatore_nome },
        });
        toast.success("Lotto spostato");
      } else if (azione === "congela") {
        if (!numero.trim()) { toast.error("Indica il congelatore"); setSaving(false); return; }
        await axios.post(`${API}/lotti/${lotto.id}/congela`, null, { params: { numero, motivo, operatore_nome } });
        toast.success("Lotto congelato: scadenza aggiornata");
      } else if (azione === "recupera") {
        await axios.post(`${API}/lotti/${lotto.id}/recupera`, null, {
          params: { quantita, motivo: motivo || "Recuperato in nuova produzione", operatore_nome },
        });
        toast.success("Recupero registrato");
      } else if (azione === "banco") {
        await axios.post(`${API}/lotti/${lotto.id}/manda-al-banco`, null, {
          params: { pezzi: quantita, reparto, operatore_nome },
        });
        toast.success("Mandato al banco");
      } else if (azione === "smalti") {
        await axios.patch(`${API}/lotti/${lotto.id}/smalti`, null, {
          params: { motivo: "smaltito_scaduto", note, operatore_nome },
        });
        toast.success("Lotto smaltito e registrato");
      }
      onFatto();
    } catch (e) {
      toast.error(apiError(e, "Operazione non riuscita"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden">
        <div className="p-4 bg-[#5b7a6b] text-white flex items-center justify-between">
          <h3 className="font-black">{titoli[azione]}</h3>
          <button onClick={onClose}><X size={18} /></button>
        </div>
        <div className="p-4 space-y-3">
          <p className="text-sm text-stone-600">{lotto.prodotto} · {lotto.numero_lotto}</p>

          {(azione === "recupera" || azione === "banco") && (
            <label className="block text-sm">
              Quantità
              <input type="number" min="0.01" step="0.01" value={quantita}
                onChange={(e) => setQuantita(Number(e.target.value))}
                className="w-full mt-1 px-3 py-2 border border-stone-200 rounded-lg text-sm" />
            </label>
          )}

          {(azione === "sposta") && (
            <label className="block text-sm">
              Tipo posizione
              <select value={tipoPos} onChange={(e) => { setTipoPos(e.target.value); setNumero(""); }}
                className="w-full mt-1 px-3 py-2 border border-stone-200 rounded-lg text-sm bg-white">
                <option value="frigo">Frigorifero</option>
                <option value="congelatore">Congelatore</option>
                <option value="abbattitore">Abbattitore</option>
                <option value="banco">Banco</option>
                <option value="magazzino">Magazzino</option>
              </select>
            </label>
          )}

          {(azione === "sposta" && (tipoPos === "frigo" || tipoPos === "congelatore")) && (
            <label className="block text-sm">
              Apparecchio
              <input list="azione-attrezzature" value={numero} onChange={(e) => setNumero(e.target.value)}
                placeholder="es. Frigorifero N°1"
                className="w-full mt-1 px-3 py-2 border border-stone-200 rounded-lg text-sm" />
              <datalist id="azione-attrezzature">
                {opzioniPerTipo.map((a) => <option key={a.numero} value={a.nome} />)}
              </datalist>
            </label>
          )}
          {(azione === "sposta" && (tipoPos === "banco" || tipoPos === "magazzino" || tipoPos === "abbattitore")) && (
            <label className="block text-sm">
              Reparto / dettaglio
              <input value={numero} onChange={(e) => setNumero(e.target.value)}
                placeholder="es. Banco pasticceria"
                className="w-full mt-1 px-3 py-2 border border-stone-200 rounded-lg text-sm" />
            </label>
          )}

          {azione === "congela" && (
            <label className="block text-sm">
              Congelatore
              <input list="azione-congelatori" value={numero} onChange={(e) => setNumero(e.target.value)}
                placeholder="es. Congelatore N°1"
                className="w-full mt-1 px-3 py-2 border border-stone-200 rounded-lg text-sm" />
              <datalist id="azione-congelatori">
                {attrezzature.congelatori.map((a) => <option key={a.numero} value={a.nome} />)}
              </datalist>
            </label>
          )}

          {(azione === "sposta" || azione === "banco") && (
            <label className="block text-sm">
              Reparto
              <select value={reparto} onChange={(e) => setReparto(e.target.value)}
                className="w-full mt-1 px-3 py-2 border border-stone-200 rounded-lg text-sm bg-white">
                <option value="pasticceria">Pasticceria</option>
                <option value="rosticceria">Rosticceria</option>
                <option value="bar">Bar</option>
              </select>
            </label>
          )}

          {/* Motivi a TENDINA, mai tastiera (regola Enzo 04/07/2026: il
              pasticcere ha le mani sporche); "Altro" solo come eccezione */}
          {(azione === "sposta" || azione === "congela" || azione === "recupera") && (
            <SceltaMotivo etichetta="Motivo" opzioni={MOTIVI[azione] || []}
              value={motivo} onChange={setMotivo} />
          )}

          {azione === "smalti" && (
            <SceltaMotivo etichetta="Azione correttiva HACCP (per il registro)" obbligatoria
              tono="danger" opzioni={MOTIVI.smaltimento}
              value={note} onChange={setNote} />
          )}

          <div className="flex gap-2 pt-2">
            <Button variant="secondary" onClick={onClose} className="flex-1">Annulla</Button>
            <Button onClick={conferma} disabled={saving || (azione === "smalti" && !note.trim())} className="flex-1">
              {saving ? "Salvo..." : "Conferma"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Modale "Gemello digitale del lotto" / cronologia completa ────────────────
export function SchedaLottoModal({ lottoId, onClose, onCambiato }) {
  const [scheda, setScheda] = useState(null);
  const [loading, setLoading] = useState(true);
  // Recall per ingrediente aperto dentro la scheda (Enzo 25/07/2026)
  const [recallIng, setRecallIng] = useState(null);
  const [recallRis, setRecallRis] = useState(null);
  const [recallLoad, setRecallLoad] = useState(false);

  const cercaRecall = async (ingrediente) => {
    const testo = String(ingrediente || "").trim();
    if (!testo) return;
    setRecallIng(testo); setRecallRis(null); setRecallLoad(true);
    try {
      const r = await axios.get(`${API}/lotti/recall/cerca`,
        { params: { ingrediente: testo, limit: 200, mesi: 6 } });
      setRecallRis(r.data);
    } catch (e) {
      toast.error("Errore ricerca recall: " + apiError(e));
      setRecallIng(null);
    } finally { setRecallLoad(false); }
  };

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/lotti/${lottoId}/scheda-completa`);
      setScheda(r.data);
    } catch (e) {
      toast.error(apiError(e, "Impossibile caricare la scheda del lotto"));
    } finally {
      setLoading(false);
    }
  }, [lottoId]);

  useEffect(() => { carica(); }, [carica]);

  const stampa = () => {
    if (!scheda) return;
    const id = scheda.lotto.numero_lotto || scheda.lotto.id;
    const url = `${API}/stampa/lotto/${encodeURIComponent(id)}`;
    const win = window.open(withToken(url), "_blank", "width=600,height=900");
    if (!win) toast.error("Popup bloccato dal browser. Consenti i popup per questo sito.");
  };

  const ICONA_EVENTO = {
    creazione: Layers, spostamento: ArrowLeftRight, uso: Store, banco: Store,
    recupero: RotateCcw, congelamento: Snowflake, smaltimento: Trash2,
    spostamento_massivo_anomalia: ArrowLeftRight, rientro_invenduto: Store,
    recall: AlertTriangle,
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="p-4 bg-[#5b7a6b] text-white flex items-center justify-between sticky top-0 z-10">
          <h3 className="font-black">Gemello digitale del lotto</h3>
          <button onClick={onClose}><X size={20} /></button>
        </div>
        {loading && <div className="p-8 text-center text-stone-500">Carico...</div>}
        {!loading && scheda && (
          <div className="p-4 space-y-4">
            {(() => {
              const l = scheda.lotto;
              const sem = SEMAFORO[l.stato_scadenza?.colore] || SEMAFORO.grigio;
              return (
                <>
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h2 className="text-xl font-black text-stone-900">{l.prodotto}</h2>
                      <p className="text-sm text-stone-500">Lotto {l.numero_lotto}</p>
                    </div>
                    <span className={`text-xs font-bold px-2 py-1 rounded-full ${sem.badge}`}>{l.stato_scadenza?.label}</span>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
                    <div><span className="text-stone-400 block text-xs">Prodotto il</span>{l.data_produzione || "—"}</div>
                    <div><span className="text-stone-400 block text-xs">Scade il</span>{l.data_scadenza || "—"}</div>
                    <div><span className="text-stone-400 block text-xs">Quantità prodotta</span>{l.pezzi ?? l.quantita ?? "—"} {l.unita_misura || ""}</div>
                    <div><span className="text-stone-400 block text-xs">Quantità residua</span>{l.quantita ?? "—"} {l.unita_misura || ""}</div>
                    <div><span className="text-stone-400 block text-xs">Posizione</span>{posizioneLabel(l)}</div>
                    <div><span className="text-stone-400 block text-xs">Valore economico</span>{euro(l.valore_economico)}</div>
                    <div className="col-span-2 sm:col-span-3"><span className="text-stone-400 block text-xs">Allergeni</span>{l.allergeni_testo || "—"}</div>
                  </div>

                  {scheda.ingredienti?.length > 0 && (
                    <div className="text-sm">
                      <span className="text-stone-400 block text-xs mb-1">
                        Ingredienti usati <span className="text-[#5b7a6b]">— tocca per il recall</span>
                      </span>
                      <ul className="space-y-1">
                        {scheda.ingredienti.map((ing, i) => (
                          <li key={i}>
                            {/* RECALL VERO (Enzo 25/07/2026): toccando un ingrediente
                                si vedono TUTTI i lotti prodotti con quello — prima
                                l'elenco era solo testo da leggere. */}
                            <button onClick={() => cercaRecall(ing)}
                              className="w-full text-left bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 text-xs hover:bg-[#f2f6f3] hover:border-[#b8d0c2] transition-colors flex items-center justify-between gap-2"
                              title="Vedi tutti i lotti prodotti con questo ingrediente">
                              <span>{ing}</span>
                              <Search size={13} className="text-stone-300 shrink-0" />
                            </button>
                          </li>
                        ))}
                      </ul>
                      {recallIng && (
                        <div className="mt-2 rounded-lg border-2 border-[#e7d6b9] bg-[#f3ead9] p-3">
                          <div className="flex items-center justify-between gap-2 mb-2">
                            <span className="text-xs font-bold text-[#56442d]">
                              Lotti con «{recallIng}»
                            </span>
                            <button onClick={() => { setRecallIng(null); setRecallRis(null); }}
                              className="text-xs font-bold text-stone-500 underline">chiudi</button>
                          </div>
                          {recallLoad && <p className="text-xs text-stone-500">Cerco…</p>}
                          {!recallLoad && recallRis && (
                            recallRis.totale_lotti > 0 ? (
                              <>
                                <p className="text-xs font-bold text-[#8f3829] mb-2">
                                  {recallRis.totale_lotti} lotti coinvolti
                                </p>
                                <div className="space-y-1 max-h-56 overflow-y-auto">
                                  {recallRis.lotti.map((lt) => (
                                    <div key={lt.id} className="bg-white border border-stone-200 rounded-lg px-2 py-1.5 text-xs">
                                      <div className="flex items-center justify-between gap-2">
                                        <span className="font-semibold capitalize">{lt.prodotto}</span>
                                        <span className="font-mono text-[10px] text-[#5b7a6b]">{lt.numero_lotto}</span>
                                      </div>
                                      <div className="text-[11px] text-stone-500">
                                        prod. {lt.data_produzione} · scad. {lt.data_scadenza || "N/D"}
                                        {lt.frigo_numero ? ` · ${lt.frigo_numero}` : ""}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </>
                            ) : (
                              <p className="text-xs text-[#234d3d]">Nessun altro lotto con questo ingrediente.</p>
                            )
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {scheda.ricetta_collegata && (
                    <div className="text-sm bg-stone-50 border border-stone-200 rounded-lg p-3">
                      <span className="text-stone-400 block text-xs">Ricetta collegata</span>
                      {scheda.ricetta_collegata.nome} · {scheda.ricetta_collegata.reparto || "—"}
                    </div>
                  )}

                  {scheda.abbattimento && (
                    <div className="text-sm bg-stone-50 border border-stone-200 rounded-lg p-3">
                      <span className="text-stone-400 block text-xs">Abbattimento</span>
                      {scheda.abbattimento.inizio ? new Date(scheda.abbattimento.inizio).toLocaleString("it-IT") : "—"}
                      {" → "}
                      {scheda.abbattimento.fine ? new Date(scheda.abbattimento.fine).toLocaleString("it-IT") : "in corso"}
                      {scheda.abbattimento.esito ? ` · ${scheda.abbattimento.esito}` : ""}
                    </div>
                  )}

                  {scheda.lotti_fornitori_scalati?.length > 0 && (
                    <div className="text-sm">
                      <span className="text-stone-400 block text-xs mb-1">Provenienza (lotti fornitori scalati)</span>
                      <div className="space-y-1">
                        {scheda.lotti_fornitori_scalati.map((s, i) => (
                          <div key={i} className="bg-stone-50 border border-stone-200 rounded-lg px-3 py-1.5 text-xs flex items-center justify-between gap-2">
                            <span className="min-w-0">
                              {s.fornitore || "—"} · lotto {s.lotto_id_fornitore || s.lotto_id || "—"}
                              {s.fattura_ref ? ` · fattura ${s.fattura_ref}` : ""}
                            </span>
                            {s.fattura_id && (
                              <button
                                onClick={() => window.open(withToken(`${API}/fatture/${s.fattura_id}/visualizza`), "_blank")}
                                className="shrink-0 flex items-center gap-1 text-[#5b7a6b] font-bold hover:underline">
                                <ExternalLink size={11} /> Apri fattura
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div>
                    <span className="text-stone-400 flex items-center gap-1 text-xs mb-2"><Clock size={13}/> Cronologia</span>
                    <div className="space-y-2">
                      {(scheda.movimenti || []).map((m) => {
                        const Icona = ICONA_EVENTO[m.tipo_evento] || Layers;
                        return (
                          <div key={m.id} className="flex gap-2 text-xs border-l-2 border-stone-200 pl-3 py-0.5">
                            <Icona size={14} className="text-[#5b7a6b] mt-0.5 shrink-0" />
                            <div>
                              <span className="font-bold capitalize">{m.tipo_evento.replaceAll("_", " ")}</span>
                              {" — "}{m.motivo || ""}
                              {m.quantita !== null && m.quantita !== undefined ? ` (${m.quantita})` : ""}
                              <div className="text-stone-400">
                                {new Date(m.data_ora).toLocaleString("it-IT")}
                                {m.operatore_nome ? ` · ${m.operatore_nome}` : ""}
                              </div>
                              {m.anomalia_collegata && (
                                <div className="text-orange-700 flex items-center gap-1">
                                  <AlertTriangle size={11} /> Anomalia: {m.anomalia_collegata.descrizione}
                                  {" "}({m.anomalia_collegata.stato})
                                </div>
                              )}
                              {m.richiamo_collegato && (
                                <div className="text-red-700 flex items-center gap-1">
                                  <AlertTriangle size={11} /> Richiamo: {m.richiamo_collegato.ingrediente}
                                  {" "}({m.richiamo_collegato.stato})
                                </div>
                              )}
                              {m.azione_correttiva_haccp && (
                                <div className="text-amber-700">Azione correttiva HACCP: {m.azione_correttiva_haccp}</div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                      {(!scheda.movimenti || scheda.movimenti.length === 0) && (
                        <p className="text-xs text-stone-400">Nessun movimento registrato.</p>
                      )}
                    </div>
                  </div>

                  {/* Collegamenti diretti (mancavano — audit onesto 04/07/2026):
                      ogni dato collegato ora è UN TOCCO, non testo da ricopiare */}
                  <div className="flex flex-wrap gap-2 pt-2 border-t border-stone-100">
                    {scheda.ricetta_collegata?.id && (
                      <Button size="sm" variant="secondary" onClick={() => {
                        try { sessionStorage.setItem("apri_ricetta_id", scheda.ricetta_collegata.id); } catch { /* no-op */ }
                        onClose(); window.location.hash = "ricette";
                      }}><ChefHat size={16}/> Apri ricetta</Button>
                    )}
                    <Button size="sm" variant="secondary"
                      title="Apre la Tracciabilità con la ricerca già compilata su questo lotto"
                      onClick={() => { onClose(); apriLottiConRicerca(l.numero_lotto || l.prodotto || ""); }}>
                      <Search size={16}/> Cerca questo lotto
                    </Button>
                    {/* 25/07/2026 — tolto «Registri HACCP del mese»: quella
                        pagina è il cruscotto di conformità di TUTTA l'attività
                        (temperature, sanificazione, olio, libretti sanitari),
                        non riguarda il singolo lotto. Resta al suo posto nel
                        menu HACCP, dove ha senso cercarla. */}
                  </div>

                  <div className="flex flex-wrap gap-2 pt-2 border-t border-stone-100">
                    <Button size="sm" variant="secondary" onClick={stampa}><Printer size={16}/> Stampa etichetta</Button>
                    <Button size="sm" variant="secondary" onClick={() => {
                      const id = l.numero_lotto || l.id;
                      const win = window.open(withToken(`${API}/stampa/report-lotto/${encodeURIComponent(id)}`), "_blank");
                      if (!win) toast.error("Popup bloccato dal browser. Consenti i popup per questo sito.");
                    }}><FileText size={16}/> Stampa report</Button>
                    {onCambiato && (
                      <>
                        <Button size="sm" variant="secondary" onClick={() => onCambiato("sposta", l)}><ArrowLeftRight size={16}/> Sposta</Button>
                        <Button size="sm" variant="secondary" onClick={() => onCambiato("congela", l)}><Snowflake size={16}/> Congela</Button>
                        <Button size="sm" variant="secondary" onClick={() => onCambiato("banco", l)}><Store size={16}/> Al banco</Button>
                        <Button size="sm" variant="secondary" onClick={() => onCambiato("recupera", l)}><RotateCcw size={16}/> Recupera</Button>
                        <Button size="sm" variant="danger" onClick={() => onCambiato("smalti", l)}><Trash2 size={16}/> Smaltisci</Button>
                      </>
                    )}
                  </div>
                </>
              );
            })()}
          </div>
        )}
      </div>
    </div>
  );
}
