import React, { useEffect, useState } from 'react';
import { Landmark, Boxes, Users, UtensilsCrossed, ArrowUpRight } from 'lucide-react';

/**
 * Il passaggio alle altre sezioni del gruppo.
 *
 * Il gestionale i collegamenti verso qui li aveva già; da qui non si tornava
 * indietro, e nemmeno si passava al magazzino: una porta a senso unico, che
 * dal di dentro sembra un muro. L'unica via era riscrivere l'indirizzo.
 *
 * L'elenco arriva da `/api/sezioni`, che è l'unico posto dove sta scritto
 * quali sezioni esistono e dove vivono. Sta in fondo alla barra laterale, che
 * è salvia scuro: testo chiaro, o l'inchiostro sparisce sul verde. Il ritorno
 * rapido al Gestionale è anche in testata (App.jsx), sempre in vista.
 *
 * Il PIN non si rifà: magazzino e portale condividono la verifica del token
 * (services/workforce_tokens.py), quindi chi è entrato resta dentro.
 */
const ICONE = { Landmark, Boxes, Users, UtensilsCrossed };

export default function SelettoreSezioni({ sezioneCorrente }) {
  const [sezioni, setSezioni] = useState([]);

  useEffect(() => {
    let vivo = true;
    fetch('/api/sezioni')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (vivo && d?.sezioni) setSezioni(d.sezioni); })
      // Senza elenco non si mostra niente: meglio nessun collegamento che
      // un collegamento inventato verso un percorso che non esiste.
      .catch(() => {});
    return () => { vivo = false; };
  }, []);

  const altre = sezioni.filter((s) => s.id !== sezioneCorrente);
  if (!altre.length) return null;

  return (
    <div style={{ padding: '14px 12px', borderTop: '1px solid rgba(255,255,255,0.12)' }}>
      <div style={{
        fontSize: 11, fontWeight: 700, letterSpacing: '0.06em',
        textTransform: 'uppercase', color: 'rgba(255,255,255,0.72)', marginBottom: 8,
      }}>
        Vai a
      </div>
      {altre.map((s) => {
        const Icona = ICONE[s.icona] || ArrowUpRight;
        return (
          <a
            key={s.id}
            href={s.percorso}
            title={s.descrizione}
            style={{
              display: 'flex', alignItems: 'center', gap: 10,
              minHeight: 44, padding: '0 10px', borderRadius: 8,
              color: '#fffefb', textDecoration: 'none', fontSize: 14, fontWeight: 600,
            }}
          >
            <Icona size={18} color="#dfe8e1" aria-hidden="true" />
            <span>{s.nome}</span>
          </a>
        );
      })}
    </div>
  );
}
