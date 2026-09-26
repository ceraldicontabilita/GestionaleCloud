import React, { useEffect, useState } from "react";
import { Landmark, Boxes, Users, UtensilsCrossed, Settings, ArrowUpRight } from "lucide-react";

/**
 * Il passaggio alle altre sezioni del gruppo.
 *
 * Dall'amministrazione del menu non si usciva: nessun collegamento al
 * gestionale, al magazzino o al personale. Per passare da una sezione
 * all'altra bisognava riscrivere l'indirizzo.
 *
 * L'elenco arriva da `/api/sezioni`, l'unico posto dove sta scritto quali
 * sezioni esistono e dove vivono. L'aspetto resta quello dell'intestazione
 * del menu.
 *
 * La sezione corrente si toglie, ma il Menu ha due facce (clienti e
 * gestione): dei `collegamenti` della sezione corrente si mostrano quelli
 * diversi dalla pagina in cui si e' (`paginaCorrente`), cosi' dalla gestione
 * si apre sempre il «Menu clienti». `escludi` toglie le sezioni che la pagina
 * mostra gia' con un pulsante proprio (es. «← Gestionale»).
 */
const ICONE = { Landmark, Boxes, Users, UtensilsCrossed, Settings };

export default function SelettoreSezioni({ sezioneCorrente, paginaCorrente, escludi = [] }) {
  const [sezioni, setSezioni] = useState([]);

  useEffect(() => {
    let vivo = true;
    fetch("/api/sezioni")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (vivo && d?.sezioni) setSezioni(d.sezioni); })
      // Senza elenco non si mostra niente: meglio nessun collegamento che uno
      // inventato verso un percorso che non esiste.
      .catch(() => {});
    return () => { vivo = false; };
  }, []);

  const corrente = sezioni.find((s) => s.id === sezioneCorrente);
  const interne = (corrente?.collegamenti || []).filter((c) => c.id !== paginaCorrente);
  const altre = sezioni.filter((s) => s.id !== sezioneCorrente && !escludi.includes(s.id));
  const voci = [...interne, ...altre];
  if (!voci.length) return null;

  return (
    <>
      {voci.map((s) => {
        const Icona = ICONE[s.icona] || ArrowUpRight;
        return (
          <a
            key={s.id}
            href={s.percorso}
            title={s.descrizione}
            data-testid={`nav-sezione-${s.id}`}
            className="inline-flex items-center gap-2 min-h-[44px] px-3 rounded-lg text-sm font-semibold text-white/90 hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#faf7f0]"
          >
            <Icona size={16} aria-hidden="true" />
            {s.nome}
          </a>
        );
      })}
    </>
  );
}
