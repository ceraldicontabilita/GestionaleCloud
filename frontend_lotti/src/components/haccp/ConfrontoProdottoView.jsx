import React, { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, GitMerge, Search, ShoppingCart, TrendingDown, X } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import { API } from "../../utils/constants";
import { apiError } from "../../utils/apiError";
import { aggiungiAlCarrello, dataIt, differenza, euro, euroPezzo, rigaCarrello } from "../../utils/confrontoFornitori";

// Miglior fornitore per articolo, dalle righe delle fatture XML ricevute
// (backend: routers/confronto_fornitori.py). Pensata per lo smartphone: una
// card per articolo, bottoni da 44px, niente tabelle larghe. Lo stesso
// carrello di Ordini (localStorage "ordini_smart_carrello").

const Card = ({ children, className = "" }) => (
  <div className={`rounded-2xl border border-[#e6e0d4] bg-[#fffefb] shadow-sm ${className}`}>{children}</div>
);

function Chip({ attivo, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={attivo}
      className={`min-h-[44px] rounded-full border px-4 text-sm font-bold transition-colors ${
        attivo ? "border-[#5b7a6b] bg-[#5b7a6b] text-white" : "border-[#e6e0d4] bg-[#fffefb] text-[#3f5a4e]"
      }`}
    >
      {children}
    </button>
  );
}

function RigaFornitore({ articolo, riga, migliore, eMigliore, pariMerito }) {
  const aggiungi = () => {
    aggiungiAlCarrello(rigaCarrello(articolo, riga));
    toast.success(`${articolo.nome}: nel carrello da ${riga.fornitore}`);
  };
  const extra = differenza(riga, migliore);
  return (
    <div
      className="flex items-center gap-3 rounded-xl px-3 py-2"
      style={eMigliore
        ? { background: "#eef3ef", border: "1px solid #b8d0c2" }
        : { background: "#fffefb", border: "1px solid #e6e0d4" }}
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="truncate text-sm font-bold text-[#2a3329]">{riga.fornitore}</span>
          {eMigliore && !pariMerito && (
            <span className="inline-flex items-center gap-1 rounded-full bg-[#3d8168] px-2 py-0.5 text-[11px] font-bold text-white">
              <TrendingDown size={12} aria-hidden="true" /> più conveniente
            </span>
          )}
          {eMigliore && pariMerito && (
            <span className="inline-flex items-center gap-1 rounded-full border border-[#b8d0c2] px-2 py-0.5 text-[11px] font-bold text-[#3f5a4e]">
              stesso prezzo · fattura più recente
            </span>
          )}
        </div>
        <div className="mt-0.5 text-[12px] text-[#6b6358]">
          <span className="font-extrabold text-[#3f5a4e] tabular-nums">{euroPezzo(riga.prezzo_pezzo)}</span> al pezzo
          {riga.per_cartone && articolo.pezzi ? <> · {euro(riga.prezzo_confezione)} il cartone</> : null}
          {extra && <span className="text-[#c4894a]"> · {extra}</span>}
        </div>
        <div className="text-[11px] text-[#8a7f70]">
          ultima fattura {dataIt(riga.data)}{riga.acquisti > 1 ? ` · ${riga.acquisti} acquisti` : ""}
        </div>
      </div>
      <button
        type="button"
        onClick={aggiungi}
        aria-label={`Aggiungi ${articolo.nome} dal fornitore ${riga.fornitore} al carrello`}
        className={`flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl ${
          eMigliore ? "bg-[#5b7a6b] text-white" : "border border-[#e6e0d4] bg-[#faf7f0] text-[#3f5a4e]"
        }`}
      >
        <ShoppingCart size={18} aria-hidden="true" />
      </button>
    </div>
  );
}

