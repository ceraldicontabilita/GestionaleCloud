import React, { useMemo } from 'react';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { QRCodeSVG } from 'qrcode.react';
import { CheckCircle2, Download, ExternalLink, Info, Link2, QrCode } from 'lucide-react';
import AdminPageHeader from '../components/admin/AdminPageHeader';
import useAdminAuth from '../hooks/useAdminAuth';

const AdminQRCodePage = () => {
  const { checking, authorized } = useAdminAuth();
  const menuUrl = useMemo(() => {
    const path = (process.env.PUBLIC_URL || '/menu').replace(/\/$/, '');
    return `${window.location.origin}${path}/`;
  }, []);

  const downloadQR = () => {
    const svg = document.querySelector('#qr-menu svg');
    if (!svg) return;
    const blob = new Blob([new XMLSerializer().serializeToString(svg)], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'ceraldi-menu-clienti-qr.svg';
    a.click();
    URL.revokeObjectURL(url);
  };

  if (checking || !authorized) {
    return <div className="min-h-screen flex items-center justify-center bg-gray-50">Caricamento…</div>;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <AdminPageHeader title="Menu clienti e QR Code" subtitle="Ceraldi Caffè Admin Panel" />
      <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-3"><QrCode className="w-8 h-8" />Menu QR Code</h1>
          <span className="rounded-full bg-green-100 px-3 py-1 text-xs font-bold text-green-800">CENTRALIZZATO</span>
        </div>

        <Card className="border-green-200 bg-green-50/60">
          <CardHeader>
            <CardTitle className="text-green-800 flex items-center gap-2"><CheckCircle2 className="w-7 h-7" />Gestione unificata</CardTitle>
            <CardDescription>Un solo QR per il menu clienti, senza configurazione Wi‑Fi duplicata.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 flex gap-3">
              <Info className="w-6 h-6 text-blue-700 shrink-0" />
              <p className="text-sm text-blue-900">L'indirizzo viene ricavato automaticamente dal dominio reale del sistema. Quando il servizio passerà da Render a Personal Cloud, questa pagina userà automaticamente il nuovo dominio.</p>
            </div>
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Menu online attuale</CardTitle>
              <CardDescription>È l'indirizzo che deve aprirsi sul telefono del cliente.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-xl border bg-white p-4 flex gap-3"><Link2 className="w-5 h-5 shrink-0" /><a href={menuUrl} target="_blank" rel="noreferrer" className="text-blue-700 underline font-semibold break-all">{menuUrl}</a></div>
              <Button onClick={() => window.open(menuUrl, '_blank')} className="w-full"><ExternalLink className="w-4 h-4 mr-2" />Apri menu clienti</Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>QR Code menu clienti</CardTitle><CardDescription>Contiene esattamente l'indirizzo mostrato a sinistra.</CardDescription></CardHeader>
            <CardContent className="space-y-4">
              <div id="qr-menu" className="flex justify-center p-6 bg-white rounded-xl border-2"><QRCodeSVG value={menuUrl} size={240} level="H" /></div>
              <Button onClick={downloadQR} variant="outline" className="w-full"><Download className="w-4 h-4 mr-2" />Scarica QR Code</Button>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader><CardTitle>Origine dei dati</CardTitle></CardHeader>
          <CardContent className="text-sm text-gray-700 space-y-2">
            <p><strong>Prodotti e categorie:</strong> dal sistema Menu/Lotti già esistente.</p>
            <p><strong>Indirizzo pubblico:</strong> dominio corrente + <code>/menu/</code>.</p>
            <p><strong>Wi‑Fi:</strong> eliminato da questa pagina perché duplicato.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default AdminQRCodePage;
