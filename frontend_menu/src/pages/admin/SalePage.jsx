import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Plus, Trash2, Pencil, Loader2, DoorOpen, DoorClosed, Banknote, Ban } from 'lucide-react';
import AdminPageHeader from '../../components/admin/AdminPageHeader';
import { useAdminAuth } from '../../hooks/useAdminAuth';
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from '../../components/ui/table';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Switch } from '../../components/ui/switch';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter
} from '../../components/ui/dialog';
import { toast } from '../../hooks/use-toast';

const BACKEND_URL = process.env.REACT_APP_MENU_BACKEND_URL;

const SalaDialog = ({ sala, onSaved, authHeader, trigger }) => {
  const isEdit = !!sala;
  const [open, setOpen] = useState(false);
  const [nome, setNome] = useState(sala?.nome || '');
  const [ordiniAbilitati, setOrdiniAbilitati] = useState(sala?.ordini_abilitati ?? true);
  const [copertoAttivo, setCopertoAttivo] = useState(sala?.coperto_attivo ?? false);
  const [copertoImporto, setCopertoImporto] = useState(sala?.coperto_importo?.toString() || '0');
  const [disabilitaContantiQr, setDisabilitaContantiQr] = useState(sala?.disabilita_contanti_qr ?? false);

  const submit = async () => {
    if (!nome.trim()) return;
    const payload = {
      nome,
      ordini_abilitati: ordiniAbilitati,
      coperto_attivo: copertoAttivo,
      coperto_importo: parseFloat(copertoImporto) || 0,
      disabilita_contanti_qr: disabilitaContantiQr,
    };
    try {
      if (isEdit) {
        await axios.put(`${BACKEND_URL}/api/sale/${sala.id}`, payload, { headers: authHeader });
      } else {
        await axios.post(`${BACKEND_URL}/api/sale/`, payload, { headers: authHeader });
      }
      setOpen(false);
      if (!isEdit) { setNome(''); setOrdiniAbilitati(true); setCopertoAttivo(false); setCopertoImporto('0'); setDisabilitaContantiQr(false); }
      onSaved();
    } catch {
      toast({ title: 'Errore', description: 'Salvataggio non riuscito', variant: 'destructive' });
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger || (
          <Button className="bg-[#4a5d4a] hover:bg-[#3d4d3d]">
            <Plus className="w-4 h-4 mr-2" /> Nuova sala
          </Button>
        )}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? `Modifica sala — ${sala.nome}` : 'Nuova sala'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <Label>Nome sala</Label>
            <Input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="es. Interno, Dehor, Terrazza..." />
            <p className="text-xs text-gray-500 mt-1">Ogni sala rappresenta un ambiente reale del locale (Sala 1, Dehor, Terrazza, ecc.).</p>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <Label>Abilita ordini</Label>
              <p className="text-xs text-gray-500">Se disattivo, i clienti/lo staff non possono creare ordini per questa sala.</p>
            </div>
            <Switch checked={ordiniAbilitati} onCheckedChange={setOrdiniAbilitati} />
          </div>
          <div className="flex items-center justify-between">
            <div>
              <Label>Coperto</Label>
              <p className="text-xs text-gray-500">Aggiunge automaticamente un importo per persona agli ordini di questa sala.</p>
            </div>
            <Switch checked={copertoAttivo} onCheckedChange={setCopertoAttivo} />
          </div>
          {copertoAttivo && (
            <div>
              <Label>Importo coperto (€ a persona)</Label>
              <Input type="number" step="0.1" min="0" value={copertoImporto} onChange={(e) => setCopertoImporto(e.target.value)} />
            </div>
          )}
          <div className="flex items-center justify-between">
            <div>
              <Label>Disabilita contanti per ordini QR</Label>
              <p className="text-xs text-gray-500">I clienti che ordinano dal menu digitale per questa sala non potranno scegliere di pagare in contanti.</p>
            </div>
            <Switch checked={disabilitaContantiQr} onCheckedChange={setDisabilitaContantiQr} />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={submit} className="bg-[#4a5d4a] hover:bg-[#3d4d3d]">Salva</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const SalePage = () => {
  const { checking, authorized, authHeader } = useAdminAuth();
  const [sale, setSale] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadSale = useCallback(async () => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/sale/`, { headers: authHeader });
      setSale(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [authHeader.Authorization]);

  useEffect(() => {
    if (authorized) loadSale();
  }, [authorized, loadSale]);

  const handleDelete = async (id, nome) => {
    if (!window.confirm(`Eliminare la sala "${nome}"?`)) return;
    try {
      await axios.delete(`${BACKEND_URL}/api/sale/${id}`, { headers: authHeader });
      loadSale();
    } catch {
      toast({ title: 'Errore', description: 'Eliminazione non riuscita', variant: 'destructive' });
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
      <AdminPageHeader title="Sale" subtitle="Gestisci le sale del locale, ordini e coperto" />
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="bg-white rounded-lg shadow p-4">
          <div className="flex justify-between items-center mb-4">
            <h2 className="font-bold">Sale ({sale.length})</h2>
            <SalaDialog onSaved={loadSale} authHeader={authHeader} />
          </div>
          {loading ? (
            <Loader2 className="w-6 h-6 animate-spin text-[#4a5d4a]" />
          ) : sale.length === 0 ? (
            <p className="text-gray-400 text-sm py-6 text-center">Nessuna sala configurata. Aggiungine una per iniziare.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Ordini</TableHead>
                  <TableHead>Coperto</TableHead>
                  <TableHead>Contanti QR</TableHead>
                  <TableHead className="text-right">Azioni</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sale.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell className="font-medium">{s.nome}</TableCell>
                    <TableCell>
                      {s.ordini_abilitati ? (
                        <span className="inline-flex items-center gap-1 text-emerald-700 text-sm"><DoorOpen className="w-4 h-4" /> Abilitati</span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-gray-400 text-sm"><DoorClosed className="w-4 h-4" /> Disabilitati</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {s.coperto_attivo ? `€ ${Number(s.coperto_importo).toFixed(2)} a persona` : '—'}
                    </TableCell>
                    <TableCell>
                      {s.disabilita_contanti_qr ? (
                        <span className="inline-flex items-center gap-1 text-amber-700 text-sm"><Ban className="w-4 h-4" /> Bloccati</span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-gray-400 text-sm"><Banknote className="w-4 h-4" /> Consentiti</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end items-center gap-1">
                        <SalaDialog
                          sala={s}
                          onSaved={loadSale}
                          authHeader={authHeader}
                          trigger={<Button size="icon" variant="ghost"><Pencil className="w-4 h-4" /></Button>}
                        />
                        <Button size="icon" variant="ghost" onClick={() => handleDelete(s.id, s.nome)}>
                          <Trash2 className="w-4 h-4 text-red-500" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </div>
    </div>
  );
};

export default SalePage;
