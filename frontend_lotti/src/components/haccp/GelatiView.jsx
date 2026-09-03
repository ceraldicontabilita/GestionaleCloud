import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Plus, Trash2, RefreshCw } from "lucide-react";
import { API } from "../../utils/constants";
import TouchNumberInput from "./shared/TouchNumberInput";

// Ricette base Ceraldi/Galatea — le quantità scalano linearmente su `base` (= somma g ricetta).
// `gruppo` raggruppa la tendina; `prep` = preparazione Galatea; un ingrediente "qb" non scala.
const RICETTE = {
  // ───────────────────── Basi Ceraldi (riferimento 5000 g) ─────────────────────
  "Frutta / Paste grasse – nocciola o pistacchio": {
    base: 5000, gruppo: "Basi Ceraldi",
    ing: { "Set_Core Velluto 540": 1600, Acqua: 2900, "Panna 38%": 0, "Pasta nocciola/pistacchio": 500 },
  },
  "Fiordilatte / base crema semplice": {
    base: 5000, gruppo: "Basi Ceraldi",
    ing: { "Set_Core Velluto 540": 1600, Acqua: 2900, "Panna 38%": 500 },
  },
  Ricotta: {
    base: 5000, gruppo: "Basi Ceraldi",
    ing: { "Set_Core Velluto 540": 1455, Acqua: 2455, "Panna 38%": 545, "Ricotta zuccherata Ceraldi": 545 },
  },
  "Base zuccherine / Superbiscotto": {
    base: 5000, gruppo: "Basi Ceraldi",
    ing: { "Set_Core Velluto 540": 1455, Acqua: 2636, "Panna 38%": 682, "Pasta Superbiscotto": 227 },
  },

  // ───────────── Galatea · Cioccolato Selection (al latte) — per 1 kg ─────────────
  "Cioccolato Giawa (Libera 100)": {
    base: 1000, gruppo: "Galatea · Selection al latte", cat: "cioccolato",
    ing: { "Set_Core Libera 100 C/F": 45, "Latte fresco intero (bollente)": 635,
      "Latte Monorigine Giawa (70712)": 200, Saccarosio: 60, Destrosio: 25,
      "Cacao 22/24 Galatea (14031)": 20, "Latte magro in polvere": 15 },
    prep: "Pastorizzare la miscela. Monorigine di Giava: aromi delicati di cacao e caramello, note acidule di banana e ananas.",
  },
  "Cioccolato Giawa (Velluto 100)": {
    base: 1000, gruppo: "Galatea · Selection al latte", cat: "cioccolato",
    ing: { "Set_Core Velluto 100 C": 60, "Latte fresco intero (bollente)": 635,
      "Latte Monorigine Giawa (70712)": 200, Saccarosio: 60, Destrosio: 25,
      "Cacao 22/24 Galatea (14031)": 20 },
    prep: "Pastorizzare la miscela.",
  },
  "Cioccolato Oompa-Loompa (Libera 100 + Cocoa Supreme)": {
    base: 1000, gruppo: "Galatea · Selection al latte", cat: "cioccolato",
    ing: { "Set_Core Libera 100 C/F": 50, "Latte fresco intero (bollente)": 575,
      "Cocoa Supreme (14033)": 50, Saccarosio: 135, Destrosio: 30,
      "Panna 35% (no carragenine)": 130, "Latte magro in polvere": 30 },
    prep: "Pastorizzare la miscela. Cocoa Supreme: blend tendente all'amaro, note di frutta fresca, vaniglia e cannella.",
  },
  "Cioccolato Oompa-Loompa (Velluto 100 + Cocoa Supreme)": {
    base: 1000, gruppo: "Galatea · Selection al latte", cat: "cioccolato",
    ing: { "Set_Core Velluto 100 C": 65, "Latte fresco intero (bollente)": 573,
      "Cocoa Supreme (14033)": 50, Saccarosio: 137, Destrosio: 25,
      "Panna 35% (no carragenine)": 130, "Latte magro in polvere": 20 },
    prep: "Pastorizzare la miscela.",
  },

  // ──────── Galatea · Cioccolato Gourmet (sorbetti fondente monorigine) — 1 kg ────────
  "Sorbetto fondente Nanarivo — Madagascar 67,4%": {
    base: 1000, gruppo: "Galatea · Gourmet fondente", cat: "cioccolato",
    ing: { "Fondente Monorigine Nanarivo 67,4% (70711)": 190, "Set_Core Grand Cru (70150)": 220,
      "Acqua bollente": 590 },
    prep: "Pastorizzare. Madagascar: dolce e intenso, tocco amaro, note di lampone, ginepro, agrumi, albicocca.",
  },
  "Sorbetto fondente Kichwa — Ecuador 70,4%": {
    base: 1000, gruppo: "Galatea · Gourmet fondente", cat: "cioccolato",
    ing: { "Fondente Monorigine Kichwa 70,4% (70710)": 180, "Set_Core Grand Cru (70150)": 230,
      "Acqua bollente": 590 },
    prep: "Pastorizzare. Ecuador: aromi tostati, sentore fruttato/acidulo, note di rum, whisky e tabacco.",
  },
  "Sorbetto fondente Micondo — Sao Thomé 70%": {
    base: 1000, gruppo: "Galatea · Gourmet fondente", cat: "cioccolato",
    ing: { "Fondente Monorigine Micondo 70% (70709)": 180, "Set_Core Grand Cru (70150)": 230,
      "Acqua bollente": 590 },
    prep: "Pastorizzare. Sao Thomé: cacao tostato, note di albicocca, frutti rossi, agrumi e tè.",
  },
  "Sorbetto fondente Brazilia — Brasile 66,8%": {
    base: 1000, gruppo: "Galatea · Gourmet fondente", cat: "cioccolato",
    ing: { "Fondente Monorigine Brazilia 66,8% (70708)": 190, "Set_Core Grand Cru (70150)": 220,
      "Acqua bollente": 590 },
    prep: "Pastorizzare. Brasile: spiccato sentore di cacao, sfumature amare e asprezza rinfrescante.",
  },

  // ──────────── Galatea · Cioccolato Emotion / Gourmet creativo — 1 kg ────────────
  "Supreme Dolce Croccante — Arancia e Crak'n Ciok": {
    base: 1000, gruppo: "Galatea · Emotion / creativo", cat: "cioccolato",
    ing: { "Core_Inside The One (70116)": 10, "Cocoa Supreme (14033)": 50,
      "Latte fresco intero (bollente)": 575, "Panna 35% (no carragenine)": 140,
      "Latte magro in polvere": 45, Saccarosio: 120, Destrosio: 60,
      "Variegato Crak'n Ciok (70417)": "qb", "Scorza di 1 arancia per kg": "qb" },
    prep: "Unire i liquidi con la scorza d'arancia (no parte bianca), infusione a caldo, in frigo dalla sera prima. Aggiungere Cocoa Supreme e le polveri, mixare, pastorizzare. Mantecare e variegare con Crak'n Ciok.",
  },
  "Dark Fresco Pungente — Limone e Zenzero": {
    base: 1002, gruppo: "Galatea · Emotion / creativo", cat: "cioccolato",
    ing: { "Set_Core Grand Cru (70150)": 230, "Fondente Monorigine Micondo 70,4% (70709)": 180,
      "Zenzero in polvere": 2, "Acqua bollente": 590, "Buccia di limone": "qb" },
    prep: "Limone e zenzero in infusione in acqua bollente; aggiungere cioccolato e polveri con acqua ancora calda, mixare. Riposo 15–20 min. Mantecare; decorare con zest o limone candito e scaglie di cioccolato.",
  },
  "Dark Dolce Speziato — Pera e Cannella": {
    base: 1002, gruppo: "Galatea · Emotion / creativo", cat: "cioccolato",
    ing: { "Set_Core Grand Cru (70150)": 230, "Fondente Monorigine Micondo 70,4% (70709)": 180,
      "Cannella in polvere": 2, "Acqua bollente": 590, "Variegato Pera": "qb" },
    prep: "Aggiungere all'acqua bollente cannella, cioccolato e polveri, mixare. Riposo 15–20 min. Mantecare e in uscita variegare con pera e polvere di cannella.",
  },
  "Grand Supreme — Nocciola e Caffè": {
    base: 1005, gruppo: "Galatea · Emotion / creativo", cat: "cioccolato",
    ing: { "Core_Inside The One (70116)": 10, "Cocoa Supreme (14033)": 50,
      "Latte fresco intero (bollente)": 570, "Panna 35% (no carragenine)": 90,
      "Latte magro in polvere": 45, "Caffè Lio": 15, Saccarosio: 120, Destrosio: 60,
      "Pasta Nocciola TGT": 40, "Caffè macinato": 5 },
    prep: "Miscelare polveri e Cocoa Supreme con latte, panna, nocciola e caffè Lio. Mixare e pastorizzare. Mantecare e a −4/−5 °C aggiungere il caffè macinato. In uscita variegare con granella di nocciole.",
  },
};
const RICETTE_KEYS = Object.keys(RICETTE);
// Tendina raggruppata per `gruppo` (preserva l'ordine di inserimento).
const RICETTE_GRUPPI = RICETTE_KEYS.reduce((acc, k) => {
  const g = RICETTE[k].gruppo || "Altre";
  (acc[g] = acc[g] || []).push(k);
  return acc;
}, {});
// % di acqua per frutto (fonte CREA / tabelle nutrizionali). Quando aggiungi frutta
// frullata, l'acqua della ricetta va ridotta SOLO della parte acquosa del frutto:
// 100 g di pera (84%) tolgono 84 g d'acqua; 100 g di anguria (95%) ne tolgono 95.
const ACQUA_FRUTTA = {
  Anguria: 0.95, Fragola: 0.91, Melone: 0.90, Pesca: 0.89, Arancia: 0.87,
  Albicocca: 0.86, Lampone: 0.85, "Frutti di bosco": 0.86, Ananas: 0.86,
  Mandarino: 0.85, Pera: 0.84, Mela_verde: 0.85, "Mela verde": 0.85, Kiwi: 0.83,
  Ciliegia: 0.82, Limone: 0.89, Mango: 0.83, Banana: 0.75,
};
const FRUTTE = Object.keys(ACQUA_FRUTTA).filter((k) => k !== "Mela_verde");
const pctAcqua = (f) => ACQUA_FRUTTA[f] ?? 0.88;
// L'anguria e' quasi tutta acqua: la frutta riempie e l'acqua sparisce (anche il campo grammi).
const FRUTTA_SENZA_ACQUA = new Set(["Anguria"]);
// La frutta si aggiunge solo alla base Frutta: per creme/zuccherine il blocco non compare.
const baseAccettaFrutta = (nomeRicetta) => (nomeRicetta || "").startsWith("Frutta");
const fmtG = (n) => Math.round(n).toLocaleString("it-IT") + " g";

