import React, { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, ChefHat, Clock, Hash } from 'lucide-react';
import { toast } from 'sonner';
import { aggiornaStatoOrdine, elencoOrdini, messaggioErrore } from '../api';

const minutiDa = (iso) => {
  try { return Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000)); } catch { return 0; }
};

const Ticket = ({ order, onStart, onReady }) => {
  const mins = minutiDa(order.created_at);
  const urgent = mins >= 10;
  return (
    <div className={`rounded-xl p-4 border-2 ${urgent ? 'border-[#d35f4e] bg-[#d35f4e]/20' : 'border-white/20 bg-white/5'}`}>
      <div className="flex justify-between items-center mb-2 text-white/70 text-sm">
        <span className="flex items-center gap-1"><Clock className="w-4 h-4" /> {mins} min</span>
        {order.table && <span className="flex items-center gap-1 font-semibold text-white"><Hash className="w-4 h-4" /> Tavolo {order.table}</span>}
      </div>
      <ul className="space-y-1 mb-4">
        {order.items.map((it, idx) => (
          <li key={idx} className="text-lg text-white flex justify-between"><span className="font-bold">{it.quantity}x</span><span className="flex-1 ml-2">{it.name}</span></li>
        ))}
      </ul>
      {order.note && <p className="text-amber-300 text-sm italic mb-3">Nota: {order.note}</p>}
      {order.status === 'nuovo' ? (
        <button onClick={() => onStart(order.id)} className="w-full bg-amber-500 hover:bg-amber-400 text-black font-bold rounded-lg py-2">Inizia preparazione</button>
      ) : (
        <button onClick={() => onReady(order.id)} className="w-full flex items-center justify-center gap-2 bg-emerald-500 hover:bg-emerald-400 text-black font-bold rounded-lg py-2"><CheckCircle2 className="w-5 h-5" /> Pronto</button>
      )}
    </div>
  );
};

export default function Cucina() {
  const [orders, setOrders] = useState([]);
  const [now, setNow] = useState(Date.now());

  const load = useCallback(async () => {
    try {
      const attivi = await elencoOrdini({ active_only: true });
      setOrders(attivi.filter((o) => o.status === 'nuovo' || o.status === 'in_corso'));
    } catch (err) { console.error('Errore caricamento cucina', err); }
  }, []);

  useEffect(() => {
    load();
    const iv = setInterval(load, 5000);
    const clock = setInterval(() => setNow(Date.now()), 30000);
    return () => { clearInterval(iv); clearInterval(clock); };
  }, [load]);

  const cambia = async (id, status) => {
    try { await aggiornaStatoOrdine(id, status); load(); } catch (err) { toast.error('Errore', { description: messaggioErrore(err, "Impossibile aggiornare l'ordine") }); }
  };

  const nuovi = orders.filter((o) => o.status === 'nuovo');
  const inCorso = orders.filter((o) => o.status === 'in_corso');
  return (
    <div className="min-h-[80vh] bg-[#1a1a1a] p-6 rounded-xl">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-3xl font-bold text-white flex items-center gap-3"><ChefHat className="w-8 h-8 text-amber-400" /> Monitor cucina</h2>
        <span className="text-white/60">{new Date(now).toLocaleTimeString('it-IT')}</span>
      </div>
      {orders.length === 0 ? (
        <p className="text-white/50 text-xl text-center py-24">Nessun ordine attivo — cucina libera</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <h3 className="text-amber-400 font-semibold mb-3 uppercase tracking-wide text-sm">Da iniziare ({nuovi.length})</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">{nuovi.map((o) => <Ticket key={o.id} order={o} onStart={(id) => cambia(id, 'in_corso')} onReady={(id) => cambia(id, 'pronto')} />)}</div>
          </div>
          <div>
            <h3 className="text-emerald-400 font-semibold mb-3 uppercase tracking-wide text-sm">In preparazione ({inCorso.length})</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">{inCorso.map((o) => <Ticket key={o.id} order={o} onStart={(id) => cambia(id, 'in_corso')} onReady={(id) => cambia(id, 'pronto')} />)}</div>
          </div>
        </div>
      )}
    </div>
  );
}
