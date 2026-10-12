export default function FiltroPreferitiAcquisti({ attivo, onChange, dati }) {
  const conteggio = dati.loading && dati.prodotti.length === 0 ? "…" : dati.prodotti.length;
  return <div className="space-y-2">
    <div className="flex flex-wrap items-center gap-2">
      <button type="button" aria-pressed={attivo} onClick={() => { onChange(true); dati.carica(); }}
        aria-busy={dati.loading}
        className={`min-h-[44px] rounded-xl border px-4 font-bold ${attivo ? "bg-[#5b7a6b] text-white" : "bg-white text-[#3f5a4e]"}`}>
        Acquistati e preferiti ({conteggio})
      </button>
      <button type="button" aria-pressed={!attivo} onClick={() => onChange(false)}
        className={`min-h-[44px] rounded-xl border px-4 font-bold ${!attivo ? "bg-[#5b7a6b] text-white" : "bg-white text-[#3f5a4e]"}`}>
        Tutto il catalogo
      </button>
      {dati.loading && <span role="status" className="text-sm text-gray-500">Aggiorno gli acquisti…</span>}
    </div>
    <p className="text-sm text-gray-500">Qui trovi i prodotti già acquistati dalle fatture e quelli che hai aggiunto ai preferiti.</p>
    {dati.errore && <p role="alert" className="text-sm text-red-700">{dati.errore}</p>}
  </div>;
}
