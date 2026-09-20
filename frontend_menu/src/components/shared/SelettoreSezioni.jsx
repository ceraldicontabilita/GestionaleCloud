import React, { useEffect, useState } from "react";
import { Landmark, Boxes, Users, UtensilsCrossed, ArrowUpRight } from "lucide-react";

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
 */
const ICONE = { Landmark, Boxes, Users, UtensilsCrossed };

export default function SelettoreSezioni({ sezioneCorrente }) {
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

  const altre = sezioni.filter((s) => s.id !== sezioneCorrente);
  if (!altre.length) return null;

  return (
    <>
      {altre.map((s) => {
        const Icona = ICONE[s.icona] || ArrowUpRight;
        return (
          <a
            key={s.id}
            href={s.percorso}
            title={s.descrizione}
            data-testid={`nav-sezione-${s.id}`}
            className="inline-flex items-center gap-2 min-h-[44px] px-3 rounded-lg text-sm font-semibold text-white/90 hover:bg-white/10"
          >
            <Icona size={16} />
            {s.nome}
          </a>
        );
      })}
    </>
  );
}
