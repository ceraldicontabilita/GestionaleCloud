import { useCallback, useEffect, useMemo, useState } from "react";
import { conferma } from "../../utils/conferma";
import axios from "axios";
import { toast } from "sonner";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Edit2,
  FileText,
  Plus,
  Printer,
  RefreshCw,
  Thermometer,
  X,
} from "lucide-react";
import Button from "../ui/Button";
import { API, MESI_IT } from "../../utils/constants";
import SegnalaGuasto from "./shared/SegnalaGuasto";
import { giorniNelMese } from "../../utils/dateUtils";
import { printHtml } from "../../utils/printHtml";
import { apiError } from "../../utils/apiError";

const AZIENDA_INFO = {
  nome: "Ceraldi Group S.R.L.",
  indirizzo: "Piazza Carità 14, 80134 Napoli (NA)",
};

const RIFERIMENTI_NORMATIVI = {
  principale: "Reg. CE 852/2004",
  secondario: "D.Lgs. 193/2007",
};

const OPERATORI_TEMPERATURE = ["Pocci Salvatore", "Vincenzo Ceraldi"];
const NUM_FRIGO_DEFAULT = 12;

const ColonnaFrigo = ({ numero, nome, onRinomina, onElimina }) => {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(nome);

  useEffect(() => setVal(nome), [nome]);

  const salva = async () => {
    const n = val.trim();
    if (!n || n === nome) {
      setEditing(false);
      return;
    }
    try {
      await axios.put(`${API}/attrezzature/frigo/${numero}/rinomina`, null, { params: { nome: n } });
      onRinomina(numero, n);
      toast.success(`Rinominato in "${n}"`);
    } catch {
      toast.error("Errore rinomina frigorifero");
    }
    setEditing(false);
  };

  const elimina = async () => {
    if (!await conferma(`Eliminare "${nome}" dalla lista?`)) return;
    try {
      await axios.delete(`${API}/attrezzature/frigo/${numero}`);
      onElimina(numero);
      toast.success(`"${nome}" rimosso`);
    } catch {
      toast.error("Errore eliminazione frigorifero");
    }
  };

  if (editing) {
    return (
      <div className="flex flex-col items-center gap-1 px-1">
        <input
          autoFocus
          value={val}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") salva();
            if (e.key === "Escape") setEditing(false);
          }}
          className="w-20 rounded border-2 border-orange-400 px-1 py-0.5 text-center text-[11px] outline-none"
        />
        <div className="flex gap-1">
          <button onClick={salva} className="text-green-600 hover:text-green-800"><Check size={12} /></button>
          <button onClick={elimina} className="text-red-500 hover:text-red-700"><X size={12} /></button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col items-center gap-1">
      <button
        type="button"
        className="group flex w-full flex-col items-center gap-1"
        onClick={() => setEditing(true)}
        title={`Clicca per rinominare o eliminare ${nome}`}
      >
        <span className="w-20 break-words text-center text-[10px] leading-tight text-gray-600">{nome}</span>
        <Edit2 size={10} className="text-gray-300 transition-colors group-hover:text-orange-500" />
      </button>
      {/* un tocco: apre l'anomalia sull'apparecchio e porta allo spostamento lotti */}
      <SegnalaGuasto attrezzatura={nome} categoria="Frigorifero" />
    </div>
  );
};

const AggiungiFrigoPanel = ({ onAdded }) => {
  const [show, setShow] = useState(false);
  const [nome, setNome] = useState("");

  const aggiungi = async () => {
    const n = nome.trim() || "Nuovo Frigorifero";
    try {
      await axios.post(`${API}/attrezzature/frigo`, { nome: n });
      toast.success(`"${n}" aggiunto`);
      setNome("");
      setShow(false);
      onAdded?.();
    } catch (e) {
      toast.error(apiError(e, "Errore aggiunta frigorifero"));
    }
  };

  if (!show) {
    return (
      <button
        onClick={() => setShow(true)}
        className="flex items-center gap-1.5 rounded-lg border border-orange-200 bg-orange-50 px-3 py-1.5 text-sm text-orange-700 transition-colors hover:bg-orange-100"
      >
        <Plus size={14} /> Aggiungi Frigorifero
      </button>
    );
  }

  return (
    <div className="flex min-w-[280px] items-center gap-2 rounded-lg border border-orange-200 bg-orange-50 p-2">
      <input
        autoFocus
        value={nome}
        onChange={(e) => setNome(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") aggiungi();
          if (e.key === "Escape") setShow(false);
        }}
        placeholder="Nome frigorifero"
        className="min-w-0 flex-1 rounded-lg border border-orange-300 px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-orange-400"
      />
      <button onClick={aggiungi} className="rounded-lg bg-orange-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-orange-600">Aggiungi</button>
      <button onClick={() => setShow(false)} className="text-gray-400 hover:text-gray-600"><X size={14} /></button>
    </div>
  );
};

