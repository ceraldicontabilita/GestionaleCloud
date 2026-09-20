import React, { useEffect, useState } from "react";
import { Landmark, Boxes, Users, UtensilsCrossed, ArrowUpRight } from "lucide-react";

/**
 * Il passaggio alle altre sezioni del gruppo.
 *
 * Qui c'era un solo collegamento, verso il gestionale, con il percorso scritto
 * a mano. Verso il personale e verso il menu non si passava: bisognava
 * riscrivere l'indirizzo.
 *
 * L'elenco ora arriva da `/api/sezioni`, l'unico posto dove sta scritto quali
 * sezioni esistono e dove vivono. L'aspetto resta quello della barra di Lotti.
 *
 * Il PIN non si rifà: magazzino e portale dipendenti condividono la verifica
 * del token (services/sessione_unica.py).
 *
 * `g-sezione-link` porta l'altezza minima di 44px: si tocca dal tablet, con
 * le mani sporche.
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
            className="g-sezione-link"
          >
            <Icona size={13} />
            {s.nome}
          </a>
        );
      })}
    </>
  );
}
