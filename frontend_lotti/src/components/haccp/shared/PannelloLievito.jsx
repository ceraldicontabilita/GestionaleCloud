import { useEffect, useState } from "react";
import axios from "axios";
import { API } from "../../../utils/constants";
import { apiError } from "../../../utils/apiError";

// Lievitazione di OGGI per una ricetta che contiene lievito di birra.
// Unico pannello per scheda ricetta e produzione da tablet: il calcolo sta
// sul server (servizi/lievitazione.py), qui si raccolgono ore e temperature.
// onCambia(condizioni | null) passa al chiamante le condizioni complete.

const CAMPI_VUOTI = { ore_ambiente: "", temperatura_c: "", ore_frigo: "", temperatura_frigo_c: "" };

export function condizioniComplete(c) {
  const n = (v) => v !== "" && v !== null && v !== undefined && Number.isFinite(Number(v));
  if (!n(c.ore_ambiente) || !n(c.temperatura_c)) return null;
  const frigo = n(c.ore_frigo) && Number(c.ore_frigo) > 0;
  if (frigo && !n(c.temperatura_frigo_c)) return null;
  return {
    ore_ambiente: Number(c.ore_ambiente),
    temperatura_c: Number(c.temperatura_c),
    ...(frigo ? { ore_frigo: Number(c.ore_frigo), temperatura_frigo_c: Number(c.temperatura_frigo_c) } : {}),
  };
}

// I valori salvati possono avere null (niente frigo): i campi vogliono "".
const inCampi = (c) => Object.fromEntries(Object.keys(CAMPI_VUOTI)
  .map((k) => [k, c?.[k] === null || c?.[k] === undefined || c?.[k] === 0 && k.includes("frigo") ? "" : String(c[k])]));

const numero = (v) => (v === null || v === undefined ? "—" : Number(v).toLocaleString("it-IT", { maximumFractionDigits: 2 }));

function Campo({ id, etichetta, unita, valore, onChange }) {
  return <label htmlFor={id} style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13, color: "#2a3329", minWidth: 0 }}>
    {etichetta}
    <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <input id={id} type="number" inputMode="decimal" step="0.5" value={valore}
        onChange={(e) => onChange(e.target.value)}
        style={{ width: "100%", minWidth: 0, minHeight: 44, fontSize: 17, fontWeight: 700, textAlign: "center",
          border: "1px solid #e6e0d4", borderRadius: 10, background: "#fffefb" }} />
      <span style={{ color: "#6b6456", whiteSpace: "nowrap" }}>{unita}</span>
    </span>
  </label>;
}

export function CampiLievitazione({ prefisso, valori, setValori }) {
  const set = (k) => (v) => setValori({ ...valori, [k]: v });
  const conFrigo = Number(valori.ore_frigo) > 0;
  return <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 10 }}>
    <Campo id={`${prefisso}-ore`} etichetta="Ore a temperatura ambiente" unita="ore" valore={valori.ore_ambiente} onChange={set("ore_ambiente")} />
    <Campo id={`${prefisso}-temp`} etichetta="Temperatura del laboratorio" unita="°C" valore={valori.temperatura_c} onChange={set("temperatura_c")} />
    <Campo id={`${prefisso}-frigo`} etichetta="Ore in frigo (se ci va)" unita="ore" valore={valori.ore_frigo} onChange={set("ore_frigo")} />
    {conFrigo && <Campo id={`${prefisso}-tfrigo`} etichetta="Temperatura del frigo" unita="°C" valore={valori.temperatura_frigo_c} onChange={set("temperatura_frigo_c")} />}
  </div>;
}

