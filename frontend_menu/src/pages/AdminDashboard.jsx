import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Button } from '../components/ui/button';
import { LogOut, QrCode, Image, Package, Database, ClipboardList, ShoppingBag, ChefHat, Warehouse, DoorOpen } from 'lucide-react';
import axios from 'axios';

// Import existing QR Code management
import AdminQRCodePage from './AdminQRCodePage';

// Import new components
import ImageUploadManager from '../components/admin/ImageUploadManager';
import ProductManager from '../components/admin/ProductManager';
import BackupManager from '../components/admin/BackupManager';

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

  const handleLogout = () => {
    localStorage.removeItem('admin_token');
    navigate('/admin/login');
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-[#4a5d4a] text-white shadow-lg">
        <div className="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold">Ceraldi Caffè Admin</h1>
            <p className="text-sm text-white/80">Pannello di Amministrazione</p>
          </div>
          <Button variant="ghost" onClick={handleLogout} className="text-white hover:bg-white/10">
            <LogOut className="w-4 h-4 mr-2" />
            Esci
          </Button>
        </div>
      </div>

      {/* Main Content with Tabs */}
      <div className="max-w-7xl mx-auto px-4 py-8">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-5 mb-8">
            <TabsTrigger value="operazioni" className="flex items-center gap-2">
              <ClipboardList className="w-4 h-4" />
              <span>Operazioni</span>
            </TabsTrigger>
            <TabsTrigger value="qrcode" className="flex items-center gap-2">
              <QrCode className="w-4 h-4" />
              <span>QR Code</span>
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

          <TabsContent value="qrcode">
            <div className="space-y-6">
              <div className="bg-white rounded-lg shadow p-6">
                <h2 className="text-xl font-bold mb-4">Gestione QR Code</h2>
                <p className="text-gray-600 mb-4">
                  Configura i QR code per il menu e il WiFi del locale
                </p>
              </div>
              {/* Reuse existing QR code content without header */}
              <AdminQRCodeContent />
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
              <ProductManager />
            </div>
          </TabsContent>

          <TabsContent value="backup">
            <div className="space-y-6">
              <div className="bg-white rounded-lg shadow p-6">
                <h2 className="text-xl font-bold mb-4">Gestione Backup Database</h2>
                <p className="text-gray-600 mb-4">
                  Crea, scarica e ripristina backup del database MongoDB
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

// Extract QR code content component (without outer layout)
const AdminQRCodeContent = () => {
  // This would contain the QR code form/display logic
  // For now, redirect to separate page or inline the content
  return (
    <div className="text-center py-8 text-gray-500">
      <p>Usa la route /admin/qrcode per la gestione completa dei QR code</p>
      <Button onClick={() => window.location.href = `${process.env.PUBLIC_URL || ''}/admin/qrcode`} className="mt-4">
        Vai a Gestione QR Code
      </Button>
    </div>
  );
};

export default AdminDashboard;