// Cella temperatura: click -> input -> salva. Risolve il fatto che le celle erano di sola lettura.
function CellaTemperatura({ display, tempValue, disabled, onSave }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState("");
  const orig = tempValue === null || tempValue === undefined ? "" : String(tempValue);
  const commit = () => {
    setEditing(false);
    const v = val.replace(",", ".").trim();
    if (v !== "" && v !== orig) onSave(v);
  };
  if (editing) {
    return (
      <input
        type="number"
        step="0.1"
        autoFocus
        value={val}
        onChange={(e) => setVal(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") commit(); else if (e.key === "Escape") setEditing(false); }}
        onBlur={commit}
        className="h-6 w-full rounded border border-orange-400 bg-white text-center text-xs text-gray-900 outline-none"
      />
    );
  }
  return (
    <div
      onClick={() => { if (!disabled) { setVal(orig); setEditing(true); } }}
      className={`flex h-6 w-full items-center justify-center rounded text-xs ${disabled ? "" : "cursor-pointer hover:ring-2 hover:ring-orange-300"} ${display.className}`}
      title={disabled ? display.title : "Tocca per inserire / modificare la temperatura"}
    >
      {display.value}
    </div>
  );
}


// ── Modale azione correttiva (frigo fuori range) ───────────────────────────
function ModalAzioneCorrettiva({ dati, onSalva, onChiudi }) {
  const [scelta, setScelta] = useState("");
  const [libero, setLibero] = useState("");
  const AZIONI = [
    "Merce spostata in altro frigo funzionante",
    "Chiamato tecnico di manutenzione",
    "Regolato/abbassato il termostato",
    "Prodotti deperibili eliminati",
    "Verificata chiusura porta / guarnizione",
  ];
  const azioneFinale = libero.trim() || scelta;
  return (
    <div onClick={onChiudi}
      style={{ position: "fixed", inset: 0, background: "rgba(31,27,46,.45)", display: "grid", placeItems: "center", zIndex: 9999, padding: 16 }}>
      <div onClick={(e) => e.stopPropagation()}
        style={{ width: "min(440px,95vw)", background: "#fffefb", borderRadius: 18, padding: 22, boxShadow: "0 20px 60px rgba(0,0,0,.3)", border: "1px solid #e6e0d4" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
          <span style={{ fontSize: 26 }}>⚠️</span>
          <h3 style={{ margin: 0, fontSize: 18, fontWeight: 800, color: "#d35f4e" }}>Frigo fuori range: {dati.temperatura}°C</h3>
        </div>
        <p style={{ margin: "0 0 14px", fontSize: 13, color: "#6b6456", lineHeight: 1.4 }}>
          La legge (Reg. 852/2004) richiede di documentare <b>cosa è stato fatto</b>. Seleziona o scrivi l'azione correttiva.
        </p>
        <div style={{ display: "grid", gap: 8, marginBottom: 12 }}>
          {AZIONI.map((a) => (
            <button key={a} onClick={() => { setScelta(a); setLibero(""); }}
              style={{ textAlign: "left", padding: "10px 12px", borderRadius: 10, cursor: "pointer",
                border: `1.5px solid ${scelta === a ? "#5b7a6b" : "#e6e0d4"}`,
                background: scelta === a ? "#5b7a6b14" : "#fff", fontWeight: 600, fontSize: 14, color: "#1f2937" }}>
              {a}
            </button>
          ))}
        </div>
        <textarea value={libero} onChange={(e) => { setLibero(e.target.value); setScelta(""); }}
          placeholder="…oppure descrivi un'altra azione" rows={2}
          style={{ width: "100%", boxSizing: "border-box", padding: "10px 12px", borderRadius: 10, border: "1px solid #e6e0d4", fontSize: 14, resize: "vertical", marginBottom: 14 }} />
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button onClick={onChiudi}
            style={{ padding: "10px 16px", borderRadius: 10, border: "1px solid #e6e0d4", background: "#fff", fontWeight: 700, cursor: "pointer", color: "#6b6456" }}>
            Più tardi
          </button>
          <button onClick={() => azioneFinale && onSalva(azioneFinale)} disabled={!azioneFinale}
            style={{ padding: "10px 18px", borderRadius: 10, border: "none", background: azioneFinale ? "#5b7a6b" : "#cfc8ba", color: "#fff", fontWeight: 800, cursor: azioneFinale ? "pointer" : "not-allowed" }}>
            Registra azione
          </button>
        </div>
      </div>
    </div>
  );
}

export default function TemperaturePositiveView() {
  const [mese, setMese] = useState(new Date().getMonth() + 1);
  const [azioneModal, setAzioneModal] = useState(null); // {frigoNum, giorno, temperatura} — frigo fuori range
  const [anno, setAnno] = useState(new Date().getFullYear());
  const [schedeFrigoriferi, setSchedeFrigoriferi] = useState({});
  const [chiusure, setChiusure] = useState({});
  const [loading, setLoading] = useState(true);
  const [nomiFrigo, setNomiFrigo] = useState({});
  const [errore, setErrore] = useState("");

  const numGiorni = giorniNelMese(mese, anno);

  const numeriFrigo = useMemo(() => {
    const nums = new Set(Array.from({ length: NUM_FRIGO_DEFAULT }, (_, i) => i + 1));
    Object.keys(nomiFrigo).forEach((n) => nums.add(Number(n)));
    Object.keys(schedeFrigoriferi).forEach((n) => nums.add(Number(n)));
    return Array.from(nums).filter(Boolean).sort((a, b) => a - b);
  }, [nomiFrigo, schedeFrigoriferi]);

  const fetchNomiFrigo = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/attrezzature/`, { params: { anno }, timeout: 30000 });
      const map = {};
      (r.data?.frigoriferi || []).forEach((f) => { map[f.numero] = f.nome; });
      setNomiFrigo(map);
    } catch {
      setNomiFrigo({});
    }
  }, [anno]);

  const fetchSchede = useCallback(async () => {
    setLoading(true);
    setErrore("");
    try {
      const [schedeRes, chiusureRes] = await Promise.allSettled([
        axios.get(`${API}/temperature-positive/schede/${anno}`, { timeout: 90000 }),
        axios.get(`${API}/chiusure/anno/${anno}`, { timeout: 30000 }),
      ]);

      if (schedeRes.status !== "fulfilled") throw schedeRes.reason;

      const schede = {};
      (schedeRes.value.data || []).forEach((scheda) => {
        const numero = Number(scheda.frigorifero_numero);
        if (numero) schede[numero] = scheda;
      });
      setSchedeFrigoriferi(schede);

      if (chiusureRes.status === "fulfilled") setChiusure(chiusureRes.value.data || {});
      else setChiusure({});
    } catch (err) {
      console.error("Errore temperature positive", err);
      setErrore(apiError(err, "Errore caricamento temperature positive"));
      toast.error("Errore caricamento temperature positive");
    } finally {
      setLoading(false);
    }
  }, [anno]);

  useEffect(() => {
    fetchSchede();
    fetchNomiFrigo();
  }, [fetchSchede, fetchNomiFrigo]);

  const cambiaMese = (delta) => {
    let nuovoMese = mese + delta;
    let nuovoAnno = anno;
    if (nuovoMese < 1) { nuovoMese = 12; nuovoAnno -= 1; }
    if (nuovoMese > 12) { nuovoMese = 1; nuovoAnno += 1; }
    setMese(nuovoMese);
    setAnno(nuovoAnno);
  };

  const isGiornoChiuso = (giorno) => {
    if (!chiusure?.chiusure) return false;
    return chiusure.chiusure.some((c) => {
      const parts = c.data_formattata?.split("/");
      if (!parts) return false;
      return parseInt(parts[0], 10) === giorno && parseInt(parts[1], 10) === mese;
    });
  };

  const getNomeFrigo = (numero) => nomiFrigo[numero] || schedeFrigoriferi[numero]?.frigorifero_nome || `Frigorifero N°${numero}`;
  const handleRinominaFrigo = (numero, nuovoNome) => setNomiFrigo((prev) => ({ ...prev, [numero]: nuovoNome }));
  const handleEliminaFrigo = (numero) => {
    setNomiFrigo((prev) => {
      const next = { ...prev };
      delete next[numero];
      return next;
    });
    fetchNomiFrigo();
  };

  const getTemperatura = (frigoNum, giorno) => {
    const scheda = schedeFrigoriferi[frigoNum];
    if (!scheda) return null;
    const t = scheda.temperature || {};
    // Tollerante al formato chiave (mese/giorno): "5", "05", 5 — i dati storici
    // possono avere chiavi diverse da quelle attuali.
    const mkeys = [String(mese), String(mese).padStart(2, "0"), mese];
    const gkeys = [String(giorno), String(giorno).padStart(2, "0"), giorno];
    for (const mk of mkeys) {
      const mm = t[mk];
      if (mm) {
        for (const gk of gkeys) {
          if (mm[gk] != null && mm[gk] !== "") return mm[gk];
        }
      }
    }
    return null;
  };

  const salvaTemperatura = async (frigoNum, giorno, tempRaw) => {
    const temperatura = Number(String(tempRaw).replace(",", ".").trim());
    if (Number.isNaN(temperatura)) { toast.error("Valore temperatura non valido"); return; }
    try {
      const res = await axios.post(
        `${API}/temperature-positive/scheda/${anno}/${frigoNum}/registra`,
        null,
        { params: { mese, giorno, temperatura }, timeout: 30000 },
      );
      if (res.data?.serve_azione_correttiva) {
        // frigo fuori range: chiedi SUBITO cosa e' stato fatto (obbligo ASL)
        setAzioneModal({ frigoNum, giorno, temperatura });
      } else {
        toast.success(`${getNomeFrigo(frigoNum)} · ${giorno}/${mese}: ${temperatura}°C`);
      }
      fetchSchede();
    } catch (err) {
      toast.error(apiError(err, "Errore salvataggio temperatura"));
    }
  };

  const salvaAzioneCorrettiva = async (azione) => {
    if (!azioneModal) return;
    const { frigoNum, giorno, temperatura } = azioneModal;
    try {
      await axios.post(
        `${API}/temperature-positive/scheda/${anno}/${frigoNum}/registra`,
        null,
        { params: { mese, giorno, temperatura, azione_correttiva: azione }, timeout: 30000 },
      );
      toast.success("Azione correttiva registrata");
      setAzioneModal(null);
      fetchSchede();
    } catch (err) {
      toast.error(apiError(err, "Errore salvataggio azione"));
    }
  };

  const getCellDisplay = (frigoNum, giorno) => {
    if (isGiornoChiuso(giorno)) return { value: "🚫", className: "bg-gray-400 text-white", title: "CHIUSO" };

    const record = getTemperatura(frigoNum, giorno);
    const scheda = schedeFrigoriferi[frigoNum];
    if (!record) return { value: "-", className: "bg-gray-50 text-gray-400", title: "Nessun dato" };

    if (typeof record === "object") {
      if (record.is_chiuso || record.tipo === "chiusura") return { value: "🚫", className: "bg-gray-400 text-white", title: "CHIUSO" };
      if (record.is_manutenzione || record.tipo === "manutenzione") return { value: "🔧", className: "bg-yellow-200 text-yellow-800", title: "MANUTENZIONE" };
      if (record.is_non_usato) return { value: "⏸", className: "bg-gray-200 text-gray-600", title: "NON USATO" };
      if (record.temp !== undefined && record.temp !== null) {
        const temp = Number(record.temp);
        const fuoriRange = temp > (scheda?.temp_max ?? 4) || temp < (scheda?.temp_min ?? 0);
        return {
          value: `${temp}°`,
          className: fuoriRange ? "bg-red-100 text-red-700 font-bold" : "bg-orange-50 text-orange-800",
          title: fuoriRange ? `⚠ ${temp}°C — fuori range` : `${temp}°C`,
        };
      }
    }

    const temp = Number(record);
    if (!Number.isNaN(temp)) {
      const fuoriRange = temp > 4 || temp < 0;
      return {
        value: `${temp}°`,
        className: fuoriRange ? "bg-red-100 text-red-700 font-bold" : "bg-orange-50 text-orange-800",
        title: fuoriRange ? `⚠ ${temp}°C — fuori range` : `${temp}°C`,
      };
    }

    return { value: "-", className: "bg-gray-50 text-gray-400", title: "Nessun dato" };
  };

  const stampaScheda = () => {
    let righe = "";
    for (let g = 1; g <= numGiorni; g += 1) {
      righe += `<tr><td style="padding:4px;border:1px solid #ccc;font-weight:bold;">${g}</td>`;
      numeriFrigo.forEach((f) => {
        const cell = getCellDisplay(f, g);
        const style = cell.className.includes("red") ? "background:#fee;color:#c00;" :
          cell.className.includes("gray-400") ? "background:#999;color:#fff;" :
          cell.className.includes("yellow") ? "background:#fff3bf;" :
          cell.className.includes("orange") ? "background:#fff7ed;" : "";
        righe += `<td style="padding:4px;border:1px solid #ccc;text-align:center;${style}">${cell.value}</td>`;
      });
      righe += "</tr>";
    }

    printHtml(`<!DOCTYPE html><html><head><title>Temperature Frigoriferi - ${MESI_IT[mese - 1]} ${anno}</title><style>body{font-family:Arial;font-size:10pt;margin:15mm}h1{font-size:14pt}table{border-collapse:collapse;width:100%}th{background:#eee;padding:4px;border:1px solid #ccc}.footer{margin-top:20px;font-size:9pt;color:#555}</style></head><body><h1>SCHEDA TEMPERATURE FRIGORIFERI</h1><p><strong>${AZIENDA_INFO.nome}</strong> - ${AZIENDA_INFO.indirizzo}</p><p><strong>Mese:</strong> ${MESI_IT[mese - 1]} ${anno} | <strong>Range:</strong> 0°C / +4°C</p><table><thead><tr><th>G</th>${numeriFrigo.map((n) => `<th>F${n}</th>`).join("")}</tr></thead><tbody>${righe}</tbody></table><div class="footer"><p><strong>Operatori:</strong> ${OPERATORI_TEMPERATURE.join(", ")}</p><p><strong>Rif:</strong> ${RIFERIMENTI_NORMATIVI.principale} - ${RIFERIMENTI_NORMATIVI.secondario}</p><p><strong>Legenda:</strong> Chiuso | Manutenzione | Non usato</p></div></body></html>`);
  };

  if (loading) {
    return (
      <div className="py-12 text-center text-gray-500">
        <RefreshCw className="mx-auto mb-3 animate-spin text-orange-600" />
        Caricamento temperature positive…
        <div className="mx-auto mt-2 max-w-xs text-xs text-gray-400">
          Al primo accesso dopo una pausa il server può impiegare fino a un minuto a riattivarsi.
        </div>
      </div>
    );
  }

  return (
    <>
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-bold">
            <Thermometer className="text-orange-600" /> Temperature Frigoriferi
          </h2>
          <p className="text-sm text-gray-500">{AZIENDA_INFO.nome} • Range: 0°C / +4°C</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => cambiaMese(-1)} className="rounded p-2 hover:bg-gray-100"><ChevronLeft size={20} /></button>
          <span className="min-w-[150px] text-center font-semibold">{MESI_IT[mese - 1]} {anno}</span>
          <button onClick={() => cambiaMese(1)} className="rounded p-2 hover:bg-gray-100"><ChevronRight size={20} /></button>
          <button
            onClick={async () => {
              try {
                await axios.post(`${API}/haccp-periodi/applica-tutti`, null, { timeout: 90000 });
                toast.success("Periodi speciali applicati");
                fetchSchede();
              } catch {
                toast.error("Errore applicazione periodi");
              }
            }}
            className="rounded border border-yellow-300 bg-yellow-100 px-3 py-1.5 text-xs font-semibold text-yellow-800 hover:bg-yellow-200"
          >
            🔧 Periodi
          </button>
          <Button onClick={stampaScheda} variant="secondary" size="sm"><Printer size={16} /> Stampa</Button>
          <Button onClick={fetchSchede} variant="secondary" size="sm"><RefreshCw size={16} /> Ricarica</Button>
        </div>
      </div>

      {errore ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <strong>Modulo non caricato:</strong> {errore}
          <button onClick={fetchSchede} className="ml-3 rounded bg-red-600 px-3 py-1 text-xs font-bold text-white">Riprova</button>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-orange-200 bg-orange-50 p-3">
          <h4 className="flex items-center gap-1 text-sm font-semibold text-orange-800"><FileText size={14} /> Riferimenti Normativi</h4>
          <p className="mt-1 text-xs text-orange-700">{RIFERIMENTI_NORMATIVI.principale} • {RIFERIMENTI_NORMATIVI.secondario}</p>
        </div>
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
          <h4 className="text-sm font-semibold text-amber-800">👷 Operatori</h4>
          <p className="mt-1 text-xs text-amber-700">{OPERATORI_TEMPERATURE.join(", ")}</p>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border bg-white">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-orange-100 bg-orange-50 px-3 py-2">
          <span className="text-xs font-medium text-orange-700">Clicca sull'intestazione colonna per rinominare o eliminare un frigorifero</span>
          <AggiungiFrigoPanel onAdded={() => { fetchNomiFrigo(); fetchSchede(); }} />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="sticky left-0 min-w-[50px] bg-gray-50 px-2 py-2 text-left font-medium text-gray-700">G</th>
                {numeriFrigo.map((numero) => (
                  <th key={numero} className="min-w-[72px] px-1 py-2 text-center font-medium text-gray-600">
                    <ColonnaFrigo numero={numero} nome={getNomeFrigo(numero)} onRinomina={handleRinominaFrigo} onElimina={handleEliminaFrigo} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y">
              {Array.from({ length: numGiorni }, (_, giornoIdx) => {
                const giorno = giornoIdx + 1;
                const chiuso = isGiornoChiuso(giorno);
                return (
                  <tr key={giorno} className={`hover:bg-gray-50 ${chiuso ? "bg-gray-100" : ""}`}>
                    <td className={`sticky left-0 px-2 py-1 font-medium text-gray-800 ${chiuso ? "bg-gray-100" : "bg-white"}`}>{giorno}</td>
                    {numeriFrigo.map((frigoNum) => {
                      const cell = getCellDisplay(frigoNum, giorno);
                      const rec = getTemperatura(frigoNum, giorno);
                      const tempValue = (rec && typeof rec === "object" && rec.temp !== undefined && rec.temp !== null) ? rec.temp : null;
                      return (
                        <td key={frigoNum} className="px-1 py-1 text-center">
                          <CellaTemperatura
                            display={cell}
                            tempValue={tempValue}
                            disabled={chiuso}
                            onSave={(v) => salvaTemperatura(frigoNum, giorno, v)}
                          />
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-4 rounded-lg bg-gray-50 p-3 text-xs text-gray-600">
        <span className="flex items-center gap-1"><span className="h-4 w-4 rounded border bg-orange-50" /> Temp OK</span>
        <span className="flex items-center gap-1"><span className="h-4 w-4 rounded border bg-red-100" /> Fuori range</span>
        <span className="flex items-center gap-1"><span className="h-4 w-4 rounded border bg-gray-400" /> Chiuso</span>
        <span className="flex items-center gap-1"><span className="h-4 w-4 rounded border bg-yellow-200" /> Manutenzione</span>
        <span className="flex items-center gap-1"><span className="h-4 w-4 rounded border bg-gray-200" /> Non usato</span>
      </div>
    </div>
      {azioneModal && (
        <ModalAzioneCorrettiva
          dati={azioneModal}
          onSalva={salvaAzioneCorrettiva}
          onChiudi={() => setAzioneModal(null)}
        />
      )}
    </>
  );
}