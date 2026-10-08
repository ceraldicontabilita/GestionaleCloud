import { useEffect, useMemo, useState } from "react";

export function numeroTastierinoValido(value, min, max) {
  if (value === "") return { valido: false, messaggio: "Inserisci una quantità" };
  const numero = Number(value);
  if (!Number.isFinite(numero)) return { valido: false, messaggio: "Quantità non valida" };
  if (min !== undefined && numero < Number(min)) {
    return { valido: false, messaggio: `Il minimo è ${min}` };
  }
  if (max !== undefined && numero > Number(max)) {
    return { valido: false, messaggio: `Disponibili al massimo ${max} g` };
  }
  return { valido: true, messaggio: "" };
}

function valoreVisualizzato(value, unit) {
  if (value === "" || value === null || value === undefined) return "—";
  const numero = Number(value);
  return `${Number.isFinite(numero) ? numero.toLocaleString("it-IT") : value}${unit ? ` ${unit}` : ""}`;
}

/**
 * Campo numerico pensato per il tablet di laboratorio: al tocco apre un
 * tastierino grande e non richiama la tastiera di sistema.
 */
export default function TouchNumberInput({
  value,
  onChange,
  title = "Inserisci quantità",
  placeholder = "Tocca per inserire",
  unit = "g",
  min,
  max,
  presets = [],
  className = "",
  disabled = false,
  testId,
}) {
  const [aperto, setAperto] = useState(false);
  const [bozza, setBozza] = useState("");
  const [errore, setErrore] = useState("");

  const presetValidi = useMemo(() => [...new Set(presets.map(Number))]
    .filter((n) => Number.isFinite(n) && n >= 0 && (max === undefined || n <= Number(max))), [presets, max]);

  const apri = () => {
    if (disabled) return;
    setBozza(value === null || value === undefined ? "" : String(value));
    setErrore("");
    setAperto(true);
  };

  const premi = (tasto) => {
    setErrore("");
    if (tasto === "cancella") {
      setBozza((corrente) => corrente.slice(0, -1));
      return;
    }
    if (tasto === "azzera") {
      setBozza("");
      return;
    }
    setBozza((corrente) => (corrente === "0" ? tasto : `${corrente}${tasto}`).slice(0, 7));
  };

  const conferma = () => {
    const esito = numeroTastierinoValido(bozza, min, max);
    if (!esito.valido) {
      setErrore(esito.messaggio);
      return;
    }
    onChange(String(Number(bozza)));
    setAperto(false);
  };

  useEffect(() => {
    if (!aperto) return undefined;
    const gestisciTasto = (event) => {
      if (/^[0-9]$/.test(event.key)) premi(event.key);
      else if (event.key === "Backspace") premi("cancella");
      else if (event.key === "Delete") premi("azzera");
      else if (event.key === "Enter") conferma();
      else if (event.key === "Escape") setAperto(false);
    };
    window.addEventListener("keydown", gestisciTasto);
    return () => window.removeEventListener("keydown", gestisciTasto);
  });

  return (
    <>
      <button
        type="button"
        onClick={apri}
        disabled={disabled}
        data-testid={testId}
        aria-label={`${title}. ${valoreVisualizzato(value, unit)}`}
        className={`flex min-h-12 w-full items-center justify-between rounded-xl border border-stone-300 bg-white px-4 py-3 text-left text-base font-bold text-stone-900 shadow-sm transition hover:border-[#5b7a6b] hover:bg-[#f5f8f5] focus:outline-none focus:ring-2 focus:ring-[#5b7a6b]/30 disabled:cursor-not-allowed disabled:bg-stone-100 disabled:text-stone-400 ${className}`}
      >
        <span className={value === "" || value === null || value === undefined ? "font-medium text-stone-400" : ""}>
          {value === "" || value === null || value === undefined ? placeholder : valoreVisualizzato(value, unit)}
        </span>
        <span aria-hidden="true" className="ml-3 rounded-lg bg-[#e8efe9] px-2 py-1 text-xs font-black uppercase text-[#4a6657]">Tastierino</span>
      </button>

      {aperto && (
        <div
          className="fixed inset-0 z-[5000] flex items-end justify-center bg-black/60 p-2 sm:items-center sm:p-4"
          role="presentation"
          onMouseDown={(e) => { if (e.target === e.currentTarget) setAperto(false); }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-label={title}
            className="w-full max-w-sm rounded-t-3xl bg-stone-900 p-4 shadow-2xl sm:rounded-3xl sm:p-5"
          >
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <p className="m-0 text-xs font-black uppercase tracking-wide text-stone-400">{title}</p>
                {max !== undefined && <p className="m-0 mt-1 text-xs font-semibold text-emerald-300">Disponibili: {Number(max).toLocaleString("it-IT")} {unit}</p>}
              </div>
              <button type="button" onClick={() => setAperto(false)} aria-label="Chiudi tastierino" className="h-12 w-12 rounded-xl bg-stone-700 text-xl font-black text-white">×</button>
            </div>

            <div aria-live="polite" className={`mb-3 flex min-h-20 items-center justify-end rounded-2xl border px-4 text-4xl font-black ${errore ? "border-red-400 bg-red-950 text-red-100" : "border-stone-700 bg-black text-white"}`}>
              {bozza || "0"}<span className="ml-2 text-xl text-stone-400">{unit}</span>
            </div>
            {errore && <p className="-mt-1 mb-3 text-center text-sm font-bold text-red-300">{errore}</p>}

            {presetValidi.length > 0 && (
              <div className="mb-3 grid grid-cols-4 gap-2" aria-label="Quantità rapide">
                {presetValidi.slice(0, 4).map((preset) => (
                  <button key={preset} type="button" onClick={() => { setBozza(String(preset)); setErrore(""); }} className="min-h-12 rounded-xl bg-emerald-900 px-1 text-sm font-black text-emerald-50">
                    {preset.toLocaleString("it-IT")}
                  </button>
                ))}
              </div>
            )}

            <div className="grid grid-cols-3 gap-2" style={{ touchAction: "manipulation" }}>
              {["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((tasto) => (
                <button key={tasto} type="button" onClick={() => premi(tasto)} className="min-h-16 rounded-2xl bg-stone-700 text-2xl font-black text-white active:bg-[#5b7a6b]">{tasto}</button>
              ))}
              <button type="button" onClick={() => premi("azzera")} className="min-h-16 rounded-2xl bg-stone-800 text-sm font-black uppercase text-amber-200">Azzera</button>
              <button type="button" onClick={() => premi("0")} className="min-h-16 rounded-2xl bg-stone-700 text-2xl font-black text-white active:bg-[#5b7a6b]">0</button>
              <button type="button" onClick={() => premi("cancella")} aria-label="Cancella ultima cifra" className="min-h-16 rounded-2xl bg-stone-800 text-2xl font-black text-white">⌫</button>
            </div>
            <button type="button" onClick={conferma} className="mt-3 min-h-16 w-full rounded-2xl bg-[#5b7a6b] text-lg font-black text-white active:bg-[#3f5b4d]">✓ Conferma quantità</button>
          </section>
        </div>
      )}
    </>
  );
}
