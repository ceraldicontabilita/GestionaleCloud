import { CakeSlice, CookingPot } from "lucide-react";

export const GRUPPI_PRODUZIONE = [
  { id: "rosticceria_giorno", label: "Produzione del giorno · Rosticceria", breve: "Rosticceria del giorno", Icona: CookingPot },
  { id: "pasticceria_classica", label: "Pasticceria classica", breve: "Pasticceria classica", Icona: CakeSlice },
];

export function categorieConGruppo(correnti, categoria, attiva) {
  let categorie = Array.isArray(correnti) ? correnti : [];
  if (!attiva) return categorie.filter(c => c !== categoria);
  if (GRUPPI_PRODUZIONE.some(g => g.id === categoria)) {
    categorie = categorie.filter(c => !GRUPPI_PRODUZIONE.some(g => g.id === c) && (categoria !== "rosticceria_giorno" || c !== "colazioni"));
  }
  if (categoria === "colazioni") categorie = categorie.filter(c => c !== "rosticceria_giorno");
  return [...new Set([...categorie, categoria])];
}

export default function GruppiProduzioneRicette({ ricette, selezionato, onScegli, reparto }) {
  return <section aria-label="Gruppi di produzione" style={{marginBottom:16}}>
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(min(240px,100%),1fr))",gap:10}}>
      {GRUPPI_PRODUZIONE.filter(g => !reparto || g.id === (reparto === "rosticceria" ? "rosticceria_giorno" : "pasticceria_classica")).map(g => <button key={g.id} type="button" aria-pressed={selezionato === g.id}
        onClick={() => onScegli(selezionato === g.id ? "tutte" : g.id)}
        style={{display:"flex",alignItems:"center",gap:12,textAlign:"left",minHeight:76,padding:16,borderRadius:14,border:"1px solid var(--border,#e6e0d4)",background:selezionato === g.id ? "var(--primary,#5b7a6b)" : "var(--card,#fffefb)",color:selezionato === g.id ? "#fff" : "var(--text,#2a3329)",fontFamily:"inherit",cursor:"pointer"}}>
        <g.Icona size={24} aria-hidden="true" style={{flexShrink:0}} />
        <span style={{fontWeight:800,fontSize:14}}>{g.label}<span style={{display:"block",fontWeight:500,fontSize:12,marginTop:4}}>
          {ricette.filter(r => (r.categorie_rapide || []).includes(g.id)).length} ricette selezionate
        </span></span>
      </button>)}
    </div>
    <p style={{fontSize:12,color:"var(--text-2,#6f7569)",margin:"8px 0 0"}}>Le spunte restano fino a quando le cambi: seleziona cosa preparare. Il lotto viene registrato solo confermando la produzione.</p>
  </section>;
}