function CardArticolo({ a }) {
  const migliore = a.migliore ? a.fornitori[0] : null;
  return (
    <Card className="space-y-2.5 p-3.5">
      <div>
        <h3 className="text-[15px] font-extrabold leading-snug text-[#2a3329]" style={{ letterSpacing: "-0.01em" }}>{a.nome}</h3>
        <p className="text-[12px] text-[#6b6358]">
          {a.formato ? <span className="font-bold">{a.formato}</span> : "formato non indicato"}
          {" · "}{a.n_fornitori} fornitor{a.n_fornitori === 1 ? "e" : "i"}
          {a.risparmio_pezzo && Number(a.risparmio_pezzo) > 0 ? ` · risparmi ${euroPezzo(a.risparmio_pezzo)} al pezzo` : ""}
        </p>
      </div>
      {!a.confrontabile && (
        <div className="flex gap-2 rounded-xl border border-[#e8d3b5] bg-[#fbf3e8] px-3 py-2 text-[12px] text-[#7a5a2e]">
          <AlertTriangle size={16} className="mt-0.5 flex-shrink-0" aria-hidden="true" />
          <span>{a.motivo}</span>
        </div>
      )}
      <div className="space-y-1.5">
        {a.fornitori.map((r) => (
          <RigaFornitore key={r.fornitore_id || r.fornitore} articolo={a} riga={r}
            migliore={migliore} eMigliore={migliore === r} pariMerito={a.pari_merito} />
        ))}
      </div>
    </Card>
  );
}

function LatoProposta({ lato, etichetta }) {
  return (
    <div className="rounded-xl border border-[#e6e0d4] bg-[#faf7f0] px-3 py-2">
      <div className="text-[11px] font-bold uppercase tracking-wide text-[#8a7f70]">{etichetta}</div>
      <div className="text-sm font-bold text-[#2a3329]">{lato.descrizione}</div>
      <div className="text-[12px] text-[#6b6358]">
        {lato.fornitori.join(", ")} · {euroPezzo(lato.prezzo_pezzo)} al pezzo · {dataIt(lato.data)}
      </div>
    </div>
  );
}

