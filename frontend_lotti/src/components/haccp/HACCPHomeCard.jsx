import {
  AlertTriangle, BookOpen, Bug, ClipboardCheck, Flame, ShieldCheck,
  Snowflake, Sparkles, Thermometer, Truck,
} from "lucide-react";

export default function HACCPHomeCard({ navigate }) {
  // Icone Lucide (mai emoji: su Android rendono con colori di sistema, spesso blu)
  const moduli = [
    [Snowflake, "#5b7a6b", "Temp. Negative", "Congelatori e surgelatori", "temp_negative", "cyan"],
    [Thermometer, "#c4894a", "Temp. Positive", "Frigoriferi e celle fresche", "temp_positive", "orange"],
    [Sparkles, "#5b7a6b", "Sanificazione", "Pulizie e controlli igiene", "sanificazione", "blue"],
    [Bug, "#3d8168", "Disinfestazione", "Monitoraggio infestanti", "disinfestazione", "green"],
    [AlertTriangle, "#c4894a", "Anomalie", "Non conformità e azioni", "anomalie", "amber"],
    [Flame, "#d35f4e", "Olio Frittura", "Controllo olio e cambi", "controllo_olio", "orange"],
    [Thermometer, "#d35f4e", "Temp. Cottura", "Cotture e sicurezza alimentare", "temp_cottura", "red"],
    [Truck, "#8a6f47", "Ricezione Merce", "Arrivi, controlli e fornitori", "ricezione_merce", "blue"],
    [ClipboardCheck, "#3d8168", "Registro HACCP", "Registro generale controlli", "registro_haccp", "green"],
    [BookOpen, "#3d8168", "Manuale HACCP", "Documentazione e procedure", "manuale", "green"],
  ];

  const tone = {
    green: "bg-emerald-50 border-emerald-200 hover:border-emerald-300",
    cyan: "bg-[#f2f6f3] border-[#cfdfd5] hover:border-[#b8d0c2]",
    orange: "bg-orange-50 border-orange-200 hover:border-orange-300",
    amber: "bg-amber-50 border-amber-200 hover:border-amber-300",
    red: "bg-red-50 border-red-200 hover:border-red-300",
    blue: "bg-amber-50 border-amber-200 hover:border-amber-300",
  };

  return (
    <section id="haccp-home-card" className="rounded-[32px] border border-emerald-200 bg-gradient-to-br from-emerald-50 via-stone-50 to-white p-5 shadow-sm">
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="grid h-14 w-14 place-items-center rounded-3xl border border-emerald-200 bg-white/80 shadow-sm"><ShieldCheck size={28} className="text-[#3d8168]" /></div>
          <div>
            <h2 className="m-0 text-2xl font-black text-stone-900">Conformità HACCP</h2>
            <p className="m-0 mt-1 text-sm font-semibold text-stone-500">Tutti i controlli alimentari in un’unica area, senza menu nascosti.</p>
          </div>
        </div>
        <span className="self-start rounded-full bg-white/80 px-3 py-1 text-xs font-black text-emerald-800 shadow-sm sm:self-auto">Centro controllo</span>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {moduli.map(([Icon, colore, title, subtitle, nav, t]) => (
          <button key={nav} onClick={() => navigate(nav)} className={`rounded-2xl border p-4 text-left shadow-sm transition hover:shadow-md active:scale-[.99] ${tone[t]}`}>
            <div className="flex items-start gap-3">
              <div className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl border border-white/70 bg-white/70 shadow-sm"><Icon size={22} color={colore} /></div>
              <div>
                <h4 className="m-0 text-sm font-black text-stone-900">{title}</h4>
                <p className="m-0 mt-1 text-xs font-semibold leading-snug text-stone-500">{subtitle}</p>
              </div>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}
