import React, { useCallback, useEffect, useState } from 'react';
import { ArrowRight, Clock, Hash, Loader2, User, X } from 'lucide-react';
import { toast } from 'sonner';
import { aggiornaStatoOrdine, elencoOrdini, euro, messaggioErrore } from '../api';

const COLUMNS = [
  { status: 'nuovo', label: 'Nuovi', color: 'bg-[#e8efe9] border-[#5b7a6b]' },
  { status: 'in_corso', label: 'In corso', color: 'bg-amber-100 border-amber-300' },
  { status: 'pronto', label: 'Pronti', color: 'bg-emerald-100 border-emerald-300' },
  { status: 'completato', label: 'Completati', color: 'bg-gray-100 border-gray-300' },
];
const NEXT_STATUS = { nuovo: 'in_corso', in_corso: 'pronto', pronto: 'completato' };

export const oraDa = (iso) => {
  try { return new Date(iso).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }); } catch { return ''; }
};

const OrderCard = ({ order, onAdvance, onCancel }) => {
  const next = NEXT_STATUS[order.status];
  return (
    <div className="bg-white rounded-lg shadow p-4 mb-3 border border-[#e6e0d4]">
      <div className="flex justify-between items-start mb-2">
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Clock className="w-4 h-4" /> {oraDa(order.created_at)}
          {order.table && <span className="flex items-center gap-1 ml-2"><Hash className="w-4 h-4" /> {order.table}</span>}
        </div>
        <span className="text-xs px-2 py-1 rounded-full bg-gray-100 text-gray-600">{order.source === 'cassa' ? 'Cassa' : 'Cliente'}</span>
      </div>
      {order.customer_name && <p className="text-sm text-gray-600 flex items-center gap-1 mb-1"><User className="w-3 h-3" /> {order.customer_name}</p>}
      {order.sala_nome && <p className="text-xs text-gray-500 mb-1">Sala: {order.sala_nome}</p>}
      <ul className="text-sm mb-3 space-y-1">
        {order.items.map((it, idx) => (
          <li key={idx} className="flex justify-between"><span>{it.quantity}x {it.name}</span><span className="text-gray-500">{it.price}</span></li>
        ))}
      </ul>
      {order.note && <p className="text-xs italic text-gray-500 mb-2">Nota: {order.note}</p>}
      <div className="flex justify-between items-center pt-2 border-t border-[#e6e0d4]">
        <span className="font-bold text-[#3f5a4e]">{euro(order.total)}{order.paid ? ' · pagato' : ''}</span>
        <div className="flex gap-2">
          {order.status !== 'completato' && (
            <button onClick={() => onCancel(order.id)} className="text-[#d35f4e] hover:bg-red-50 rounded p-1.5" title="Annulla"><X className="w-4 h-4" /></button>
          )}
          {next && (
            <button onClick={() => onAdvance(order.id, next)} className="flex items-center gap-1 text-sm bg-[#5b7a6b] text-white rounded-lg px-3 py-1.5 hover:bg-[#3f5a4e]">Avanza <ArrowRight className="w-3 h-3" /></button>
          )}
        </div>
      </div>
    </div>
  );
};

export default function Ordini() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try { setOrders(await elencoOrdini()); } catch (err) { console.error('Errore caricamento ordini', err); } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    load();
    const iv = setInterval(load, 5000);
    return () => clearInterval(iv);
  }, [load]);

  const cambia = async (id, status, msg) => {
    try { await aggiornaStatoOrdine(id, status); load(); } catch (err) { toast.error('Errore', { description: messaggioErrore(err, msg) }); }
  };

  return (
    <div>
      <h2 className="text-xl font-bold text-[#2a3329] mb-1">Ordini</h2>
      <p className="text-sm text-gray-500 mb-4">Gestione ordini in tempo reale (aggiornamento ogni 5 secondi)</p>
      {loading ? (
        <div className="flex justify-center py-12"><Loader2 className="w-8 h-8 animate-spin text-[#5b7a6b]" /></div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {COLUMNS.map((col) => {
            const columnOrders = orders.filter((o) => o.status === col.status);
            return (
              <div key={col.status} className={`rounded-lg border-2 ${col.color} p-3 min-h-[200px]`}>
                <h3 className="font-bold mb-3 flex items-center justify-between">{col.label}<span className="text-sm bg-white rounded-full px-2 py-0.5">{columnOrders.length}</span></h3>
                {columnOrders.length === 0 && <p className="text-sm text-gray-400 text-center py-6">Nessun ordine</p>}
                {columnOrders.map((order) => (
                  <OrderCard key={order.id} order={order} onAdvance={(id, s) => cambia(id, s, "Impossibile aggiornare l'ordine")} onCancel={(id) => cambia(id, 'annullato', "Impossibile annullare l'ordine")} />
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