function CardProposta({ p, onDecisa }) {
  const [busy, setBusy] = useState(false);
  const decidi = async (esito) => {
    setBusy(true);
    try {
      await axios.post(`${API}/confronto-fornitori/decisione`, { chiavi: p.chiavi, esito });
      toast.success(esito === "stesso" ? "Uniti: ora si confrontano i prezzi" : "Segnati come articoli diversi");
      onDecisa();
    } catch (e) {
      toast.error(apiError(e, "Decisione non salvata"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card className="space-y-2 p-3.5">
      <p className="text-[13px] font-bold text-[#3f5a4e]">
        Stesso articolo? <span className="font-normal text-[#6b6358]">({p.a.formato || "stesso formato"})</span>
      </p>
      <LatoProposta lato={p.a} etichetta="Fattura A" />
      <LatoProposta lato={p.b} etichetta="Fattura B" />
      <div className="grid grid-cols-2 gap-2 pt-1">
        <button type="button" disabled={busy} onClick={() => decidi("stesso")}
          className="flex min-h-[48px] items-center justify-center gap-2 rounded-xl bg-[#5b7a6b] text-sm font-bold text-white disabled:opacity-50">
          <Check size={18} aria-hidden="true" /> Sì, è lo stesso
        </button>
        <button type="button" disabled={busy} onClick={() => decidi("diverso")}
          className="flex min-h-[48px] items-center justify-center gap-2 rounded-xl border border-[#e6e0d4] bg-[#fffefb] text-sm font-bold text-[#3f5a4e] disabled:opacity-50">
          <X size={18} aria-hidden="true" /> No, sono diversi
        </button>
      </div>
    </Card>
  );
}

export default function ConfrontoProdottoView() {
  const [q, setQ] = useState("");
  const [vista, setVista] = useState("confronti");   // confronti | tutti | da_confermare
  const [fornitore, setFornitore] = useState("");
  const [dati, setDati] = useState(null);
  const [proposte, setProposte] = useState(null);
  const [loading, setLoading] = useState(false);
  const timer = useRef(null);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      if (vista === "da_confermare") {
        const r = await axios.get(`${API}/confronto-fornitori/da-confermare`);
        setProposte(r.data);
      } else {
        const r = await axios.get(`${API}/confronto-fornitori`, {
          params: { q: q.trim(), solo_confronti: vista === "confronti", fornitore, limit: 200 },
        });
        setDati(r.data);
      }
    } catch (e) {
      toast.error(apiError(e, "Confronto non disponibile"));
    } finally {
      setLoading(false);
    }
  }, [q, vista, fornitore]);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(carica, 300);
    return () => timer.current && clearTimeout(timer.current);
  }, [carica]);

  const daConfermare = proposte?.totale ?? dati?.da_confermare ?? 0;

  return (
    <div className="mx-auto w-full max-w-2xl space-y-3">
      <div>
        <h2 className="text-lg font-extrabold text-[#2a3329]" style={{ letterSpacing: "-0.02em" }}>Miglior fornitore</h2>
        <p className="text-[13px] text-[#6b6358]">
          Ultimo prezzo di ogni fornitore dalle fatture ricevute, confrontato al pezzo. Il più conveniente è in verde con la scritta.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <Chip attivo={vista === "confronti"} onClick={() => setVista("confronti")}>Da confrontare</Chip>
        <Chip attivo={vista === "tutti"} onClick={() => setVista("tutti")}>Tutti</Chip>
        <Chip attivo={vista === "da_confermare"} onClick={() => setVista("da_confermare")}>
          <span className="inline-flex items-center gap-1.5"><GitMerge size={15} aria-hidden="true" /> Da confermare{daConfermare ? ` (${daConfermare})` : ""}</span>
        </Chip>
      </div>

      {vista !== "da_confermare" && (
        <div className="space-y-2">
          <label className="relative block">
            <span className="sr-only">Cerca un articolo</span>
            <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8a7f70]" aria-hidden="true" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Cerca: crodino, coca zero, farina…"
              className="min-h-[48px] w-full rounded-xl border border-[#e6e0d4] bg-[#fffefb] pl-10 pr-3 text-base focus:outline-none focus:ring-2 focus:ring-[#b8d0c2]"
            />
          </label>
          <label className="block">
            <span className="sr-only">Fornitore</span>
            <select
              value={fornitore}
              onChange={(e) => setFornitore(e.target.value)}
              className="min-h-[48px] w-full rounded-xl border border-[#e6e0d4] bg-[#fffefb] px-3 text-base text-[#2a3329]"
            >
              <option value="">Tutti i fornitori</option>
              {(dati?.fornitori || []).map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          </label>
          {dati && (
            <p className="text-[12px] text-[#8a7f70]">
              {dati.trovati} articoli · {dati.con_confronto} con un fornitore più conveniente su {dati.totale_articoli} acquistati
            </p>
          )}
        </div>
      )}

      {loading && <div className="py-8 text-center text-[#8a7f70]">Carico i prezzi dalle fatture…</div>}

      {!loading && vista !== "da_confermare" && dati && dati.articoli.length === 0 && (
        <div className="py-8 text-center text-[#8a7f70]">
          Nessun articolo{q ? ` per «${q}»` : ""}{vista === "confronti" ? " con almeno due fornitori: prova «Tutti»" : ""}.
        </div>
      )}

      {!loading && vista !== "da_confermare" && dati?.articoli.map((a) => <CardArticolo key={a.chiave} a={a} />)}

      {!loading && vista === "da_confermare" && proposte && (
        proposte.proposte.length === 0
          ? <div className="py-8 text-center text-[#8a7f70]">Niente da confermare.</div>
          : (
            <>
              <p className="text-[12px] text-[#8a7f70]">
                Due fornitori scrivono lo stesso articolo in modo diverso? Confermalo una volta e i prezzi si confrontano da soli.
              </p>
              {proposte.proposte.map((p) => <CardProposta key={p.chiavi.join("~")} p={p} onDecisa={carica} />)}
            </>
          )
      )}
    </div>
  );
}
