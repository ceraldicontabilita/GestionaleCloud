import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { QRCodeSVG } from 'qrcode.react';
import { Download, ExternalLink, Link2, Pencil, QrCode, AlertTriangle } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { toast } from '../../hooks/use-toast';

const BACKEND_URL = process.env.REACT_APP_MENU_BACKEND_URL;

/**
 * Indirizzo pubblico del menu clienti e il suo QR code, nella dashboard.
 *
 * Una sola fonte: `menu_qrcode_config.menu_url` (GET/PUT `/api/qrcode/menu-url`),
 * l'indirizzo che l'amministratore ha scelto e che sta stampato sui tavoli.
 * Il QR si ricava da quel valore e da nient'altro: prima la pagina lo
 * costruiva dal dominio da cui si apriva l'amministrazione, e lo stesso locale
 * poteva stampare QR diversi a seconda di dove era entrato.
 */
const MenuClientiQR = () => {
  const [stato, setStato] = useState('caricamento'); // caricamento | pronto | errore
  const [menuUrl, setMenuUrl] = useState(null);
  const [modifica, setModifica] = useState(false);
  const [bozza, setBozza] = useState('');
  const [salvataggio, setSalvataggio] = useState(false);

  useEffect(() => {
    let vivo = true;
    axios.get(`${BACKEND_URL}/api/qrcode/menu-url`)
      .then((res) => {
        if (!vivo) return;
        setMenuUrl(res.data?.url || null);
        setStato('pronto');
      })
      .catch(() => { if (vivo) setStato('errore'); });
    return () => { vivo = false; };
  }, []);

  const salva = async () => {
    setSalvataggio(true);
    try {
      const token = localStorage.getItem('admin_token');
      const res = await axios.put(
        `${BACKEND_URL}/api/qrcode/menu-url`,
        { url: bozza },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setMenuUrl(res.data.url);
      setModifica(false);
      toast({ title: 'Indirizzo salvato', description: res.data.url });
    } catch (err) {
      const dettaglio = err?.response?.data?.detail;
      toast({
        title: 'Indirizzo non salvato',
        description: typeof dettaglio === 'string' ? dettaglio : 'Riprova tra poco.',
        variant: 'destructive',
      });
    } finally {
      setSalvataggio(false);
    }
  };

  const scaricaQR = () => {
    const svg = document.querySelector('#qr-menu-clienti svg');
    if (!svg) return;
    const blob = new Blob([new XMLSerializer().serializeToString(svg)], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'ceraldi-menu-clienti-qr.svg';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="bg-white rounded-lg shadow p-4 sm:p-6 border border-[#e6e0d4]" aria-labelledby="titolo-menu-clienti" data-testid="menu-clienti-qr">
      <h2 id="titolo-menu-clienti" className="text-xl font-bold mb-1 flex items-center gap-2">
        <QrCode className="w-6 h-6 text-[#3f5a4e]" aria-hidden="true" />
        Menu clienti
      </h2>
      <p className="text-sm text-gray-600 mb-4">L'indirizzo che si apre sul telefono del cliente e il QR da stampare sui tavoli.</p>

      {stato === 'caricamento' && <p className="text-sm text-gray-600">Caricamento…</p>}
      {stato === 'errore' && (
        <p className="text-sm text-[#d35f4e] flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" aria-hidden="true" />
          Indirizzo del menu non leggibile: riprova a ricaricare la pagina.
        </p>
      )}

      {stato === 'pronto' && (
        <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-6 items-start">
          <div className="space-y-3 min-w-0">
            {menuUrl ? (
              <div className="rounded-lg border border-[#e6e0d4] bg-[#faf7f0] p-3 flex gap-2 items-start">
                <Link2 className="w-5 h-5 shrink-0 text-[#3f5a4e]" aria-hidden="true" />
                <a href={menuUrl} target="_blank" rel="noopener noreferrer" className="text-[#3f5a4e] underline font-semibold break-all" data-testid="menu-url-pubblico">
                  {menuUrl}
                </a>
              </div>
            ) : (
              <p className="rounded-lg border border-[#c4894a] bg-[#faf7f0] p-3 text-sm flex gap-2">
                <AlertTriangle className="w-5 h-5 shrink-0 text-[#c4894a]" aria-hidden="true" />
                Indirizzo pubblico non ancora scelto: senza, il QR non si genera.
              </p>
            )}

            {modifica ? (
              <div className="space-y-2">
                <label className="block text-sm font-medium">
                  Indirizzo pubblico (https://…/menu/)
                  <Input
                    value={bozza}
                    onChange={(e) => setBozza(e.target.value)}
                    placeholder="https://dominio/menu/"
                    className="mt-1"
                    inputMode="url"
                  />
                </label>
                <div className="flex flex-wrap gap-2">
                  <Button onClick={salva} disabled={salvataggio || !bozza.trim()} className="min-h-[44px]">
                    {salvataggio ? 'Salvataggio…' : 'Salva indirizzo'}
                  </Button>
                  <Button variant="outline" onClick={() => setModifica(false)} className="min-h-[44px]">Annulla</Button>
                </div>
              </div>
            ) : (
              <div className="flex flex-wrap gap-2">
                {menuUrl && (
                  <Button asChild className="min-h-[44px]">
                    <a href={menuUrl} target="_blank" rel="noopener noreferrer">
                      <ExternalLink className="w-4 h-4 mr-2" aria-hidden="true" />Apri menu clienti
                    </a>
                  </Button>
                )}
                <Button variant="outline" onClick={() => { setBozza(menuUrl || ''); setModifica(true); }} className="min-h-[44px]">
                  <Pencil className="w-4 h-4 mr-2" aria-hidden="true" />Cambia indirizzo
                </Button>
              </div>
            )}
          </div>

          {menuUrl && (
            <div className="flex flex-col items-center gap-2">
              <div id="qr-menu-clienti" className="p-3 bg-white rounded-lg border-2 border-[#e6e0d4]">
                <QRCodeSVG value={menuUrl} size={180} level="H" title={`QR code: ${menuUrl}`} />
              </div>
              <Button variant="outline" onClick={scaricaQR} className="min-h-[44px] w-full">
                <Download className="w-4 h-4 mr-2" aria-hidden="true" />Scarica QR
              </Button>
            </div>
          )}
        </div>
      )}
    </section>
  );
};

export default MenuClientiQR;
