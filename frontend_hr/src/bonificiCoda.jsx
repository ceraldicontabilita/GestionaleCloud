// Coda «Bonifici da associare»: pezzi di presentazione senza stato, così si
// provano da soli (bonificiCoda.test.jsx). Nessun testo libero: si sceglie
// toccando un candidato (bottone da 44 px), mai scrivendo. Un candidato non si
// applica da solo: il tocco apre la conferma e solo quella scrive.
import React from "react";
import { AlertTriangle, UserCheck } from "lucide-react";

// Il motivo dell'avviso, a parole (le chiavi sono quelle di
// app/constants/stati_associazione_bonifico.py).
export const MOTIVI_AVVISO = {
  cognome_condiviso: "Cognome condiviso da più dipendenti: serve anche il nome proprio",
  stesso_importo_piu_buste: "Lo stesso importo compare in più buste",
  beneficiari_vari: "Bonifico cumulativo «beneficiari vari»: può pagare più dipendenti",
  nota_di_terzi: "La nota nomina una persona, ma la distinta può pagare più dipendenti",
};

export const eurDaCentesimi = (c) => (c === null || c === undefined ? null
  : (Number(c) / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));

// «03/2026» dal candidato; senza periodo il campo resta vuoto, mai inventato.
export const periodoCandidato = (c) => c?.periodo || (c?.mese && c?.anno ? `${String(c.mese).padStart(2, "0")}/${c.anno}` : null);

// CRO (TRN della ricevuta) e riferimento banca «MB…»: chi confronta il bonifico
// con l'estratto li copia da qui. tabular-nums e selezione intera al tocco.
export function CodaRiferimenti({ b }) {
  const voci = [["CRO", b?.cro], ["Rif. banca", b?.rif_banca || b?.rif_interno]].filter(([, v]) => v);
  if (!voci.length) return <span className="dc-muted">—</span>;
  return (
    <div className="dc-coda-rif">
      {voci.map(([etichetta, valore]) => (
        <div key={etichetta} className="dc-coda-rif-riga">
          <span className="dc-coda-rif-et">{etichetta}</span>
          <code className="dc-coda-rif-val" data-testid={`rif-${etichetta}`}>{valore}</code>
        </div>
      ))}
    </div>
  );
}

// Avviso calcolato dal backend (avviso_multi_dipendente + avviso_motivo): un
// distintivo con icona e testo, mai il solo colore.
export function AvvisoMultiDipendente({ b }) {
  if (!b?.avviso_multi_dipendente) return null;
  const motivo = MOTIVI_AVVISO[b.avviso_motivo] || "Il bonifico può riguardare più dipendenti";
  return (
    <div className="dc-coda-avviso" role="note" data-motivo={b.avviso_motivo || ""}>
      <AlertTriangle size={16} aria-hidden="true" />
      <span>{motivo}</span>
    </div>
  );
}

// «Scegli dipendente»: al massimo 10 candidati, uno per bottone. Il tocco non
// associa: chiama onScegli(candidato), che apre la conferma.
export function CandidatiBonifico({ candidati, onScegli, disabled = false }) {
  const lista = Array.isArray(candidati) ? candidati : [];
  if (!lista.length) {
    return <p className="dc-muted dc-coda-nessuno">Nessun candidato: scegli dal menu.</p>;
  }
  return (
    <div role="group" aria-label="Scegli dipendente" className="dc-coda-cand">
      <span className="dc-coda-cand-titolo">Scegli dipendente</span>
      <div className="dc-coda-cand-lista">
        {lista.map((c) => {
          const periodo = periodoCandidato(c);
          const residuo = eurDaCentesimi(c.importo_residuo_cents);
          return (
            <button key={`${c.dipendente_id}-${c.periodo || ""}`} type="button" className="dc-coda-chip"
              disabled={disabled} onClick={() => onScegli?.(c)}
              title={c.prova_testo || undefined}
              aria-label={`Scegli ${c.nome}${periodo ? `, busta ${periodo}` : ""}${residuo ? `, residuo € ${residuo}` : ""}`}>
              <UserCheck size={16} aria-hidden="true" />
              <span className="dc-coda-chip-testo">
                <span className="dc-coda-chip-nome">{c.nome}</span>
                <span className="dc-coda-chip-dett">
                  {periodo ? `Busta ${periodo}` : "Busta non trovata"}{residuo ? ` · residuo € ${residuo}` : ""}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
