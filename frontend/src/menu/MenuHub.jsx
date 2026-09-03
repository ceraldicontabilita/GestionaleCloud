/**
 * Area operativa del menu digitale dentro il gestionale — rotte /menu/<sezione>
 * (/menu senza sezione e' il menu pubblico dei clienti, MenuPubblico.jsx).
 *
 * Sotto-pagine: Ordini, Cassa, Cucina (monitor), Magazzino bar (condiviso con
 * Lotti), Sale, Gestione (prodotti, immagini, QR code, backup e migrazione).
 * Le prime quattro sono lavoro di banco e valgono anche per una sessione del
 * portale dipendenti (rotta /menu-banco, `standalone`): in quel caso il
 * componente porta una testata propria senza il layout del gestionale.
 */
import React, { useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import { ChefHat, ClipboardList, DoorOpen, LogOut, Settings2, ShoppingBag, Warehouse } from 'lucide-react';
import './menu.css';
import { puoGestire, ruoloCorrente } from './api';
import Ordini from './pagine/Ordini.jsx';
import Cassa from './pagine/Cassa.jsx';
import Cucina from './pagine/Cucina.jsx';
import Magazzino from './pagine/Magazzino.jsx';
import Sale from './pagine/Sale.jsx';
import Gestione from './pagine/Gestione.jsx';

const SEZIONI = [
  { to: 'ordini', label: 'Ordini', desc: 'Ordini in arrivo, in corso e pronti', Icon: ShoppingBag, banco: true },
  { to: 'cassa', label: 'Cassa', desc: 'Ordini al banco e incassi', Icon: ClipboardList, banco: true },
  { to: 'cucina', label: 'Cucina', desc: 'Monitor di preparazione', Icon: ChefHat, banco: true },
  { to: 'magazzino', label: 'Magazzino bar', desc: 'Giacenze, carichi e scarichi (condiviso con Lotti)', Icon: Warehouse, banco: true },
  { to: 'sale', label: 'Sale', desc: 'Sale del locale, ordini e coperto', Icon: DoorOpen, banco: false },
  { to: 'gestione', label: 'Gestione menu', desc: 'Prodotti, immagini, QR code, backup', Icon: Settings2, banco: false, gestione: true },
];

export default function MenuHub({ standalone = false }) {
  const navigate = useNavigate();
  const [ruolo, setRuolo] = useState(() => ruoloCorrente());
  useEffect(() => { setRuolo(ruoloCorrente()); }, []);
  const gestione = puoGestire(ruolo);
  const sezioni = SEZIONI.filter((s) => (standalone ? s.banco : true)).filter((s) => !s.gestione || gestione);

  const esci = () => {
    localStorage.removeItem('pt_token');
    localStorage.removeItem('pt_role');
    localStorage.removeItem('pt_name');
    navigate('/portale', { replace: true });
  };

  return (
    <div className={`menu-root ${standalone ? 'min-h-screen bg-[#faf7f0]' : ''}`}>
      {standalone && (
        <div className="bg-[#3f5a4e] text-white shadow-lg">
          <div className="max-w-7xl mx-auto px-4 py-3 flex justify-between items-center">
            <div>
              <h1 className="text-xl font-bold">Ceraldi Caffè — Banco</h1>
              <p className="text-sm text-white/80">{localStorage.getItem('pt_name') || 'Portale dipendenti'}</p>
            </div>
            <button onClick={esci} className="inline-flex items-center gap-2 text-white hover:bg-white/10 rounded-md px-3 py-2 text-sm"><LogOut className="w-4 h-4" /> Esci</button>
          </div>
        </div>
      )}
      <div className="max-w-7xl mx-auto px-4 py-4">
        <nav className="flex flex-wrap gap-2 mb-4" aria-label="Sezioni menu">
          {sezioni.map((s) => (
            <NavLink key={s.to} to={s.to} title={s.desc} className={({ isActive }) => `inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium border ${isActive ? 'bg-[#5b7a6b] text-white border-[#5b7a6b]' : 'bg-white text-[#3f5a4e] border-[#e6e0d4] hover:bg-[#e8efe9]'}`}>
              <s.Icon className="w-4 h-4" /> {s.label}
            </NavLink>
          ))}
        </nav>
        <Routes>
          <Route index element={<Navigate to="ordini" replace />} />
          <Route path="ordini" element={<Ordini />} />
          <Route path="cassa" element={<Cassa />} />
          <Route path="cucina" element={<Cucina />} />
          <Route path="magazzino" element={<Magazzino ruolo={ruolo} />} />
          {!standalone && <Route path="sale" element={<Sale ruolo={ruolo} />} />}
          {!standalone && gestione && <Route path="gestione/*" element={<Gestione ruolo={ruolo} />} />}
          <Route path="*" element={<Navigate to="ordini" replace />} />
        </Routes>
      </div>
    </div>
  );
}
