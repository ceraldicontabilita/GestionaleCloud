/**
 * SceltaMotivo — menù a tendina con i motivi già pronti, al posto dei campi
 * di testo liberi. REGOLA PERMANENTE (Enzo 04/07/2026): il pasticcere ha le
 * mani sporche — deve agire su automazioni, MAI usare la tastiera. La
 * tastiera compare SOLO se sceglie «Altro (scrivi tu)».
 * Riusato da: RicezioneMerceView (azione correttiva), SchedaLottoModal
 * (sposta/congela/recupera/smaltisci). Per nuovi flussi: aggiungere la lista
 * qui, non creare textarea libere.
 */
import { useState } from "react";

export const MOTIVI = {
  ricezione_non_conforme: [
    "Temperatura fuori range — merce respinta al fornitore",
    "Temperatura fuori range — accettata con riserva, avvisato il fornitore",
    "Imballaggio danneggiato (rotture, gonfiamenti, perdite)",
    "Etichettatura non conforme / data illeggibile",
    "Prodotto troppo vicino a scadenza",
    "Quantità non corrispondente al documento",
    "Merce respinta al fornitore — richiesta sostituzione",
  ],
  smaltimento: [
    "Lotto scaduto — smaltito nei rifiuti organici",
    "Aspetto/odore non conforme — smaltito per sicurezza",
    "Catena del freddo interrotta — smaltito",
    "Invenduto non recuperabile — smaltito",
    "Danneggiato durante la manipolazione — smaltito",
  ],
  sposta: [
    "Riorganizzazione del frigo",
    "Frigo in manutenzione / anomalia",
    "Spazio esaurito nella posizione attuale",
    "Avvicinato al banco per l'uso di oggi",
  ],
  congela: [
    "Non si usa oggi — congelato per conservarlo",
    "Produzione in eccesso",
    "Chiusura imminente (festivo / riposo)",
  ],
  recupera: [
    "Riutilizzo in nuova produzione",
    "Base per farcitura / crema",
    "Dolce del giorno dopo",
  ],
  olio_fuori_norma: [
    "Olio sostituito completamente, friggitrice pulita",
    "Olio sostituito, filtro pulito",
    "Rabboccato con olio nuovo e programmata sostituzione domani",
    "Temperatura abbassata sotto 175 °C",
    "Friggitrice fermata in attesa di manutenzione",
  ],
  cottura_sotto_soglia: [
    "Prolungata la cottura fino a temperatura raggiunta",
    "Prodotto rimesso in forno e ricontrollato",
    "Prodotto abbattuto subito (soglia 70 °C rispettata)",
    "Prodotto scartato per sicurezza",
  ],
};

const ALTRO = "__altro__";

export function SceltaMotivo({ opzioni, value, onChange, etichetta, obbligatoria = false, tono = "neutro" }) {
  // se il valore attuale non è tra le opzioni, siamo in modalità "Altro"
  const [altro, setAltro] = useState(() => !!value && !opzioni.includes(value));
  const bordo = tono === "danger" ? "#fecaca" : "#e6e0d4";

  return (
    <div>
      {etichetta && (
        <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 4 }}>
          {etichetta}{obbligatoria ? " *" : ""}
        </div>
      )}
      <select
        value={altro ? ALTRO : (value || "")}
        onChange={(e) => {
          if (e.target.value === ALTRO) { setAltro(true); onChange(""); }
          else { setAltro(false); onChange(e.target.value); }
        }}
        style={{
          width: "100%", padding: "12px", borderRadius: 12, fontSize: 14, fontWeight: 600,
          border: `1.5px solid ${bordo}`, background: "#fff", minHeight: 46,
        }}
      >
        <option value="">— Scegli il motivo —</option>
        {opzioni.map((o) => <option key={o} value={o}>{o}</option>)}
        <option value={ALTRO}>✍️ Altro (scrivi tu)</option>
      </select>
      {altro && (
        <input
          autoFocus
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Scrivi il motivo…"
          style={{
            width: "100%", marginTop: 6, padding: "11px 12px", borderRadius: 12,
            fontSize: 14, border: `1.5px solid ${bordo}`, background: "#fff",
          }}
        />
      )}
    </div>
  );
}
