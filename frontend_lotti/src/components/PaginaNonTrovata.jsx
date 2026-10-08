import { Compass, Home } from "lucide-react";

// Pagina per un indirizzo che non esiste (link vecchio, errore di battitura):
// prima l'area restava vuota, senza dire niente.
export default function PaginaNonTrovata({ id, onHome }) {
  return (
    <div role="alert" className="mx-auto max-w-md rounded-2xl border border-[#e6e0d4] bg-[#fffefb] p-8 text-center">
      <Compass className="mx-auto mb-3 text-[#8a6f47]" size={36} aria-hidden="true" />
      <h2 className="m-0 text-xl font-extrabold text-[#2a3329]">Pagina non trovata</h2>
      <p className="mt-2 text-sm text-[#6b7669]">
        {id ? <>L'indirizzo «{id}» non corrisponde a nessuna pagina.</> : "Questo indirizzo non corrisponde a nessuna pagina."}
      </p>
      <button
        type="button"
        onClick={onHome}
        className="mt-4 inline-flex min-h-[44px] items-center gap-2 rounded-xl bg-[#5b7a6b] px-5 text-sm font-bold text-white"
      >
        <Home size={16} aria-hidden="true" /> Torna alla Home
      </button>
    </div>
  );
}
