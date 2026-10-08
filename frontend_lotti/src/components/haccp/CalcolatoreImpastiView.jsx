import { useEffect, useState } from "react";
import axios from "axios";
import { API } from "../../utils/constants";
import { apiError } from "../../utils/apiError";
import { CampiLievitazione, condizioniComplete } from "./shared/PannelloLievito";

// Calcolatore impasti: tutte le formule stanno sul server
// (app/lotti/servizi/lievitazione.py), la pagina raccoglie i dati e mostra
// il risultato. Non salva nulla.

const SAGE = "#5b7a6b";
const SAGE_SCURO = "#3f5a4e";
const BORDO = "#e6e0d4";
const INCHIOSTRO = "#2a3329";
const SPENTO = "#6b6456";

const box = { background: "#fffefb", border: `1px solid ${BORDO}`, borderRadius: 12, padding: 14, marginBottom: 14 };
const titolo = { margin: "0 0 10px", fontSize: 16, color: SAGE_SCURO };
const griglia = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 10 };
const g = (v, cifre = 0) => (v === null || v === undefined ? "—"
  : Number(v).toLocaleString("it-IT", { maximumFractionDigits: cifre }));

function Numero({ id, etichetta, unita, valore, onChange, passo = "1" }) {
  return <label htmlFor={id} style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13, color: INCHIOSTRO, minWidth: 0 }}>
    {etichetta}
    <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <input id={id} type="number" inputMode="decimal" step={passo} value={valore} onChange={(e) => onChange(e.target.value)}
        style={{ width: "100%", minWidth: 0, minHeight: 44, fontSize: 17, fontWeight: 700, textAlign: "center",
          border: `1px solid ${BORDO}`, borderRadius: 10, background: "#fffefb" }} />
      {unita && <span style={{ color: SPENTO, whiteSpace: "nowrap" }}>{unita}</span>}
    </span>
  </label>;
}

function Riga({ nome, valore, forte }) {
  return <div style={{ display: "flex", justifyContent: "space-between", gap: 10, padding: "9px 0", borderTop: `1px solid #eee7dd` }}>
    <span>{nome}</span>
    <strong style={{ whiteSpace: "nowrap", fontSize: forte ? 20 : 16, color: forte ? SAGE_SCURO : INCHIOSTRO }}>{valore}</strong>
  </div>;
}

function Avvisi({ elenco }) {
  return (elenco || []).map((a) => <p key={a} role="status" style={{ margin: "8px 0 0", fontSize: 13, color: "#8a5a1f" }}>{a}</p>);
}

// Chiamata al server con attesa breve: ogni tasto non è una richiesta.
function useCalcolo(percorso, corpo, pronto) {
  const [esito, setEsito] = useState(null);
  const [errore, setErrore] = useState("");
  const chiave = JSON.stringify(corpo);
  useEffect(() => {
    if (!pronto) { setEsito(null); setErrore(""); return undefined; }
    let attivo = true;
    const timer = setTimeout(() => {
      axios.post(`${API}/food-cost/${percorso}`, corpo)
        .then(({ data }) => { if (attivo) { setEsito(data); setErrore(""); } })
        .catch((e) => { if (attivo) { setEsito(null); setErrore(apiError(e, "Calcolo non riuscito")); } });
    }, 300);
    return () => { attivo = false; clearTimeout(timer); };
  }, [percorso, chiave, pronto]); // eslint-disable-line react-hooks/exhaustive-deps
  return { esito, errore };
}

const pieno = (...v) => v.every((x) => x !== "" && x !== null && x !== undefined);

const TIPI_LIEVITO = [
  ["fresco", "Lievito di birra fresco"],
  ["secco_attivo", "Lievito secco attivo"],
  ["istantaneo", "Lievito secco istantaneo"],
];

const PREFERMENTI = {
  nessuno: { etichetta: "Impasto diretto" },
  // Biga classica: 44% d'acqua e 1% di lievito sulla sua farina.
  biga: { etichetta: "Biga", idratazione_pct: "44", lievito_pct: "1" },
  // Poolish: stessa acqua e farina; il lievito dipende dalle ore, lo decide chi impasta.
  poolish: { etichetta: "Poolish", idratazione_pct: "100", lievito_pct: "" },
};

