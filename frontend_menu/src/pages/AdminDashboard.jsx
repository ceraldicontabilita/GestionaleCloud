import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Button } from '../components/ui/button';
import { LogOut, Image, Package, Database, ClipboardList, ShoppingBag, ChefHat, Warehouse, DoorOpen, ArrowLeft, ExternalLink } from 'lucide-react';
import SelettoreSezioni from "../components/shared/SelettoreSezioni";
import axios from 'axios';
import { esciDalGruppo } from '../lib/sessioneGruppo';

import ImageUploadManager from '../components/admin/ImageUploadManager';
import ProductManager from '../components/admin/ProductManager';
import AllergeniMancanti from '../components/admin/AllergeniMancanti';
import BackupManager from '../components/admin/BackupManager';
import MenuClientiQR from '../components/admin/MenuClientiQR';

const BACKEND_URL = process.env.REACT_APP_MENU_BACKEND_URL;

const AdminDashboard = () => {
  const [activeTab, setActiveTab] = useState('operazioni');
  const navigate = useNavigate();

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    const token = localStorage.getItem('admin_token');
    if (!token) {
      navigate('/admin/login');
      return;
    }

    try {
      await axios.get(`${BACKEND_URL}/api/qrcode/verify`, {
        headers: { Authorization: `Bearer ${token}` }
      });
    } catch (error) {
      localStorage.removeItem('admin_token');
      navigate('/admin/login');
    }
  };


  return (
    <div className="min-h-screen bg-gray-50">
      {/* Intestazione fissa da tablet in su: si torna al gestionale e si apre
          il menu dei clienti da qualunque punto della pagina. Sul telefono
          scorre con la pagina (andando a capo occuperebbe mezzo schermo), e
          «Apri menu clienti» si ripete nel riquadro subito sotto. Nessun ingranaggio
          «Impostazioni»: il Menu non ha una pagina di impostazioni propria. */}
      <header className="md:sticky md:top-0 z-40 bg-[#4a5d4a] text-white shadow-lg">
        <div className="max-w-7xl mx-auto px-4 py-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <a
              href="/"
              className="inline-flex items-center gap-2 min-h-[44px] px-3 rounded-lg text-sm font-semibold bg-white/10 hover:bg-white/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#faf7f0]"
              data-testid="torna-gestionale"
            >
              <ArrowLeft className="w-4 h-4" aria-hidden="true" />
              Gestionale
            </a>
            <div className="min-w-0">
              <h1 className="text-xl md:text-2xl font-bold">Gestione Menu</h1>
              <p className="text-sm text-white/80">Ceraldi Caffè · amministrazione</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-1">
            <a
              href={`${process.env.PUBLIC_URL || ''}/`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 min-h-[44px] px-4 rounded-lg text-sm font-bold bg-[#faf7f0] text-[#2a3329] hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#faf7f0] focus-visible:ring-offset-2 focus-visible:ring-offset-[#4a5d4a]"
              data-testid="apri-menu-clienti"
            >
              <ExternalLink className="w-4 h-4" aria-hidden="true" />
              Apri menu clienti
            </a>
            <SelettoreSezioni sezioneCorrente="menu" paginaCorrente="menu-gestione" escludi={['gestionale']} />
            <Button variant="ghost" onClick={esciDalGruppo} className="min-h-[44px] text-white hover:bg-white/10">
              <LogOut className="w-4 h-4 mr-2" />
              Esci
            </Button>
          </div>
        </div>
      </header>

      {/* Main Content with Tabs */}
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="mb-8">
          <MenuClientiQR />
        </div>
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-2 sm:grid-cols-4 h-auto mb-8">
            <TabsTrigger value="operazioni" className="flex items-center gap-2">
              <ClipboardList className="w-4 h-4" />
              <span>Operazioni</span>
            </TabsTrigger>
            <TabsTrigger value="images" className="flex items-center gap-2">
              <Image className="w-4 h-4" />
              <span>Immagini</span>
            </TabsTrigger>
            <TabsTrigger value="products" className="flex items-center gap-2">
              <Package className="w-4 h-4" />
              <span>Prodotti</span>
            </TabsTrigger>
            <TabsTrigger value="backup" className="flex items-center gap-2">
              <Database className="w-4 h-4" />
              <span>Backup</span>
            </TabsTrigger>
          </TabsList>

          <TabsContent value="operazioni">
            <div className="space-y-6">
              <div className="bg-white rounded-lg shadow p-6">
                <h2 className="text-xl font-bold mb-4">Operazioni del locale</h2>
                <p className="text-gray-600 mb-4">
                  Ordini, cassa, cucina e magazzino: le schermate operative pensate per lo staff, ognuna a schermo intero.
                </p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {[
                  { to: '/admin/ordini', label: 'Ordini', desc: 'Gestisci gli ordini in arrivo, in corso e pronti', icon: ShoppingBag },
                  { to: '/admin/cassa', label: 'Cassa', desc: 'Registra ordini al banco e incassi', icon: ClipboardList },
                  { to: '/admin/cucina', label: 'Kitchen Monitor', desc: 'Schermo cucina per la preparazione', icon: ChefHat },
                  { to: '/admin/magazzino', label: 'Magazzino', desc: 'Giacenze, carichi e scarichi', icon: Warehouse },
                  { to: '/admin/sale', label: 'Sale', desc: 'Gestisci le sale, ordini e coperto', icon: DoorOpen },
                ].map((op) => (
                  <button
                    key={op.to}
                    onClick={() => (window.location.href = `${process.env.PUBLIC_URL || ''}${op.to}`)}
                    className="bg-white rounded-lg shadow p-6 text-left hover:shadow-md hover:-translate-y-0.5 transition-all border"
                  >
                    <op.icon className="w-8 h-8 text-[#4a5d4a] mb-3" />
                    <h3 className="font-bold text-lg mb-1">{op.label}</h3>
                    <p className="text-sm text-gray-500">{op.desc}</p>
                  </button>
                ))}
              </div>
            </div>
          </TabsContent>

          <TabsContent value="images">
            <div className="space-y-6">
              <div className="bg-white rounded-lg shadow p-6">
                <h2 className="text-xl font-bold mb-4">Gestione Immagini</h2>
                <p className="text-gray-600 mb-4">
                  Carica immagini dei prodotti e associale automaticamente
                </p>
              </div>
              <ImageUploadManager />
            </div>
          </TabsContent>

          <TabsContent value="products">
            <div className="space-y-6">
              <div className="bg-white rounded-lg shadow p-6">
                <h2 className="text-xl font-bold mb-4">Gestione Prodotti</h2>
                <p className="text-gray-600 mb-4">
                  Modifica nomi, prezzi, descrizioni e allergeni dei prodotti
                </p>
              </div>
              <AllergeniMancanti />
              <ProductManager />
            </div>
          </TabsContent>

          <TabsContent value="backup">
            <div className="space-y-6">
              <div className="bg-white rounded-lg shadow p-6">
                <h2 className="text-xl font-bold mb-4">Gestione Backup Database</h2>
                <p className="text-gray-600 mb-4">
                  Crea, scarica e ripristina i backup dei dati del Menu
                </p>
              </div>
              <BackupManager />
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

export default AdminDashboard;