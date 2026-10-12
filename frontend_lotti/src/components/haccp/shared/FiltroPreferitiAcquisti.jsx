export default function FiltroPreferitiAcquisti({ attivo, onChange, dati }) {
  return <div className="space-y-2">
    <div className="flex flex-wrap items-center gap-2">
      <button type="button" aria-pressed={attivo} onClick={() => { onChange(true); dati.carica(); }}
        className={`min-h-[44px] rounded-xl border px-4 font-bold ${attivo ? "bg-[#5b7a6b] text-white" : "bg-white text-[#3f5a4e]"}`}>
        ★ Preferiti ({dati.prodotti.length})
      </button>
      <button type="button" aria-pressed={!attivo} onClick={() => onChange(false)}
        className={`min-h-[44px] rounded-xl border px-4 font-bold ${!attivo ? "bg-[#5b7a6b] text-white" : "bg-white text-[#3f5a4e]"}`}>
        Tutto il catalogo
      </button>
      {dati.loading && <span role="status" className="text-sm text-gray-500">Aggiorno gli acquisti…</span>}
    </div>
    <p className="text-sm text-gray-500">I preferiti si aggiornano dai prodotti delle fatture di acquisto.</p>
    {dati.errore && <p role="alert" className="text-sm text-red-700">{dati.errore}</p>}
  </div>;
}