export default function CalcolatoreImpastiView() {
  const [impasto, setImpasto] = useState({ panetti: "", peso_panetto_g: "", idratazione_pct: "", sale_g_litro: "", grassi_g_litro: "" });
  const [tipoLievito, setTipoLievito] = useState("fresco");
  const [lievitazione, setLievitazione] = useState({ ore_ambiente: "", temperatura_c: "", ore_frigo: "", temperatura_frigo_c: "" });
  const [pref, setPref] = useState({ tipo: "nessuno", quota_farina_pct: "", idratazione_pct: "", lievito_pct: "" });
  const setI = (k) => (v) => setImpasto({ ...impasto, [k]: v });
  const setP = (k) => (v) => setPref({ ...pref, [k]: v });

  const cond = condizioniComplete(lievitazione);
  const conPref = pref.tipo !== "nessuno";
  const prontoImpasto = pieno(impasto.panetti, impasto.peso_panetto_g, impasto.idratazione_pct, impasto.sale_g_litro)
    && !!cond && (!conPref || pieno(pref.quota_farina_pct, pref.idratazione_pct, pref.lievito_pct));
  const { esito, errore } = useCalcolo("calcolatore-impasto", {
    ...impasto, tipo_lievito: tipoLievito, ...(cond || {}),
    ...(conPref ? { prefermento: pref } : {}),
  }, prontoImpasto);

  const [mix, setMix] = useState({ w_a: "", w_b: "", w_voluto: "" });
  const farinaMix = esito?.farina_g ?? "";
  const calcMix = useCalcolo("calcolatore-impasto/mix-farine", { ...mix, farina_totale_g: farinaMix },
    pieno(mix.w_a, mix.w_b, mix.w_voluto, farinaMix));

  const [temp, setTemp] = useState({ tfi: "", t_ambiente: "", t_farina: "", attrito: "", t_prefermento: "" });
  const calcAcqua = useCalcolo("calcolatore-impasto/temperatura-acqua", {
    tfi: temp.tfi, t_ambiente: temp.t_ambiente, t_farina: temp.t_farina, attrito: temp.attrito,
    t_prefermento: conPref ? temp.t_prefermento : null,
  }, pieno(temp.tfi, temp.t_ambiente, temp.t_farina, temp.attrito) && (!conPref || pieno(temp.t_prefermento)));

  const [prova, setProva] = useState({ tfi_misurata: "", t_ambiente: "", t_farina: "", t_acqua: "" });
  const calcAttrito = useCalcolo("calcolatore-impasto/temperatura-acqua", prova,
    pieno(prova.tfi_misurata, prova.t_ambiente, prova.t_farina, prova.t_acqua));

  const nomeLievito = TIPI_LIEVITO.find(([k]) => k === tipoLievito)[1];

  return <div style={{ maxWidth: 880, color: INCHIOSTRO }}>
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 14, alignItems: "start" }}>
      <div>
        <section style={box} aria-labelledby="t-impasto">
          <h3 id="t-impasto" style={titolo}>Impasto</h3>
          <div style={griglia}>
            <Numero id="ci-panetti" etichetta="Panetti" valore={impasto.panetti} onChange={setI("panetti")} />
            <Numero id="ci-peso" etichetta="Peso del panetto" unita="g" valore={impasto.peso_panetto_g} onChange={setI("peso_panetto_g")} />
            <Numero id="ci-idro" etichetta="Idratazione" unita="%" valore={impasto.idratazione_pct} onChange={setI("idratazione_pct")} />
            <Numero id="ci-sale" etichetta="Sale per litro d'acqua" unita="g/l" valore={impasto.sale_g_litro} onChange={setI("sale_g_litro")} />
            <Numero id="ci-grassi" etichetta="Olio o strutto per litro" unita="g/l" valore={impasto.grassi_g_litro} onChange={setI("grassi_g_litro")} />
            <label htmlFor="ci-tipo" style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
              Lievito
              <select id="ci-tipo" value={tipoLievito} onChange={(e) => setTipoLievito(e.target.value)}
                style={{ minHeight: 44, border: `1px solid ${BORDO}`, borderRadius: 10, background: "#fffefb", fontSize: 15, padding: "0 8px" }}>
                {TIPI_LIEVITO.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </label>
          </div>
        </section>

        <section style={box} aria-labelledby="t-lievitazione">
          <h3 id="t-lievitazione" style={titolo}>Lievitazione</h3>
          <CampiLievitazione prefisso="ci-lievitazione" valori={lievitazione} setValori={setLievitazione} />
        </section>

        <section style={box} aria-labelledby="t-pref">
          <h3 id="t-pref" style={titolo}>Prefermento</h3>
          <div role="radiogroup" aria-label="Tipo di impasto" style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: conPref ? 12 : 0 }}>
            {Object.entries(PREFERMENTI).map(([k, v]) => <button key={k} type="button" role="radio" aria-checked={pref.tipo === k}
              onClick={() => setPref({ tipo: k, quota_farina_pct: pref.quota_farina_pct,
                idratazione_pct: v.idratazione_pct ?? "", lievito_pct: v.lievito_pct ?? "" })}
              style={{ minHeight: 44, padding: "0 14px", borderRadius: 10, cursor: "pointer", fontWeight: 700,
                border: `1px solid ${pref.tipo === k ? SAGE : BORDO}`, background: pref.tipo === k ? SAGE : "#fffefb",
                color: pref.tipo === k ? "#fff" : INCHIOSTRO }}>{v.etichetta}</button>)}
          </div>
          {conPref && <div style={griglia}>
            <Numero id="ci-quota" etichetta="Farina nel prefermento" unita="%" valore={pref.quota_farina_pct} onChange={setP("quota_farina_pct")} />
            <Numero id="ci-pidro" etichetta="Sua idratazione" unita="%" valore={pref.idratazione_pct} onChange={setP("idratazione_pct")} />
            <Numero id="ci-plievito" etichetta="Suo lievito sulla farina" unita="%" passo="0.05" valore={pref.lievito_pct} onChange={setP("lievito_pct")} />
          </div>}
        </section>
      </div>

      <div>
        <section style={{ ...box, borderColor: SAGE }} aria-labelledby="t-ricetta" aria-live="polite">
          <h3 id="t-ricetta" style={titolo}>Ricetta</h3>
          {!prontoImpasto && <p style={{ margin: 0, color: SPENTO, fontSize: 14 }}>
            Compila panetti, peso, idratazione, sale e lievitazione: la ricetta compare qui.
          </p>}
          {errore && <p role="alert" style={{ margin: 0, color: "#8f3829" }}>{errore}</p>}
          {esito && <>
            {esito.prefermento && <>
              <h4 style={{ margin: "4px 0 2px", fontSize: 14 }}>{PREFERMENTI[esito.prefermento.tipo].etichetta}</h4>
              <Riga nome="Farina" valore={`${g(esito.prefermento.farina_g)} g`} />
              <Riga nome="Acqua" valore={`${g(esito.prefermento.acqua_g)} g`} />
              <Riga nome="Lievito di birra fresco" valore={`${g(esito.prefermento.lievito_g, 2)} g`} />
              <h4 style={{ margin: "14px 0 2px", fontSize: 14 }}>Chiusura</h4>
              <Riga nome="Farina" valore={`${g(esito.chiusura.farina_g)} g`} />
              <Riga nome="Acqua" valore={`${g(esito.chiusura.acqua_g)} g`} />
              <Riga nome="Sale" valore={`${g(esito.chiusura.sale_g, 1)} g`} />
              {esito.chiusura.grassi_g > 0 && <Riga nome="Olio o strutto" valore={`${g(esito.chiusura.grassi_g, 1)} g`} />}
              <p style={{ margin: "10px 0 0", fontSize: 13, color: SPENTO }}>
                Il lievito lo porta il prefermento: in chiusura se ne aggiunge solo se serve, a giudizio di chi impasta.
              </p>
            </>}
            {!esito.prefermento && <>
              <Riga nome="Farina" valore={`${g(esito.farina_g)} g`} />
              <Riga nome="Acqua" valore={`${g(esito.acqua_g)} g`} />
              <Riga nome="Sale" valore={`${g(esito.sale_g, 1)} g`} />
              {esito.grassi_g > 0 && <Riga nome="Olio o strutto" valore={`${g(esito.grassi_g, 1)} g`} />}
            </>}
            {!esito.prefermento && <Riga nome={nomeLievito} valore={`${g(esito.lievito.grammi, 2)} g`} forte />}
            <p style={{ margin: "8px 0 0", fontSize: 13, color: SPENTO }}>
              Totale {g(esito.totale_g)} g · {g(esito.ore_equivalenti, 1)} ore equivalenti a temperatura ambiente
            </p>
            <Avvisi elenco={esito.avvisi} />
          </>}
        </section>

        <section style={box} aria-labelledby="t-mix">
          <h3 id="t-mix" style={titolo}>Mix di due farine</h3>
          <div style={griglia}>
            <Numero id="ci-wa" etichetta="W prima farina" valore={mix.w_a} onChange={(v) => setMix({ ...mix, w_a: v })} passo="10" />
            <Numero id="ci-wb" etichetta="W seconda farina" valore={mix.w_b} onChange={(v) => setMix({ ...mix, w_b: v })} passo="10" />
            <Numero id="ci-wv" etichetta="W che ti serve" valore={mix.w_voluto} onChange={(v) => setMix({ ...mix, w_voluto: v })} passo="10" />
          </div>
          {!farinaMix && <p style={{ margin: "10px 0 0", fontSize: 13, color: SPENTO }}>Si divide la farina della ricetta: compila prima l'impasto.</p>}
          {calcMix.errore && <p role="alert" style={{ margin: "10px 0 0", color: "#8f3829" }}>{calcMix.errore}</p>}
          {calcMix.esito && <div style={{ marginTop: 6 }}>
            <Riga nome={`Farina W ${mix.w_a}`} valore={`${g(calcMix.esito.farina_a_g)} g`} />
            <Riga nome={`Farina W ${mix.w_b}`} valore={`${g(calcMix.esito.farina_b_g)} g`} />
          </div>}
        </section>

        <section style={box} aria-labelledby="t-acqua">
          <h3 id="t-acqua" style={titolo}>Temperatura dell'acqua</h3>
          <div style={griglia}>
            <Numero id="ci-tfi" etichetta="Fine impasto voluta" unita="°C" valore={temp.tfi} onChange={(v) => setTemp({ ...temp, tfi: v })} />
            <Numero id="ci-tamb" etichetta="Laboratorio" unita="°C" valore={temp.t_ambiente} onChange={(v) => setTemp({ ...temp, t_ambiente: v })} />
            <Numero id="ci-tfar" etichetta="Farina" unita="°C" valore={temp.t_farina} onChange={(v) => setTemp({ ...temp, t_farina: v })} />
            <Numero id="ci-att" etichetta="Attrito impastatrice" unita="°C" valore={temp.attrito} onChange={(v) => setTemp({ ...temp, attrito: v })} />
            {conPref && <Numero id="ci-tpref" etichetta="Prefermento" unita="°C" valore={temp.t_prefermento} onChange={(v) => setTemp({ ...temp, t_prefermento: v })} />}
          </div>
          {calcAcqua.errore && <p role="alert" style={{ margin: "10px 0 0", color: "#8f3829" }}>{calcAcqua.errore}</p>}
          {calcAcqua.esito && <><Riga nome="Acqua da usare" valore={`${g(calcAcqua.esito.acqua_c, 1)} °C`} forte />
            <Avvisi elenco={calcAcqua.esito.avvisi} /></>}

          <details style={{ marginTop: 12 }}>
            <summary style={{ cursor: "pointer", minHeight: 44, display: "flex", alignItems: "center", color: SAGE_SCURO, fontWeight: 700 }}>
              Non conosci l'attrito? Ricavalo da un impasto già fatto
            </summary>
            <div style={griglia}>
              <Numero id="ci-p-tfi" etichetta="Misurata a fine impasto" unita="°C" valore={prova.tfi_misurata} onChange={(v) => setProva({ ...prova, tfi_misurata: v })} />
              <Numero id="ci-p-amb" etichetta="Laboratorio" unita="°C" valore={prova.t_ambiente} onChange={(v) => setProva({ ...prova, t_ambiente: v })} />
              <Numero id="ci-p-far" etichetta="Farina" unita="°C" valore={prova.t_farina} onChange={(v) => setProva({ ...prova, t_farina: v })} />
              <Numero id="ci-p-acq" etichetta="Acqua usata" unita="°C" valore={prova.t_acqua} onChange={(v) => setProva({ ...prova, t_acqua: v })} />
            </div>
            {calcAttrito.errore && <p role="alert" style={{ margin: "10px 0 0", color: "#8f3829" }}>{calcAttrito.errore}</p>}
            {calcAttrito.esito && <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <div style={{ flex: 1 }}><Riga nome="Attrito della tua impastatrice" valore={`${g(calcAttrito.esito.attrito_c, 1)} °C`} /></div>
              <button type="button" onClick={() => setTemp({ ...temp, attrito: String(calcAttrito.esito.attrito_c) })}
                style={{ minHeight: 44, padding: "0 14px", borderRadius: 10, border: 0, background: SAGE, color: "#fff", fontWeight: 800, cursor: "pointer" }}>
                Usa questo attrito
              </button>
            </div>}
          </details>
        </section>
      </div>
    </div>

    <p style={{ fontSize: 12, color: SPENTO, maxWidth: 70 * 8 }}>
      Lievito: formula «Japi 2» della comunità La Verace, tarata fra 15 e 35 °C, 1 e 96 ore, idratazione 50–100%.
      Ore in frigo convertite con la regola di Hamelman (fermentazione tre volte più veloce ogni 9 °C).
      Secco attivo = fresco × 0,4, istantaneo = fresco ÷ 3. Sono stime: la lievitazione si controlla sempre a vista.
    </p>
  </div>;
}
