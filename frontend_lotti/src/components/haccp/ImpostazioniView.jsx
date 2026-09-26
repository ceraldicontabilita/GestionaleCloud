// Impostazioni: un solo punto d'ingresso per tutta la configurazione del
// titolare. Ogni sezione porta alla pagina che già la gestisce: qui non c'è
// una seconda copia di nessuna impostazione (una sola fonte per funzione).
import {
  Building2, Users, ShieldCheck, LayoutGrid, Refrigerator, Printer, Globe, Lock, DatabaseBackup,
  BookMarked, ClipboardCheck, FlaskConical, ChevronRight,
} from "lucide-react";

export const SEZIONI_IMPOSTAZIONI = [
  { id: "azienda", titolo: "Azienda", testo: "Ragione sociale, indirizzo, P.IVA e responsabile HACCP stampati sui registri.", icona: Building2, vai: "personale" },
  { id: "operatori", titolo: "Operatori e PIN", testo: "Chi lavora oggi, postazione e PIN (uno per persona, dalla scheda HR).", icona: Users, vai: "personale" },
  { id: "ruoli", titolo: "Ruoli e visibilità", testo: "Operatore, responsabile HACCP e caporeparto (col suo reparto): si scelgono qui, sulla scheda di ogni persona.", icona: ShieldCheck, vai: "personale" },
  { id: "reparti", titolo: "Reparti", testo: "Reparto di ogni ricetta e prodotti mostrati sui tablet.", icona: LayoutGrid, vai: "backoffice" },
  { id: "frigoriferi", titolo: "Frigoriferi e congelatori", testo: "Apparecchi censiti, nomi, responsabile del controllo, fuori servizio.", icona: Refrigerator, vai: "attrezzature" },
  { id: "stampanti", titolo: "Stampanti", testo: "Stampante per ogni tipo di documento e coda del print agent del negozio.", icona: Printer, vai: "stampanti" },
  { id: "cataloghi", titolo: "Cataloghi fornitori", testo: "Siti dei fornitori collegati ai prezzi e alle schede prodotto.", icona: Globe, vai: "cataloghi_esterni" },
  { id: "sicurezza", titolo: "Sicurezza e registri", testo: "Verifica dei dati e attendibilità dello storico HACCP senza firma.", icona: Lock, vai: "controllo_dati", altri: [{ label: "Attendibilità registri", vai: "attendibilita_haccp" }] },
  { id: "backup", titolo: "Backup", testo: "Backup verificati su Supabase, simulazione e ripristino.", icona: DatabaseBackup, vai: "backup" },
];

const ALTRE = [
  { titolo: "Dizionario ingredienti", icona: BookMarked, vai: "dizionario" },
  { titolo: "Configurazione guidata", icona: ClipboardCheck, vai: "configura" },
  { titolo: "Collaudi", icona: FlaskConical, vai: "collaudi" },
];

export default function ImpostazioniView({ onNavigate }) {
  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div className="border-b border-[#e6e0d4] pb-3">
        <p className="m-0 text-xs font-black uppercase text-[#8a6f47]">Amministrazione</p>
        <h1 className="m-0 mt-1 text-3xl font-extrabold tracking-tight text-[#2a3329]">Impostazioni</h1>
        <p className="m-0 mt-1 text-sm font-semibold text-[#6b7669]">Tutta la configurazione in un posto: ogni voce apre la pagina che la gestisce.</p>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {SEZIONI_IMPOSTAZIONI.map(({ id, titolo, testo, icona: Icona, vai, altri }) => (
          <div key={id} className="flex flex-col rounded-2xl border border-[#e6e0d4] bg-[#fffefb] p-4">
            <button
              type="button"
              onClick={() => onNavigate(vai)}
              data-testid={`impostazioni-${id}`}
              className="flex min-h-[44px] w-full items-start gap-3 text-left"
            >
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#eef3ef]">
                <Icona size={20} className="text-[#3f5a4e]" aria-hidden="true" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-base font-extrabold text-[#2a3329]">{titolo}</span>
                <span className="block text-sm text-[#6b7669]">{testo}</span>
              </span>
              <ChevronRight size={18} className="mt-1 shrink-0 text-[#8a8478]" aria-hidden="true" />
            </button>
            {altri?.map((a) => (
              <button key={a.vai} type="button" onClick={() => onNavigate(a.vai)}
                className="mt-2 min-h-[44px] rounded-xl border border-[#e6e0d4] px-3 text-left text-sm font-bold text-[#3f5a4e]">
                {a.label}
              </button>
            ))}
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        {ALTRE.map(({ titolo, icona: Icona, vai }) => (
          <button key={vai} type="button" onClick={() => onNavigate(vai)}
            className="inline-flex min-h-[44px] items-center gap-2 rounded-xl border border-[#e6e0d4] bg-[#fffefb] px-4 text-sm font-bold text-[#2a3329]">
            <Icona size={16} aria-hidden="true" /> {titolo}
          </button>
        ))}
      </div>
    </div>
  );
}
