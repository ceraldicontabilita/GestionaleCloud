import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Clock, Hash, CheckCircle2, ChefHat, Loader2 } from 'lucide-react';
import { useAdminAuth } from '../../hooks/useAdminAuth';

const BACKEND_URL = process.env.REACT_APP_MENU_BACKEND_URL;

const elapsedMinutes = (iso) => {
  try {
    return Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000));
  } catch {
    return 0;
  }
};

const Ticket = ({ order, onStart, onReady }) => {
  const mins = elapsedMinutes(order.created_at);
  const urgent = mins >= 10;
  return (
    <div className={`rounded-xl p-4 border-2 ${urgent ? 'border-red-500 bg-red-950/40' : 'border-white/20 bg-white/5'}`}>
      <div className="flex justify-between items-center mb-2 text-white/70 text-sm">
        <span className="flex items-center gap-1">
          <Clock className="w-4 h-4" /> {mins} min
        </span>
        {order.table && (
          <span className="flex items-center gap-1 font-semibold text-white">
            <Hash className="w-4 h-4" /> Tavolo {order.table}
          </span>
        )}
      </div>
      <ul className="space-y-1 mb-4">
        {order.items.map((it, idx) => (
          <li key={idx} className="text-lg text-white flex justify-between">
            <span className="font-bold">{it.quantity}x</span>
            <span className="flex-1 ml-2">{it.name}</span>
          </li>
        ))}
      </ul>
      {order.note && <p className="text-amber-300 text-sm italic mb-3">Nota: {order.note}</p>}
      {order.status === 'nuovo' ? (
        <button
          onClick={() => onStart(order.id)}
          className="w-full bg-amber-500 hover:bg-amber-400 text-black font-bold rounded-lg py-2"
        >
          Inizia preparazione
        </button>
      ) : (
        <button
          onClick={() => onReady(order.id)}
          className="w-full flex items-center justify-center gap-2 bg-emerald-500 hover:bg-emerald-400 text-black font-bold rounded-lg py-2"
        >
          <CheckCircle2 className="w-5 h-5" /> Pronto
        </button>
      )}
    </div>
  );
};

const KitchenMonitorPage = () => {
  const { checking, authorized, authHeader } = useAdminAuth();
  const [orders, setOrders] = useState([]);
  const [now, setNow] = useState(Date.now());

  const loadOrders = useCallback(async () => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/orders/`, {
        params: { active_only: true },
        headers: authHeader
      });
      setOrders(res.data.filter((o) => o.status === 'nuovo' || o.status === 'in_corso'));
    } catch (err) {
      console.error('Errore caricamento cucina', err);
    }
  }, [authHeader.Authorization]);

  useEffect(() => {
    if (!authorized) return;
    loadOrders();
    const interval = setInterval(loadOrders, 5000);
    const clock = setInterval(() => setNow(Date.now()), 30000);
    return () => {
      clearInterval(interval);
      clearInterval(clock);
    };
  }, [authorized, loadOrders]);

  const handleStart = async (id) => {
    await axios.patch(`${BACKEND_URL}/api/orders/${id}/status`, { status: 'in_corso' }, { headers: authHeader });
    loadOrders();
  };

  const handleReady = async (id) => {
    await axios.patch(`${BACKEND_URL}/api/orders/${id}/status`, { status: 'pronto' }, { headers: authHeader });
    loadOrders();
  };

  if (checking) {
    return (
      <div className="min-h-screen bg-[#1a1a1a] flex items-center justify-center">
        <Loader2 className="w-10 h-10 animate-spin text-white" />
      </div>
    );
  }

  const newOrders = orders.filter((o) => o.status === 'nuovo');
  const inProgress = orders.filter((o) => o.status === 'in_corso');

  return (
    <div className="min-h-screen bg-[#1a1a1a] p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
          <ChefHat className="w-8 h-8 text-amber-400" /> Kitchen Monitor
        </h1>
        <span className="text-white/60">{new Date(now).toLocaleTimeString('it-IT')}</span>
      </div>

      {orders.length === 0 ? (
        <p className="text-white/50 text-xl text-center py-24">Nessun ordine attivo — cucina libera</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <h2 className="text-amber-400 font-semibold mb-3 uppercase tracking-wide text-sm">Da iniziare ({newOrders.length})</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {newOrders.map((order) => (
                <Ticket key={order.id} order={order} onStart={handleStart} onReady={handleReady} />
              ))}
            </div>
          </div>
          <div>
            <h2 className="text-emerald-400 font-semibold mb-3 uppercase tracking-wide text-sm">In preparazione ({inProgress.length})</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {inProgress.map((order) => (
                <Ticket key={order.id} order={order} onStart={handleStart} onReady={handleReady} />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default KitchenMonitorPage;
