import { useState } from "react";
import axios from "axios";
import { conferma } from "../../../utils/conferma";
import { preparaImportFotoRicette } from "./pianoImportFotoRicette";

const API = process.env.REACT_APP_LOTTI_BACKEND_URL + "/api";

export default function ImportaFotoRicette({ ricette, onCompletata }) {
  const [mappaFile, setMappaFile] = useState(null);
  const [immagini, setImmagini] = useState(null);
  const [piano, setPiano] = useState(null);
  const [errore, setErrore] = useState("");
  const [avanzamento, setAvanzamento] = useState(null);
  const [esito, setEsito] = useState(null);

  const analizza = async () => {
    setErrore("");
    setEsito(null);
    setPiano(null);
    if (!ricette.length) { setErrore("Le ricette operative non sono caricate"); return; }
    if (!mappaFile || !immagini?.length) {
      setErrore("Seleziona la mappa JSON e la cartella con i PNG");
      return;
    }
    try {
      const mappa = JSON.parse(await mappaFile.text());
      const risultato = preparaImportFotoRicette(mappa, immagini, ricette);
      setPiano(risultato);
    } catch (e) {
      setErrore(e.message || "Mappa immagini non leggibile");
    }
  };

  const importa = async () => {
    if (!piano?.piano.length || avanzamento) return;
    const ok = await conferma(
      `Migrare ${piano.piano.length} foto di ricette operative su Supabase Storage?\n\n` +
      `Le ${piano.giaCanoniche} foto già canoniche restano intatte. ` +
      `Le ricette eliminate e quelle con nome cambiato non vengono modificate. ` +
      "La foto precedente resta nel backup e il Menu viene sincronizzato."
    );
    if (!ok) return;
    const risultati = { riuscite: 0, giaPresenti: 0, saltate: [], errori: [], interrotto: false };
    setEsito(null);
    for (let i = 0; i < piano.piano.length; i++) {
      const voce = piano.piano[i];
      setAvanzamento({ corrente: i + 1, totale: piano.piano.length, nome: voce.nome });
      try {
        // Lo snapshot locale può essere vecchio: rileggi prima della scrittura.
        const corrente = (await axios.get(`${API}/ricette/${voce.id}`)).data;
        if (corrente.nome !== voce.nome) {
          risultati.saltate.push(`${voce.nome}: nome cambiato`);
          continue;
        }
        if (corrente.foto_storage_path) {
          risultati.giaPresenti += 1;
          continue;
        }
        const bytes = await voce.immagine.arrayBuffer();
        const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)))
          .map(x => x.toString(16).padStart(2, "0")).join("");
        const dati = new FormData();
        dati.append("file", voce.immagine, voce.file);
        dati.append("foto_source", "upload_manuale");
        dati.append("cestina_precedente", "false");
        const risposta = await axios.post(`${API}/ricette/${voce.id}/upload-foto`, dati, {
          headers: { "Content-Type": "multipart/form-data" },
          timeout: 120000,
        });
        if (risposta.data?.foto_sha256 !== digest) {
          risultati.errori.push(`${voce.nome}: hash restituito diverso dal PNG`);
        } else {
          risultati.riuscite += 1;
        }
      } catch (e) {
        const dettaglio = e?.response?.data?.detail;
        risultati.errori.push(`${voce.nome}: ${typeof dettaglio === "string" ? dettaglio : e.message}`);
        // Con sessione scaduta o servizio instabile, fermati. Un nuovo avvio
        // rilegge le ricette e salta quelle già migrate con successo.
        if ([401, 403, 502, 503, 504].includes(e?.response?.status) || !e?.response) {
          risultati.interrotto = true;
          break;
        }
      }
      setEsito({ ...risultati });
    }
    setAvanzamento(null);
    setEsito({ ...risultati });
    await onCompletata();
  };

  return (
    <details style={{ marginBottom: 16, padding: "10px 14px", border: "1px solid var(--border)", borderRadius: 10 }}>
      <summary style={{ cursor: "pointer", fontWeight: 700 }}>📷 Associa immagini alle ricette operative</summary>
      <p style={{ margin: "10px 0", color: "var(--text-2)", fontSize: 13 }}>
        Usa la mappa con ID ricetta e la cartella dei PNG estratti. Le immagini sono salvate
        nel percorso canonico del ricettario, non come link alla cartella Drive.
      </p>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "end" }}>
        <label>Mappa JSON<br />
          <input type="file" accept=".json,application/json" aria-label="Mappa immagini JSON"
            onChange={e => { setMappaFile(e.target.files?.[0] || null); setPiano(null); }} />
        </label>
        <label>Cartella PNG<br />
          <input type="file" accept="image/png" multiple webkitdirectory="" directory=""
            aria-label="Cartella immagini PNG"
            onChange={e => { setImmagini(e.target.files); setPiano(null); }} />
        </label>
        <button type="button" onClick={analizza} disabled={!!avanzamento}>Verifica abbinamenti</button>
      </div>
      {errore && <p role="alert" style={{ color: "#a12b20" }}>{errore}</p>}
      {piano && <div style={{ marginTop: 12, fontSize: 13 }}>
        <p>{piano.righe} righe nella mappa; {piano.piano.length} foto da importare; {piano.giaCanoniche} già
          su Supabase; {piano.eliminate} ricette non più operative; {piano.conflitti.length} nomi cambiati;
          {piano.mancanti.length} PNG mancanti.</p>
        {piano.conflitti.length > 0 &&
          <p>Da verificare a mano: {piano.conflitti.map(x => x.nomeAttuale).join(", ")}</p>}
        {piano.mancanti.length > 0 &&
          <p>File mancanti: {piano.mancanti.map(x => x.file).join(", ")}</p>}
        <button type="button" onClick={importa} disabled={!piano.piano.length || !!avanzamento}>
          {avanzamento ? `Importo ${avanzamento.corrente}/${avanzamento.totale}: ${avanzamento.nome}`
            : `Importa ${piano.piano.length} foto`}
        </button>
      </div>}
      {esito && <p role="status" style={{ fontSize: 13 }}>
        {esito.riuscite} importate, {esito.giaPresenti} già presenti, {esito.saltate.length} saltate,
        {" "}{esito.errori.length} errori.
        {esito.interrotto && " Importazione interrotta: aggiorna le ricette e riprendi senza duplicare."}
        {esito.errori.length > 0 && <span> Errori: {esito.errori.join("; ")}</span>}
      </p>}
    </details>
  );
}