const CAT_LABEL = { crema: "Crema", frutta: "Frutta", cioccolato: "Cioccolato" };
const CAT_DOT = { crema: "bg-amber-500", frutta: "bg-emerald-500", cioccolato: "bg-amber-900" };

function opzioniGustiRaggruppate(gusti) {
  return ["crema", "frutta", "cioccolato"].map((categoria) => ({
    categoria,
    gusti: gusti.filter((gusto) => gusto.categoria === categoria),
  })).filter((gruppo) => gruppo.gusti.length > 0);
}

const inputCls =
  "w-full rounded-xl border border-stone-300 bg-white px-3 py-2.5 text-base text-stone-900 focus:border-[#5b7a6b] focus:outline-none focus:ring-2 focus:ring-[#5b7a6b]/20";
const labelCls = "mb-1 block text-xs font-bold uppercase tracking-wide text-stone-500";

function Tabs({ tab, setTab }) {
  const items = [
    ["calcolo", "🧮 Calcolo ricetta"],
    ["invenduti", "🍨 Invenduti"],
    ["produzioni", "📒 Produzioni"],
    ["report", "📊 Riepilogo"],
    ["prodotti", "📦 Prodotti Galatea"],
  ];
  return (
    <div className="flex flex-wrap gap-2 rounded-2xl border border-stone-200 bg-white p-1.5 shadow-sm">
      {items.map(([k, label]) => (
        <button
          key={k}
          onClick={() => setTab(k)}
          className={`flex-1 whitespace-nowrap rounded-xl px-3 py-2 text-sm font-bold transition ${
            tab === k ? "bg-[#5b7a6b] text-white shadow" : "text-stone-500 hover:bg-stone-50"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

// ───────────────────────── Calcolo ─────────────────────────
function CalcoloTab({ onProdotto }) {
  const [recipeT, setRecipeT] = useState(RICETTE_KEYS[0]);
  const [totale, setTotale] = useState(5000);
  const [fruttaT, setFruttaT] = useState("Fragola");
  const [fruttaGT, setFruttaGT] = useState(0);
  const [saved, setSaved] = useState(false);

  // Recupero gelato rientrato (invenduti) da incorporare nel rinfuso del gelato nuovo
  const [usaRecupero, setUsaRecupero] = useState(false);
  const [dispo, setDispo] = useState([]);       // [{gusto, categoria, disponibile_g}]
  const [gustiList, setGustiList] = useState([]);
  const [recGusto, setRecGusto] = useState("");
  const [recQty, setRecQty] = useState("");
  const [rinGusto, setRinGusto] = useState(""); // registrazione di un nuovo rientro
  const [rinQty, setRinQty] = useState("");
  const [mostraNuovoRientro, setMostraNuovoRientro] = useState(false);

  const caricaDispo = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/gelati/invenduti-disponibili`);
      setDispo(r.data?.disponibili || []);
    } catch { setDispo([]); }
    try {
      const g = await axios.get(`${API}/gelati/gusti`);
      setGustiList(g.data?.gusti || []);
    } catch { /* tendina rientro resta col testo libero */ }
  }, []);
  useEffect(() => { caricaDispo(); }, [caricaDispo]);

  const recDisp = dispo.find((d) => d.gusto === recGusto)?.disponibile_g || 0;
  const recuperato = (usaRecupero && recGusto) ? Math.min(Number(recQty) || 0, recDisp) : 0;
  const nuovo = Math.max(0, (Number(totale) || 0) - recuperato);

  const registraRientro = async () => {
    if (!rinGusto.trim() || !(Number(rinQty) > 0)) { toast.error("Indica gusto e peso del gelato rientrato"); return; }
    const cat = gustiList.find((x) => x.nome === rinGusto)?.categoria || "crema";
    try {
      await axios.post(`${API}/gelati/invenduti`, { gusto: rinGusto.trim(), categoria: cat, quantita_g: Number(rinQty) });
      setRecGusto(rinGusto.trim());
      setRecQty("");
      toast.success(`${rinGusto.trim()}: ${fmtG(Number(rinQty))} salvati in giacenza`);
      setRinGusto(""); setRinQty("");
      setMostraNuovoRientro(false);
      await caricaDispo();
    } catch { toast.error("Errore nella registrazione del rientro"); }
  };

  const righeTot = useMemo(() => {
    const r = RICETTE[recipeT];
    const t = nuovo;  // la ricetta vera scala sul NUOVO da produrre (totale − recuperato)
    if (t <= 0) return null;
    let righe = Object.entries(r.ing).map(([n, amt]) =>
      typeof amt === "number" ? { n, q: (amt / r.base) * t } : { n, qb: true });
    const acquaQ = righe.find((x) => x.n === "Acqua")?.q || 0;
    const fg = !baseAccettaFrutta(recipeT) ? 0
      : FRUTTA_SENZA_ACQUA.has(fruttaT) ? acquaQ
      : Number(fruttaGT) || 0;
    // quanta ACQUA togliere: solo la parte acquosa del frutto
    const acquaDaTogliere = FRUTTA_SENZA_ACQUA.has(fruttaT) ? acquaQ : fg * pctAcqua(fruttaT);
    let warnFrutta = null;
    if (fg > 0) {
      // La frutta frullata sostituisce pari grammi di acqua (bilanciamento).
      const acqua = righe.find((x) => x.n === "Acqua");
      let notaFrutta = null;
      if (acqua) {
        if (acquaDaTogliere > acqua.q) warnFrutta = `Attenzione: ${fmtG(fg)} di ${fruttaT} apportano ${fmtG(acquaDaTogliere)} d'acqua, più dell'acqua della ricetta (${fmtG(acqua.q)}). Acqua a zero, ricetta sbilanciata.`;
        else if (FRUTTA_SENZA_ACQUA.has(fruttaT)) notaFrutta = `${fruttaT} ${fmtG(fg)} (95% acqua): sostituisce TUTTA l'acqua della ricetta (acqua a zero).`;
        else notaFrutta = `${fruttaT} ${fmtG(fg)} (${Math.round(pctAcqua(fruttaT)*100)}% acqua) → tolgo ${fmtG(acquaDaTogliere)} d'acqua: acqua a ${fmtG(Math.max(0, acqua.q - acquaDaTogliere))}.`;
        acqua.q = Math.max(0, acqua.q - acquaDaTogliere);
      }
      const rigaFrutta = { n: `${fruttaT} (frullata)`, q: fg, frutta: true };
      const iA = righe.findIndex((x) => x.n === "Acqua");
      if (iA >= 0) righe.splice(iA + 1, 0, rigaFrutta); else righe.push(rigaFrutta);
      return { righe, warnFrutta, notaFrutta };
    }
    return { righe, warnFrutta };
  }, [recipeT, nuovo, fruttaT, fruttaGT]);

  const registra = async () => {
    const t = Number(totale) || 0;
    if (t <= 0) return;
    if (usaRecupero && recGusto && (Number(recQty) || 0) > recDisp) {
      toast.error(`Di ${recGusto} ci sono solo ${fmtG(recDisp)} disponibili in giacenza.`);
      return;
    }
    // Se è un gelato alla frutta, il gusto scelto entra nel nome della produzione
    // (così il lotto è "Gelato Frutta — Fragola/Limone/Mango/Anguria…", non generico).
    const conFrutta = baseAccettaFrutta(recipeT) && (FRUTTA_SENZA_ACQUA.has(fruttaT) || Number(fruttaGT) > 0);
    const ricettaNome = conFrutta ? `Frutta — ${fruttaT}` : recipeT;
    const recuperi = recuperato > 0 ? [{ gusto: recGusto, quantita_g: recuperato }] : [];
    try {
      // peso_g = TOTALE finito; il backend scala il recupero dagli invenduti e
      // registra il lotto come "nuovo + recuperato".
      await axios.post(`${API}/gelati/produzioni`, { ricetta: ricettaNome, peso_g: t, modalita: "totale", recuperi });
      if (recuperi.length) { setRecQty(""); setRecGusto(""); setUsaRecupero(false); caricaDispo(); }
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
      onProdotto?.();
    } catch (e) {
      toast.error("Errore nel salvataggio della produzione");
    }
  };

  return (
    <div className="space-y-4">
      {/* Quantità totale */}
      <div className="rounded-3xl border border-stone-200 bg-white p-5 shadow-sm">
        <h3 className="m-0 mb-3 text-lg font-black text-stone-900">Quantità totale</h3>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className={labelCls}>Ricetta</label>
            <select className={inputCls} value={recipeT} onChange={(e) => setRecipeT(e.target.value)}>
              {Object.entries(RICETTE_GRUPPI).map(([g, keys]) => (
                <optgroup key={g} label={g}>
                  {keys.map((k) => <option key={k}>{k}</option>)}
                </optgroup>
              ))}
            </select>
          </div>
          <div>
            <label className={labelCls}>Peso totale da produrre (g)</label>
            <TouchNumberInput value={totale} onChange={setTotale} min={1} title="Peso totale da produrre" presets={[1000, 2000, 3000, 5000]} />
          </div>
        </div>
        {baseAccettaFrutta(recipeT) && (
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div>
            <label className={labelCls}>➕ Aggiungi frutta (frullata)</label>
            <select className={inputCls} value={fruttaT} onChange={(e) => setFruttaT(e.target.value)}>
              {FRUTTE.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          </div>
          {FRUTTA_SENZA_ACQUA.has(fruttaT) ? (
            <div className="flex items-end"><div className="w-full rounded-xl border-l-4 border-emerald-500 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">🍉 L'anguria sostituisce <b>tutta</b> l'acqua della ricetta: niente acqua, grammi calcolati da soli.</div></div>
          ) : (
          <div>
            <label className={labelCls}>Frutta (g) — scala l'acqua di pari grammi</label>
            <TouchNumberInput value={fruttaGT} onChange={setFruttaGT} min={0} title={`Grammi di ${fruttaT}`} presets={[250, 500, 1000, 1500]} />
          </div>
          )}
        </div>
        )}
        {righeTot && (
          <>
            {righeTot.warnFrutta && (
              <div className="mt-3 rounded-xl border-l-4 border-amber-500 bg-amber-50 p-3 text-sm font-semibold text-amber-800">{righeTot.warnFrutta}</div>
            )}
            {righeTot.notaFrutta && (
              <div className="mt-3 rounded-xl border-l-4 border-emerald-500 bg-emerald-50 p-3 text-sm font-semibold text-emerald-800">🍓 {righeTot.notaFrutta}</div>
            )}
            <div className="mt-4 overflow-x-auto"><table className="w-full border-collapse text-sm">
              <thead>
                <tr className="bg-stone-100 text-stone-600">
                  <th className="rounded-l-lg p-2.5 text-left font-bold">Ingrediente</th>
                  <th className="rounded-r-lg p-2.5 text-right font-bold">Quantità</th>
                </tr>
              </thead>
              <tbody>
                {righeTot.righe.map((r) => (
                  <tr key={r.n} className={`border-b border-stone-100 ${r.frutta ? "bg-emerald-50" : ""}`}>
                    <td className="p-2.5 font-semibold text-stone-800">{r.n}</td>
                    <td className="p-2.5 text-right font-black text-stone-900">{r.qb ? "q.b." : fmtG(r.q)}</td>
                  </tr>
                ))}
                <tr>
                  <td className="border-t-2 border-stone-800 p-2.5 font-black">{recuperato > 0 ? "Nuovo da produrre" : "Totale"}</td>
                  <td className="border-t-2 border-stone-800 p-2.5 text-right font-black">{fmtG(nuovo)}</td>
                </tr>
                {recuperato > 0 && (
                  <>
                    <tr>
                      <td className="p-2.5 text-sm font-semibold text-emerald-700">+ Recuperato ({recGusto})</td>
                      <td className="p-2.5 text-right text-sm font-bold text-emerald-700">{fmtG(recuperato)}</td>
                    </tr>
                    <tr>
                      <td className="p-2.5 font-black text-stone-900">= Totale finito</td>
                      <td className="p-2.5 text-right font-black text-stone-900">{fmtG(Number(totale) || 0)}</td>
                    </tr>
                  </>
                )}
              </tbody>
            </table></div>

            {RICETTE[recipeT].prep && (
              <div className="mt-3 rounded-xl border-l-4 border-[#5b7a6b] bg-[#eef3ef] p-3 text-sm text-stone-700">
                <span className="font-bold text-[#5b7a6b]">Preparazione Galatea:</span> {RICETTE[recipeT].prep}
              </div>
            )}

            {/* Recupero gelato rientrato dagli invenduti */}
            <div className="mt-4 rounded-2xl border border-stone-200 bg-stone-50 p-4">
              <label className="flex min-h-12 cursor-pointer items-center gap-3 text-sm font-bold text-stone-800">
                <input type="checkbox" checked={usaRecupero} onChange={(e) => setUsaRecupero(e.target.checked)} className="h-6 w-6 flex-none accent-[#5b7a6b]" />
                ♻️ Recupera gelato rientrato dal banco
              </label>
              {usaRecupero && (
                <div className="mt-3 space-y-4">
                  <div className="rounded-xl border-l-4 border-[#5b7a6b] bg-[#eef3ef] p-3 text-sm leading-relaxed text-stone-700">
                    <p className="m-0 font-black text-[#4a6657]">Come funziona la giacenza</p>
                    <p className="m-0 mt-1"><b>Salva rientro</b> registra il gelato tornato dal banco, ma non lo usa ancora. Scegli poi quanto riutilizzare qui sotto: la quantità viene scalata dalla giacenza e collegata alla tracciabilità solo quando premi <b>Registra produzione</b>.</p>
                  </div>
                  {/* 1 · porta un rientro in giacenza */}
                  {dispo.length > 0 && <button
                    type="button"
                    onClick={() => setMostraNuovoRientro((aperto) => !aperto)}
                    className="min-h-14 w-full rounded-xl border-2 border-dashed border-[#5b7a6b]/50 bg-white px-4 text-left text-sm font-black text-[#4a6657] hover:bg-[#f5f8f5]"
                  >
                    {mostraNuovoRientro ? "− Nascondi inserimento rientro" : "+ Il gelato è appena rientrato dal banco?"}
                  </button>}
                  {(mostraNuovoRientro || dispo.length === 0) && (
                  <div className="rounded-xl border border-dashed border-stone-300 bg-white p-3">
                    <p className="m-0 text-sm font-black text-stone-800">Registra il gelato appena rientrato</p>
                    <p className="m-0 mb-3 mt-1 text-xs text-stone-500">Scegli il gusto, pesa ciò che è rimasto e salvalo.</p>
                    <div className="grid gap-2 sm:grid-cols-3">
                      <select className={inputCls} value={rinGusto} onChange={(e) => setRinGusto(e.target.value)}>
                        <option value="">Scegli il gusto</option>
                        {opzioniGustiRaggruppate(gustiList).map((gruppo) => (
                          <optgroup key={gruppo.categoria} label={CAT_LABEL[gruppo.categoria]}>
                            {gruppo.gusti.map((x) => <option key={x.nome} value={x.nome}>{x.nome}</option>)}
                          </optgroup>
                        ))}
                      </select>
                      <TouchNumberInput value={rinQty} onChange={setRinQty} min={1} title="Peso del gelato rientrato" placeholder="Inserisci peso" presets={[250, 500, 1000, 1500]} />
                      <button onClick={registraRientro} className="min-h-14 rounded-xl bg-stone-700 px-4 py-2.5 text-sm font-black text-white hover:bg-stone-800">Salva rientro in giacenza</button>
                    </div>
                  </div>
                  )}
                  {/* 2 · recupera dalla giacenza */}
                  {dispo.length === 0 ? (
                    <p className="rounded-xl bg-amber-50 p-3 text-sm font-semibold text-amber-800">La giacenza è vuota. Registra prima il gelato rientrato qui sopra.</p>
                  ) : (
                  <div>
                    <p className="m-0 text-sm font-black text-stone-800">Quanto vuoi riutilizzare adesso?</p>
                    <p className="m-0 mb-3 mt-1 text-xs text-stone-500">Tocca il gusto disponibile, poi inserisci i grammi.</p>
                    <div className="mb-3 grid grid-cols-2 gap-2 lg:grid-cols-3">
                      {dispo.map((d) => (
                        <button
                          type="button"
                          key={d.gusto}
                          onClick={() => { setRecGusto(d.gusto); setRecQty(""); }}
                          className={`min-h-16 rounded-xl border-2 px-3 py-2 text-left transition ${recGusto === d.gusto ? "border-[#5b7a6b] bg-[#e8efe9] text-[#3f5b4d]" : "border-stone-200 bg-white text-stone-700 hover:border-[#5b7a6b]/50"}`}
                        >
                          <span className="block text-sm font-black">{d.gusto}</span>
                          <span className="mt-1 block text-xs font-bold">{fmtG(d.disponibile_g)} disponibili</span>
                        </button>
                      ))}
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div>
                        <label className={labelCls}>Gusto scelto</label>
                        <div className="flex min-h-12 items-center rounded-xl border border-stone-200 bg-white px-4 text-sm font-black text-stone-800">{recGusto || "Tocca un gusto qui sopra"}</div>
                      </div>
                      <div>
                        <label className={labelCls}>Quantità da recuperare (g){recGusto ? ` — max ${fmtG(recDisp)}` : ""}</label>
                        <TouchNumberInput
                          value={recQty}
                          onChange={setRecQty}
                          min={1}
                          max={recGusto ? recDisp : undefined}
                          disabled={!recGusto}
                          title={`Quantità di ${recGusto || "gelato"} da riutilizzare`}
                          placeholder={recGusto ? "Inserisci grammi" : "Scegli prima il gusto"}
                          presets={[250, 500, 1000, recDisp]}
                        />
                      </div>
                    </div>
                    {recGusto && Number(recQty) > recDisp && (
                      <p className="mt-2 text-xs font-semibold text-rose-600">Di {recGusto} ci sono solo {fmtG(recDisp)} disponibili.</p>
                    )}
                    {recuperato > 0 && (
                      <p className="mt-2 text-xs font-semibold text-emerald-700">
                        Recuperi {fmtG(recuperato)} di {recGusto} → la ricetta produce {fmtG(nuovo)} nuovi; totale finito {fmtG(Number(totale) || 0)}. Restano {fmtG(recDisp - recuperato)} in giacenza.
                      </p>
                    )}
                  </div>
                  )}
                </div>
              )}
            </div>

            <button
              onClick={registra}
              className="mt-4 inline-flex items-center gap-2 rounded-xl bg-[#5b7a6b] px-4 py-2.5 text-sm font-black text-white hover:bg-[#4a6657]"
            >
              <Plus size={16} /> Registra produzione
            </button>
            {saved && <span className="ml-3 text-sm font-bold text-emerald-600">Produzione registrata ✓</span>}
          </>
        )}
      </div>
      <p className="px-1 text-xs text-stone-400">
        Ricette: tabelle di produzione “base ceraldi” (Gelinova/Galatea). Le quantità scalano in proporzione al peso totale.
      </p>
    </div>
  );
}

// ───────────────────────── Invenduti ─────────────────────────
function InvendutiTab() {
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [gusto, setGusto] = useState("");
  const [gustiList, setGustiList] = useState([]);
  const [altroGusto, setAltroGusto] = useState(false);
  const [categoria, setCategoria] = useState("crema");
  const [qty, setQty] = useState("");
  const [data, setData] = useState(new Date().toISOString().slice(0, 10));

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/gelati/invenduti`);
      setList(r.data?.invenduti || []);
      try {
        const g = await axios.get(`${API}/gelati/gusti`);
        setGustiList(g.data?.gusti || []);
      } catch { /* tendina vuota: resta il campo testo */ }
    } catch (e) {
      setList([]);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    carica();
  }, [carica]);

  const aggiungi = async () => {
    if (!gusto.trim() || !(Number(qty) > 0)) {
      toast.error("Inserisci gusto e quantità");
      return;
    }
    try {
      await axios.post(`${API}/gelati/invenduti`, {
        gusto: gusto.trim(),
        categoria,
        quantita_g: Number(qty),
        data,
      });
      setGusto("");
      setAltroGusto(false);
      setQty("");
      carica();
    } catch (e) {
      toast.error("Errore nel salvataggio");
    }
  };
  const elimina = async (id) => {
    try {
      await axios.delete(`${API}/gelati/invenduti/${id}`);
      carica();
    } catch (e) {}
  };
  const cambiaEsito = async (id, esito) => {
    try {
      await axios.post(`${API}/gelati/invenduti/${id}/esito?esito=${esito}`);
      carica();
    } catch (e) { toast.error("Errore aggiornamento esito"); }
  };

  return (
    <div className="space-y-4">
      <div className="rounded-3xl border border-stone-200 bg-white p-5 shadow-sm">
        <h3 className="m-0 mb-3 text-lg font-black text-stone-900">Aggiungi gelato invenduto</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <label className={labelCls}>Gusto</label>
            {!altroGusto ? (
              <select
                className={inputCls}
                value={gusto}
                onChange={(e) => {
                  const v = e.target.value;
                  if (v === "__altro__") { setAltroGusto(true); setGusto(""); return; }
                  setGusto(v);
                  const sel = gustiList.find((x) => x.nome === v);
                  if (sel?.categoria) setCategoria(sel.categoria);
                }}
              >
                <option value="">— scegli il gusto —</option>
                {gustiList.map((x) => (
                  <option key={x.nome} value={x.nome}>{x.nome}</option>
                ))}
                <option value="__altro__">➕ Altro gusto (scrivi)…</option>
              </select>
            ) : (
              <div className="flex gap-2">
                <input className={inputCls} autoFocus value={gusto} onChange={(e) => setGusto(e.target.value)} placeholder="Nuovo gusto (entra in tendina per sempre)" />
                <button type="button" onClick={() => { setAltroGusto(false); setGusto(""); }} className="rounded-xl border border-stone-200 px-3 text-sm font-bold text-stone-500 hover:bg-stone-50">Tendina</button>
              </div>
            )}
          </div>
          <div>
            <label className={labelCls}>Categoria</label>
            <select className={inputCls} value={categoria} onChange={(e) => setCategoria(e.target.value)}>
              <option value="crema">Crema</option>
              <option value="frutta">Frutta</option>
              <option value="cioccolato">Cioccolato</option>
            </select>
          </div>
          <div>
            <label className={labelCls}>Quantità (g)</label>
            <TouchNumberInput value={qty} onChange={setQty} min={1} title="Quantità del gelato invenduto" placeholder="Inserisci grammi" presets={[250, 500, 1000, 1500]} />
          </div>
          <div>
            <label className={labelCls}>Data calo banco</label>
            <input className={inputCls} type="date" value={data} onChange={(e) => setData(e.target.value)} />
          </div>
          <div className="flex items-end">
            <button onClick={aggiungi} className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#5b7a6b] px-4 py-2.5 text-sm font-black text-white hover:bg-[#4a6657]">
              <Plus size={16} /> Aggiungi
            </button>
          </div>
        </div>
      </div>

      <div className="rounded-3xl border border-stone-200 bg-white p-5 shadow-sm">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="m-0 text-lg font-black text-stone-900">Registro invenduti</h3>
          <button onClick={carica} className="rounded-lg p-1.5 text-stone-400 hover:bg-stone-100"><RefreshCw size={16} /></button>
        </div>
        {loading ? (
          <p className="py-6 text-center text-sm text-stone-400">Caricamento…</p>
        ) : list.length === 0 ? (
          <p className="py-6 text-center text-sm text-stone-400">Nessun gelato invenduto registrato.</p>
        ) : (
          <div className="divide-y divide-stone-100">
            {list.map((it) => {
              const es = it.esito || "rientrato";
              return (
              <div key={it.id} className="flex flex-wrap items-center gap-3 py-2.5">
                <span className={`h-2.5 w-2.5 flex-none rounded-full ${CAT_DOT[it.categoria] || "bg-stone-400"}`} />
                <div className="min-w-0 flex-1">
                  <p className="m-0 truncate text-sm font-bold text-stone-900">{it.gusto}</p>
                  <p className="m-0 text-xs text-stone-500">
                    {CAT_LABEL[it.categoria] || it.categoria} · calato il {it.data ? it.data.split("-").reverse().join("/") : "—"}
                  </p>
                </div>
                <span className="whitespace-nowrap text-sm font-black text-stone-800">{fmtG(it.quantita_g)}</span>
                {es === "rientrato" ? (
                  <div className="flex gap-1.5">
                    <button onClick={() => cambiaEsito(it.id, "riutilizzato")} className="rounded-lg bg-emerald-50 px-2.5 py-1 text-xs font-bold text-emerald-700 hover:bg-emerald-100">♻️ Riutilizza</button>
                    <button onClick={() => cambiaEsito(it.id, "dismesso")} className="rounded-lg bg-rose-50 px-2.5 py-1 text-xs font-bold text-rose-700 hover:bg-rose-100">🗑 Dismetti</button>
                  </div>
                ) : (
                  <button onClick={() => cambiaEsito(it.id, "rientrato")} title="Riporta in attesa"
                    className={`rounded-lg px-2.5 py-1 text-xs font-bold ${es === "riutilizzato" ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
                    {es === "riutilizzato" ? "♻️ Riutilizzato" : "🗑 Dismesso"} ↩︎
                  </button>
                )}
                <button onClick={() => elimina(it.id)} className="rounded-lg p-1.5 text-stone-300 hover:bg-red-50 hover:text-red-500"><Trash2 size={16} /></button>
              </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ───────────────────────── Produzioni ─────────────────────────
function ProduzioniTab() {
  const [list, setList] = useState([]);
  const [tot, setTot] = useState(0);
  const [loading, setLoading] = useState(true);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/gelati/produzioni`);
      setList(r.data?.produzioni || []);
      setTot(r.data?.peso_totale_g || 0);
    } catch (e) {
      setList([]);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    carica();
  }, [carica]);

  const elimina = async (id) => {
    try {
      await axios.delete(`${API}/gelati/produzioni/${id}`);
      carica();
    } catch (e) {}
  };

  return (
    <div className="rounded-3xl border border-stone-200 bg-white p-5 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="m-0 text-lg font-black text-stone-900">Produzioni registrate</h3>
        <button onClick={carica} className="rounded-lg p-1.5 text-stone-400 hover:bg-stone-100"><RefreshCw size={16} /></button>
      </div>
      <p className="m-0 mb-3 text-sm font-semibold text-stone-500">Totale prodotto: <b className="text-stone-900">{fmtG(tot)}</b></p>
      {loading ? (
        <p className="py-6 text-center text-sm text-stone-400">Caricamento…</p>
      ) : list.length === 0 ? (
        <p className="py-6 text-center text-sm text-stone-400">Nessuna produzione registrata. Calcola una ricetta e premi “Registra produzione”.</p>
      ) : (
        <div className="divide-y divide-stone-100">
          {list.map((p) => (
            <div key={p.id} className="flex items-center gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="m-0 truncate text-sm font-bold text-stone-900">{p.ricetta}</p>
                <p className="m-0 text-xs text-stone-500">{p.data ? p.data.split("-").reverse().join("/") : "—"} · {p.modalita}</p>
              </div>
              <span className="whitespace-nowrap text-sm font-black text-stone-800">{fmtG(p.peso_g)}</span>
              <button onClick={() => elimina(p.id)} className="rounded-lg p-1.5 text-stone-300 hover:bg-red-50 hover:text-red-500"><Trash2 size={16} /></button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ───────────────────────── Prodotti Galatea (in arrivo) ─────────────────────────
function ProdottiTab() {
  const cats = ["Basi (latte e frutta)", "Paste (pistacchio, nocciola, mandorla, arachide, noce)", "Variegati", "Salse", "Polveri aromatizzanti"];
  return (
    <div className="rounded-3xl border border-stone-200 bg-white p-5 shadow-sm">
      <h3 className="m-0 mb-2 text-lg font-black text-stone-900">Catalogo Galatea</h3>
      <p className="m-0 text-sm text-stone-500">
        Il catalogo completo dei prodotti Galatea (con allergeni e voci “senza lattosio”) verrà popolato dai prodotti realmente acquistati nelle fatture e dal sito. Categorie:
      </p>
      <ul className="mt-3 space-y-1.5 text-sm font-semibold text-stone-700">
        {cats.map((c) => (
          <li key={c} className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-[#5b7a6b]" /> {c}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ───────────────────────── Riepilogo / Report ─────────────────────────
function ReportTab() {
  const [periodo, setPeriodo] = useState("mese");
  const [rep, setRep] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filtro, setFiltro] = useState("");

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/gelati/report?periodo=${periodo}`);
      setRep(r.data);
    } catch (e) { setRep(null); } finally { setLoading(false); }
  }, [periodo]);
  useEffect(() => { carica(); }, [carica]);

  const righe = (rep?.righe || []).filter((r) => r.gusto.toLowerCase().includes(filtro.toLowerCase()));
  const t = rep?.totali || {};
  const dmy = (s) => (s ? s.split("-").reverse().join("/") : "—");

  return (
    <div className="space-y-4">
      <div className="rounded-3xl border border-stone-200 bg-white p-5 shadow-sm">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h3 className="m-0 text-lg font-black text-stone-900">Riepilogo invenduti e recuperi</h3>
          <button onClick={carica} className="rounded-lg p-1.5 text-stone-400 hover:bg-stone-100"><RefreshCw size={16} /></button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {[["settimana", "Settimana"], ["mese", "Mese"], ["anno", "Anno"]].map(([k, lab]) => (
            <button key={k} onClick={() => setPeriodo(k)}
              className={`rounded-xl px-4 py-2 text-sm font-bold transition ${periodo === k ? "bg-[#5b7a6b] text-white shadow" : "border border-stone-200 text-stone-500 hover:bg-stone-50"}`}>{lab}</button>
          ))}
          {rep && <span className="self-center text-xs text-stone-400">{dmy(rep.da)} → {dmy(rep.a)}</span>}
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <div className="rounded-2xl bg-stone-50 p-4"><p className="m-0 text-xs font-bold uppercase tracking-wide text-stone-400">Invenduto rientrato</p><p className="m-0 mt-1 text-2xl font-black text-stone-900">{fmtG(t.invenduto_g || 0)}</p></div>
          <div className="rounded-2xl bg-emerald-50 p-4"><p className="m-0 text-xs font-bold uppercase tracking-wide text-emerald-600">Riutilizzato (rinfuso)</p><p className="m-0 mt-1 text-2xl font-black text-emerald-700">{fmtG(t.riutilizzato_g || 0)}</p></div>
          <div className="rounded-2xl bg-rose-50 p-4"><p className="m-0 text-xs font-bold uppercase tracking-wide text-rose-500">Dismesso</p><p className="m-0 mt-1 text-2xl font-black text-rose-600">{fmtG(t.dismesso_g || 0)}</p></div>
        </div>
      </div>

      <div className="rounded-3xl border border-stone-200 bg-white p-5 shadow-sm">
        <input value={filtro} onChange={(e) => setFiltro(e.target.value)} placeholder="🔎 Filtra per gusto…" className={`${inputCls} mb-3`} />
        {loading ? (
          <p className="py-6 text-center text-sm text-stone-400">Caricamento…</p>
        ) : righe.length === 0 ? (
          <p className="py-6 text-center text-sm text-stone-400">Nessun invenduto nel periodo selezionato.</p>
        ) : (
          <div className="overflow-x-auto"><table className="w-full border-collapse text-sm">
            <thead>
              <tr className="bg-stone-100 text-stone-600">
                <th className="rounded-l-lg p-2.5 text-left font-bold">Gusto</th>
                <th className="p-2.5 text-right font-bold">Invenduto</th>
                <th className="p-2.5 text-right font-bold">Riutilizzato</th>
                <th className="p-2.5 text-right font-bold">Dismesso</th>
                <th className="rounded-r-lg p-2.5 text-right font-bold">In attesa</th>
              </tr>
            </thead>
            <tbody>
              {righe.map((r) => (
                <tr key={r.gusto} className="border-b border-stone-100">
                  <td className="p-2.5"><span className={`mr-2 inline-block h-2 w-2 rounded-full ${CAT_DOT[r.categoria] || "bg-stone-400"}`} /><span className="font-bold text-stone-800">{r.gusto}</span></td>
                  <td className="p-2.5 text-right font-semibold text-stone-700">{fmtG(r.invenduto_g)}</td>
                  <td className="p-2.5 text-right font-bold text-emerald-700">{fmtG(r.riutilizzato_g)}</td>
                  <td className="p-2.5 text-right text-rose-600">{fmtG(r.dismesso_g)}</td>
                  <td className="p-2.5 text-right text-stone-500">{fmtG(r.in_attesa_g)}</td>
                </tr>
              ))}
              <tr>
                <td className="border-t-2 border-stone-800 p-2.5 font-black">Totale</td>
                <td className="border-t-2 border-stone-800 p-2.5 text-right font-black text-stone-900">{fmtG(t.invenduto_g || 0)}</td>
                <td className="border-t-2 border-stone-800 p-2.5 text-right font-black text-emerald-700">{fmtG(t.riutilizzato_g || 0)}</td>
                <td className="border-t-2 border-stone-800 p-2.5 text-right font-black text-rose-600">{fmtG(t.dismesso_g || 0)}</td>
                <td className="border-t-2 border-stone-800 p-2.5 text-right font-black text-stone-500">{fmtG(t.in_attesa_g || 0)}</td>
              </tr>
            </tbody>
          </table></div>
        )}
      </div>
    </div>
  );
}

export default function GelatiView() {
  const [tab, setTab] = useState("calcolo");
  const [prodKey, setProdKey] = useState(0);
  return (
    <div className="space-y-5">
      {/* Titolo nell'intestazione uniforme di pagina */}
      <Tabs tab={tab} setTab={setTab} />
      {tab === "calcolo" && <CalcoloTab onProdotto={() => setProdKey((k) => k + 1)} />}
      {tab === "invenduti" && <InvendutiTab />}
      {tab === "produzioni" && <ProduzioniTab key={prodKey} />}
      {tab === "report" && <ReportTab />}
      {tab === "prodotti" && <ProdottiTab />}
    </div>
  );
}
