// Magazzino vero (audit 27/09/2026). Due verità che il magazzino non diceva:
//  1. merce comprata da mesi e mai scaricata da una produzione, che risultava
//     ancora disponibile: qui si vede per mese e la chiude solo il titolare,
//     con simulazione prima e possibilità di annullare (niente si cancella);
//  2. ricette senza dosi: produrle non scala il magazzino e il costo resta
//     da verificare. Qui l'elenco per reparto, da completare.
import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { PackageX, ClipboardList, RotateCcw } from "lucide-react";
import { API } from "../../utils/constants";
import { apiError } from "../../utils/apiError";
import { conferma } from "../../utils/conferma";

const MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
  "settembre", "ottobre", "novembre", "dicembre"];
const REPARTI = ["", "pasticceria", "rosticceria", "bar", "altro"];

export function sogliaGiorni(giorni, oggi = new Date()) {
  const d = new Date(oggi.getFullYear(), oggi.getMonth(), oggi.getDate() - giorni);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

const dataIt = (iso) => (iso ? iso.split("-").reverse().join("/") : "");
const nomeMese = (chiave) => {
  const [a, m] = String(chiave).split("-");
  return `${MESI[Number(m) - 1] || m} ${a}`;
};
const euro = (v) => Number(v || 0).toLocaleString("it-IT", { style: "currency", currency: "EUR" });

const chip = (attivo) =>
  `min-h-[44px] rounded-xl border px-4 text-sm font-bold ${attivo ? "border-[#3f5a4e] bg-[#5b7a6b] text-white" : "border-[#e6e0d4] bg-[#fffefb] text-[#2a3329]"}`;

function MerceFerma() {
  const [giorni, setGiorni] = useState(60);
  const [dati, setDati] = useState(null);
  const [errore, setErrore] = useState("");
  const [lavoro, setLavoro] = useState(false);
  const [ultimaChiusura, setUltimaChiusura] = useState(null);
  const primaDel = useMemo(() => sogliaGiorni(giorni), [giorni]);

  const carica = useCallback(async () => {
    setErrore("");
    try {
      const r = await axios.get(`${API}/lotti-fornitori/merce-ferma`, { params: { prima_del: primaDel } });
      setDati(r.data);
    } catch (e) {
      setDati(null);
      setErrore(apiError(e, "Merce ferma non disponibile"));
    }
  }, [primaDel]);

  useEffect(() => { carica(); }, [carica]);

  const chiudi = async () => {
    if (!dati?.righe) return;
    const ok = await conferma(
      `Chiudo come consumate ${dati.righe} righe di merce comprata prima del ${dataIt(primaDel)} e mai scaricata. Non si cancella niente e puoi annullare.`,
      { titolo: "Chiudere la merce ferma?", ok: `Sì, chiudi ${dati.righe} righe`, pericolo: true },
    );
    if (!ok) return;
    setLavoro(true);
    try {
      const r = await axios.post(`${API}/lotti-fornitori/merce-ferma/chiudi`, {
        prima_del: primaDel, dry_run: false, conferma: "CHIUDI MERCE FERMA",
      });
      setUltimaChiusura(r.data.chiuso_il);
      toast.success(`${r.data.chiusi} righe chiuse`);
      await carica();
    } catch (e) {
      toast.error(apiError(e, "Chiusura non riuscita"));
    } finally {
      setLavoro(false);
    }
  };

  const annulla = async () => {
    setLavoro(true);
    try {
      const r = await axios.post(`${API}/lotti-fornitori/merce-ferma/riapri`, null, { params: { chiuso_il: ultimaChiusura } });
      toast.success(`${r.data.riaperti} righe tornate disponibili`);
      setUltimaChiusura(null);
      await carica();
    } catch (e) {
      toast.error(apiError(e, "Annullamento non riuscito"));
    } finally {
      setLavoro(false);
    }
  };

  return (
    <section className="rounded-2xl border border-[#e6e0d4] bg-[#fffefb] p-4">
      <h2 className="m-0 flex items-center gap-2 text-lg font-extrabold text-[#2a3329]">
        <PackageX size={20} className="text-[#c4894a]" aria-hidden="true" /> Merce ferma
      </h2>
      <p className="m-0 mt-1 text-sm text-[#6b7669]">
        Materie prime comprate e mai scaricate da una produzione: il magazzino le conta ancora come disponibili.
      </p>
      <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Ferma da">
        {[30, 60, 90].map((g) => (
          <button key={g} type="button" className={chip(giorni === g)} aria-pressed={giorni === g} onClick={() => setGiorni(g)}>
            più di {g} giorni
          </button>
        ))}
      </div>
      {errore && <p role="alert" className="mt-3 text-sm font-bold text-[#d35f4e]">{errore}</p>}
      {dati && (
        <>
          <p className="mt-3 text-sm text-[#2a3329]">
            <strong>{dati.righe}</strong> righe comprate prima del {dataIt(dati.prima_del)}
            {dati.righe > 0 && <> · valore {euro(dati.valore)}{dati.senza_prezzo ? ` (${dati.senza_prezzo} senza prezzo in fattura, fuori dal totale)` : ""}</>}
          </p>
          <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {dati.mesi.map((m) => (
              <div key={m.mese} className="rounded-xl border border-[#e6e0d4] p-3">
                <div className="font-bold capitalize text-[#2a3329]">{nomeMese(m.mese)} · {m.righe} righe · {euro(m.valore)}</div>
                <ul className="m-0 mt-1 list-none p-0 text-xs text-[#6b7669]">
                  {m.esempi.map((e, i) => (
                    <li key={i}>{e.prodotto} — {e.fornitore} · {e.quantita} {e.unita} · fattura {e.data_fattura}</li>
                  ))}
                  {m.righe > m.esempi.length && <li>… e altre {m.righe - m.esempi.length}</li>}
                </ul>
              </div>
            ))}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" disabled={lavoro || !dati.righe} onClick={chiudi}
              className="min-h-[48px] rounded-xl bg-[#c4894a] px-5 text-sm font-extrabold text-white disabled:opacity-50">
              Chiudi come consumate ({dati.righe})
            </button>
            {ultimaChiusura && (
              <button type="button" disabled={lavoro} onClick={annulla}
                className="inline-flex min-h-[48px] items-center gap-2 rounded-xl border border-[#e6e0d4] bg-[#fffefb] px-5 text-sm font-bold text-[#2a3329]">
                <RotateCcw size={16} aria-hidden="true" /> Annulla l'ultima chiusura
              </button>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function RicetteDaCompletare() {
  const [reparto, setReparto] = useState("");
  const [dati, setDati] = useState(null);
  const [errore, setErrore] = useState("");

  useEffect(() => {
    let attivo = true;
    setErrore("");
    axios.get(`${API}/ricette-da-completare`, { params: reparto ? { reparto } : {} })
      .then((r) => { if (attivo) setDati(r.data); })
      .catch((e) => { if (attivo) { setDati(null); setErrore(apiError(e, "Elenco non disponibile")); } });
    return () => { attivo = false; };
  }, [reparto]);

  return (
    <section className="rounded-2xl border border-[#e6e0d4] bg-[#fffefb] p-4">
      <h2 className="m-0 flex items-center gap-2 text-lg font-extrabold text-[#2a3329]">
        <ClipboardList size={20} className="text-[#5b7a6b]" aria-hidden="true" /> Ricette senza dosi
      </h2>
      <p className="m-0 mt-1 text-sm text-[#6b7669]">
        Finché mancano le dosi, produrle non scala il magazzino e il costo del lotto resta da verificare.
        Le completa il caporeparto del reparto o il titolare.
      </p>
      <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Reparto">
        {REPARTI.map((r) => (
          <button key={r || "tutti"} type="button" className={chip(reparto === r)} aria-pressed={reparto === r} onClick={() => setReparto(r)}>
            {r ? r[0].toUpperCase() + r.slice(1) : "Tutti"}
          </button>
        ))}
      </div>
      {errore && <p role="alert" className="mt-3 text-sm font-bold text-[#d35f4e]">{errore}</p>}
      {dati && (
        <>
          <p className="mt-3 text-sm text-[#2a3329]"><strong>{dati.da_completare}</strong> da completare su {dati.totale_ricette}</p>
          <ul className="m-0 mt-2 list-none space-y-2 p-0">
            {dati.ricette.map((r) => (
              <li key={r.id} className="rounded-xl border border-[#e6e0d4] p-3">
                <div className="font-bold text-[#2a3329]">{r.nome} <span className="text-xs font-semibold text-[#8a6f47]">{r.reparto}</span></div>
                <div className="text-xs text-[#6b7669]">
                  {r.ingredienti === 0 ? "Nessun ingrediente inserito"
                    : `Senza dose (${r.senza_dose.length} su ${r.ingredienti}): ${r.senza_dose.join(", ")}`}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

export default function MerceFermaView() {
  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <MerceFerma />
      <RicetteDaCompletare />
    </div>
  );
}