export default function PannelloLievito({ ricetta, pezzi, onCambia, mostraDosi = true }) {
  const [oggi, setOggi] = useState(CAMPI_VUOTI);
  const [esito, setEsito] = useState(null);
  const [errore, setErrore] = useState("");
  const [riferimento, setRiferimento] = useState(ricetta?.lievitazione_riferimento || null);
  const [modificaRif, setModificaRif] = useState(false);
  const [bozzaRif, setBozzaRif] = useState(CAMPI_VUOTI);
  const [salvando, setSalvando] = useState(false);
  const [erroreRif, setErroreRif] = useState("");
  const [versioneRif, setVersioneRif] = useState(0);

  useEffect(() => {
    setOggi(CAMPI_VUOTI);
    setRiferimento(ricetta?.lievitazione_riferimento || null);
    setModificaRif(false);
    setEsito(null);
  }, [ricetta?.id, JSON.stringify(ricetta?.lievitazione_riferimento || null)]); // eslint-disable-line react-hooks/exhaustive-deps

  const complete = condizioniComplete(oggi);
  const chiave = JSON.stringify(complete);

  // Si notifica solo quando cambiano davvero le condizioni (chiave), non a ogni render.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { onCambia?.(complete); }, [chiave]);

  useEffect(() => {
    if (!ricetta?.id) return undefined;
    let attivo = true;
    const timer = setTimeout(() => {
      axios.post(`${API}/food-cost/ricetta/${ricetta.id}/lievito`, { pezzi: pezzi || null, lievitazione: complete })
        .then(({ data }) => { if (attivo) { setEsito(data); setErrore(""); } })
        .catch((e) => { if (attivo) setErrore(apiError(e, "Lievito non calcolabile")); });
    }, 250);
    return () => { attivo = false; clearTimeout(timer); };
  }, [ricetta?.id, pezzi, chiave, versioneRif]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!esito || esito.stato === "senza_lievito") return null;
  // Il riferimento vero è quello che il server ha usato: la ricetta passata
  // dal tablet può non portarlo con sé.
  const rif = riferimento || esito.riferimento || null;

  const salvaRiferimento = async () => {
    const valido = condizioniComplete(bozzaRif);
    if (!valido) { setErroreRif("Scrivi almeno ore e temperatura."); return; }
    setSalvando(true);
    try {
      await axios.patch(`${API}/ricette/${ricetta.id}`, { lievitazione_riferimento: valido });
      setRiferimento(valido);
      setVersioneRif((n) => n + 1);
      setModificaRif(false);
      setErroreRif("");
    } catch (e) {
      setErroreRif(e?.response?.status === 403
        ? "Solo chi gestisce le ricette può salvarlo: chiedi al caporeparto."
        : apiError(e, "Riferimento non salvato"));
    } finally {
      setSalvando(false);
    }
  };

  const descriviRif = (r) => `${numero(r.ore_ambiente)} ore a ${numero(r.temperatura_c)} °C`
    + (r.ore_frigo ? ` più ${numero(r.ore_frigo)} ore in frigo a ${numero(r.temperatura_frigo_c)} °C` : "");

  return <section aria-label="Lievito di oggi" style={{ background: "#fffefb", border: "1px solid #e6e0d4", borderRadius: 12, padding: 12, marginBottom: 12 }}>
    <h4 style={{ margin: "0 0 4px", fontSize: 15, color: "#3f5a4e" }}>Lievito di oggi</h4>

    {rif && !modificaRif ? <p style={{ margin: "0 0 10px", fontSize: 13, color: "#6b6456" }}>
      La dose della ricetta vale per {descriviRif(rif)}.{" "}
      <button type="button" onClick={() => { setBozzaRif(inCampi(rif)); setModificaRif(true); }}
        style={{ background: "none", border: 0, padding: 0, color: "#3f5a4e", textDecoration: "underline", cursor: "pointer", fontSize: 13 }}>
        Cambia
      </button>
    </p> : <div style={{ background: "#f7f1e6", border: "1px solid #e6e0d4", borderRadius: 10, padding: 10, margin: "0 0 12px" }}>
      <p style={{ margin: "0 0 8px", fontSize: 13 }}>
        {rif ? "Per quale lievitazione vale il lievito scritto in ricetta?"
          : "La ricetta non dice per quale lievitazione vale la sua dose di lievito, quindi non posso adeguarla. Indicala una volta sola:"}
      </p>
      <CampiLievitazione prefisso={`rif-${ricetta.id}`} valori={bozzaRif} setValori={setBozzaRif} />
      <div style={{ display: "flex", gap: 10, marginTop: 10, flexWrap: "wrap", alignItems: "center" }}>
        <button type="button" onClick={salvaRiferimento} disabled={salvando}
          style={{ minHeight: 44, padding: "0 16px", borderRadius: 10, border: 0, background: "#5b7a6b", color: "#fff", fontWeight: 800, cursor: "pointer" }}>
          {salvando ? "Salvataggio…" : "Salva nella ricetta"}
        </button>
        {rif && <button type="button" onClick={() => setModificaRif(false)}
          style={{ minHeight: 44, padding: "0 14px", borderRadius: 10, border: "1px solid #e6e0d4", background: "#fffefb", cursor: "pointer" }}>Annulla</button>}
        {erroreRif && <span role="alert" style={{ color: "#8f3829", fontSize: 13 }}>{erroreRif}</span>}
      </div>
    </div>}

    {rif && <>
      <p style={{ margin: "0 0 8px", fontSize: 13 }}>Come lieviterà oggi?</p>
      <CampiLievitazione prefisso={`oggi-${ricetta.id}`} valori={oggi} setValori={setOggi} />
    </>}

    {errore && <p role="alert" style={{ color: "#8f3829", margin: "10px 0 0", fontSize: 13 }}>{errore}</p>}

    {mostraDosi && esito.stato === "ricalcolato" && <div style={{ marginTop: 12 }}>
      {esito.righe.map((r, i) => <div key={`${r.nome}-${i}`} style={{ display: "flex", justifyContent: "space-between", gap: 10, padding: "8px 0", borderTop: "1px solid #eee7dd" }}>
        <span>{r.nome}<br /><span style={{ fontSize: 12, color: "#6b6456" }}>in ricetta {numero(r.ricetta)} {r.unita}</span></span>
        <strong style={{ fontSize: 20, color: "#3f5a4e", whiteSpace: "nowrap" }}>{numero(r.oggi)} {r.unita}</strong>
      </div>)}
    </div>}
    {!mostraDosi && esito.stato === "ricalcolato" && <p style={{ margin: "10px 0 0", fontSize: 13, color: "#3f5a4e" }}>
      Lievito × {numero(esito.fattore)} rispetto alla ricetta: la dose qui sotto è già quella di oggi.
    </p>}
    {(esito.avvisi || []).map((a) => <p key={a} role="status" style={{ margin: "8px 0 0", fontSize: 13, color: "#8a5a1f" }}>{a}</p>)}
  </section>;
}
