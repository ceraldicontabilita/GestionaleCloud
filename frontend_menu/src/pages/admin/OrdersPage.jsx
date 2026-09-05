import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Clock, User, Hash, X, ArrowRight, Loader2 } from 'lucide-react';
import AdminPageHeader from '../../components/admin/AdminPageHeader';
import { useAdminAuth } from '../../hooks/useAdminAuth';
import { toast } from '../../hooks/use-toast';

const BACKEND_URL = process.env.REACT_APP_MENU_BACKEND_URL;

const COLUMNS = [
  { status: 'nuovo', label: 'Nuovi', color: 'bg-blue-100 border-blue-300' },
  { status: 'in_corso', label: 'In corso', color: 'bg-amber-100 border-amber-300' },
  { status: 'pronto', label: 'Pronti', color: 'bg-emerald-100 border-emerald-300' },
  { status: 'completato', label: 'Completati', color: 'bg-gray-100 border-gray-300' },
];

const NEXT_STATUS = {
  nuovo: 'in_corso',
  in_corso: 'pronto',
  pronto: 'completato',
};

const formatTime = (iso) => {
  try {
    return new Date(iso).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
};

const OrderCard = ({ order, onAdvance, onCancel }) => {
  const next = NEXT_STATUS[order.status];
  return (
    <div className="bg-white rounded-lg shadow p-4 mb-3 border">
      <div className="flex justify-between items-start mb-2">
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Clock className="w-4 h-4" />
          {formatTime(order.created_at)}
          {order.table && (
            <span className="flex items-center gap-1 ml-2">
              <Hash className="w-4 h-4" /> {order.table}
            </span>
          )}
        </div>
        <span className="text-xs px-2 py-1 rounded-full bg-gray-100 text-gray-600">
          {order.source === 'cassa' ? 'Cassa' : 'Cliente'}
        </span>
      </div>
      {order.customer_name && (
        <p className="text-sm text-gray-600 flex items-center gap-1 mb-1">
          <User className="w-3 h-3" /> {order.customer_name}
        </p>
      )}
      <ul className="text-sm mb-3 space-y-1">
        {order.items.map((it, idx) => (
          <li key={idx} className="flex justify-between">
            <span>{it.quantity}x {it.name}</span>
            <span className="text-gray-500">{it.price}</span>
          </li>
        ))}
      </ul>
      {order.note && <p className="text-xs italic text-gray-500 mb-2">Nota: {order.note}</p>}
      <div className="flex justify-between items-center pt-2 border-t">
        <span className="font-bold text-[#4a5d4a]">€ {order.total?.toFixed(2)}</span>
        <div className="flex gap-2">
          {order.status !== 'completato' && (
            <button
              onClick={() => onCancel(order.id)}
              className="text-red-500 hover:bg-red-50 rounded p-1.5"
              title="Annulla"
            >
              <X className="w-4 h-4" />
            </button>
          )}
          {next && (
            <button
              onClick={() => onAdvance(order.id, next)}
              className="flex items-center gap-1 text-sm bg-[#4a5d4a] text-white rounded-lg px-3 py-1.5 hover:bg-[#3d4d3d]"
            >
              Avanza <ArrowRight className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

const OrdersPage = () => {
  const { checking, authorized, authHeader } = useAdminAuth();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadOrders = useCallback(async () => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/orders/`, { headers: authHeader });
      setOrders(res.data);
    } catch (err) {
      console.error('Errore caricamento ordini', err);
    } finally {
      setLoading(false);
    }
  }, [authHeader.Authorization]);

  useEffect(() => {
    if (!authorized) return;
    loadOrders();
    const interval = setInterval(loadOrders, 5000);
    return () => clearInterval(interval);
  }, [authorized, loadOrders]);

  const handleAdvance = async (id, status) => {
    try {
      await axios.patch(`${BACKEND_URL}/api/orders/${id}/status`, { status }, { headers: authHeader });
      loadOrders();
    } catch {
      toast({ title: 'Errore', description: 'Impossibile aggiornare l\'ordine', variant: 'destructive' });
    }
  };

  const handleCancel = async (id) => {
    try {
      await axios.patch(`${BACKEND_URL}/api/orders/${id}/status`, { status: 'annullato' }, { headers: authHeader });
      loadOrders();
    } catch {
      toast({ title: 'Errore', description: 'Impossibile annullare l\'ordine', variant: 'destructive' });
    }
  };

  if (checking) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-[#4a5d4a]" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <AdminPageHeader title="Ordini" subtitle="Gestione ordini in tempo reale" />
      <div className="max-w-7xl mx-auto px-4 py-6">
        {loading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-[#4a5d4a]" />
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {COLUMNS.map((col) => {
              const columnOrders = orders.filter((o) => o.status === col.status);
              return (
                <div key={col.status} className={`rounded-lg border-2 ${col.color} p-3 min-h-[200px]`}>
                  <h2 className="font-bold mb-3 flex items-center justify-between">
                    {col.label}
                    <span className="text-sm bg-white rounded-full px-2 py-0.5">{columnOrders.length}</span>
                  </h2>
                  {columnOrders.length === 0 && (
                    <p className="text-sm text-gray-400 text-center py-6">Nessun ordine</p>
                  )}
                  {columnOrders.map((order) => (
                    <OrderCard key={order.id} order={order} onAdvance={handleAdvance} onCancel={handleCancel} />
                  ))}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default OrdersPage;
