import React, { useCallback, useEffect, useState } from 'react';
import { Ban, Banknote, DoorClosed, DoorOpen, Loader2, Pencil, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { aggiornaSala, creaSala, elencoSale, eliminaSala, euro, messaggioErrore, puoGestire } from '../api';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Switch } from '../ui/switch';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '../ui/dialog';

const SalaDialog = ({ sala, onSaved, trigger }) => {
  const isEdit = !!sala;
  const [open, setOpen] = useState(false);
  const [nome, setNome] = useState(sala?.nome || '');
  const [ordiniAbilitati, setOrdiniAbilitati] = useState(sala?.ordini_abilitati ?? true);
  const [copertoAttivo, setCopertoAttivo] = useState(sala?.coperto_attivo ?? false);
  const [copertoImporto, setCopertoImporto] = useState(sala?.coperto_importo?.toString() || '0');
  const [disabilitaContantiQr, setDisabilitaContantiQr] = useState(sala?.disabilita_contanti_qr ?? false);

  const submit = async () => {
    if (!nome.trim()) return;
    const payload = { nome, ordini_abilitati: ordiniAbilitati, coperto_attivo: copertoAttivo, coperto_importo: parseFloat(copertoImporto) || 0, disabilita_contanti_qr: disabilitaContantiQr };
    try {
      if (isEdit) await aggiornaSala(sala.id, payload); else await creaSala(payload);
      setOpen(false);
      if (!isEdit) { setNome(''); setOrdiniAbilitati(true); setCopertoAttivo(false); setCopertoImporto('0'); setDisabilitaContantiQr(false); }
      onSaved();
    } catch (err) { toast.error('Errore', { description: messaggioErrore(err, 'Salvataggio non riuscito') }); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger || <Button className="bg-[#5b7a6b] hover:bg-[#3f5a4e] text-white"><Plus className="w-4 h-4 mr-2" /> Nuova sala</Button>}</DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>{isEdit ? `Modifica sala — ${sala.nome}` : 'Nuova sala'}</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div>
            <Label>Nome sala</Label>
            <Input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="es. Interno, Dehor, Terrazza..." />
            <p className="text-xs text-gray-500 mt-1">Ogni sala rappresenta un ambiente reale del locale.</p>
          </div>
          <div className="flex items-center justify-between gap-4">
            <div><Label>Abilita ordini</Label><p className="text-xs text-gray-500">Se disattivo, clienti e staff non possono creare ordini per questa sala.</p></div>
            <Switch checked={ordiniAbilitati} onCheckedChange={setOrdiniAbilitati} />
          </div>
          <div className="flex items-center justify-between gap-4">
            <div><Label>Coperto</Label><p className="text-xs text-gray-500">Aggiunge un importo per persona agli ordini di questa sala.</p></div>
            <Switch checked={copertoAttivo} onCheckedChange={setCopertoAttivo} />
          </div>
          {copertoAttivo && <div><Label>Importo coperto (€ a persona)</Label><Input type="number" step="0.1" min="0" value={copertoImporto} onChange={(e) => setCopertoImporto(e.target.value)} /></div>}
          <div className="flex items-center justify-between gap-4">
            <div><Label>Disabilita contanti per ordini QR</Label><p className="text-xs text-gray-500">I clienti che ordinano dal menu digitale non potranno pagare in contanti.</p></div>
            <Switch checked={disabilitaContantiQr} onCheckedChange={setDisabilitaContantiQr} />
          </div>
        </div>
        <DialogFooter><Button onClick={submit} className="bg-[#5b7a6b] hover:bg-[#3f5a4e] text-white">Salva</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default function Sale({ ruolo }) {
  const [sale, setSale] = useState([]);
  const [loading, setLoading] = useState(true);
  const gestione = puoGestire(ruolo);

  const load = useCallback(async () => {
    try { setSale(await elencoSale()); } catch (err) { console.error(err); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const handleDelete = async (id, nome) => {
    if (!window.confirm(`Eliminare la sala "${nome}"?`)) return;
    try { await eliminaSala(id); load(); } catch (err) { toast.error('Errore', { description: messaggioErrore(err, 'Eliminazione non riuscita') }); }
  };

  return (
    <div>
      <h2 className="text-xl font-bold text-[#2a3329] mb-1">Sale</h2>
      <p className="text-sm text-gray-500 mb-4">Sale del locale, ordini e coperto</p>
      <div className="bg-white rounded-lg shadow p-4 border border-[#e6e0d4]">
        <div className="flex justify-between items-center mb-4">
          <h3 className="font-bold">Sale ({sale.length})</h3>
          {gestione && <SalaDialog onSaved={load} />}
        </div>
        {loading ? <Loader2 className="w-6 h-6 animate-spin text-[#5b7a6b]" /> : sale.length === 0 ? (
          <p className="text-gray-400 text-sm py-6 text-center">Nessuna sala configurata.</p>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow><TableHead>Nome</TableHead><TableHead>Ordini</TableHead><TableHead>Coperto</TableHead><TableHead>Contanti QR</TableHead>{gestione && <TableHead className="text-right">Azioni</TableHead>}</TableRow></TableHeader>
              <TableBody>
                {sale.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell className="font-medium">{s.nome}</TableCell>
                    <TableCell>{s.ordini_abilitati ? <span className="inline-flex items-center gap-1 text-emerald-700 text-sm"><DoorOpen className="w-4 h-4" /> Abilitati</span> : <span className="inline-flex items-center gap-1 text-gray-400 text-sm"><DoorClosed className="w-4 h-4" /> Disabilitati</span>}</TableCell>
                    <TableCell>{s.coperto_attivo ? `${euro(s.coperto_importo)} a persona` : '—'}</TableCell>
                    <TableCell>{s.disabilita_contanti_qr ? <span className="inline-flex items-center gap-1 text-amber-700 text-sm"><Ban className="w-4 h-4" /> Bloccati</span> : <span className="inline-flex items-center gap-1 text-gray-400 text-sm"><Banknote className="w-4 h-4" /> Consentiti</span>}</TableCell>
                    {gestione && (
                      <TableCell className="text-right">
                        <div className="flex justify-end items-center gap-1">
                          <SalaDialog sala={s} onSaved={load} trigger={<Button size="icon" variant="ghost"><Pencil className="w-4 h-4" /></Button>} />
                          <Button size="icon" variant="ghost" onClick={() => handleDelete(s.id, s.nome)}><Trash2 className="w-4 h-4 text-[#d35f4e]" /></Button>
                        </div>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
  );
}
