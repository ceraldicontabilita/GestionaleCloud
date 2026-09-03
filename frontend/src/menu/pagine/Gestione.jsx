/**
 * Gestione del menu (admin/operatore): catalogo (categorie, sottocategorie,
 * prodotti con allergeni e immagine), immagini caricate, QR code menu/WiFi,
 * backup JSON e migrazione dal vecchio Supabase dell'app Menu (solo admin).
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import {
  Database, Download, Edit, FolderPlus, Image as ImageIcon, Loader2, Plus, QrCode, RefreshCw, Save, Search,
  Trash2, Upload, Wifi, X,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  aggiornaCategoria, aggiornaProdotto, aggiornaSottocategoria, avviaMigrazione, caricaImmagine, caricaMenu, configQr,
  creaCategoria, creaProdotto, creaSottocategoria, eAdmin, elencoImmagini, eliminaCategoria, eliminaImmagine,
  eliminaProdotto, eliminaSottocategoria, esportaBackup, messaggioErrore, prodottiPiatti, ripristinaBackup,
  salvaConfigQr, statoDati, statoMigrazione,
} from '../api';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog';

const dimensione = (bytes) => (bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`);
const dataOra = (iso) => (iso ? new Date(iso).toLocaleString('it-IT', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—');
const BTN = 'bg-[#5b7a6b] hover:bg-[#3f5a4e] text-white';

/* ------------------------------------------------------------------ selettore immagine */
function SelettoreImmagine({ value, onChange, immagini }) {
  return (
    <div className="space-y-2">
      <Label>Immagine</Label>
      <div className="flex gap-2 items-start">
        {value && <img src={value} alt="" className="w-16 h-16 object-cover rounded border border-[#e6e0d4]" />}
        <div className="flex-1 space-y-2">
          <Select value={value || '__nessuna__'} onValueChange={(v) => onChange(v === '__nessuna__' ? null : v)}>
            <SelectTrigger><SelectValue placeholder="Scegli tra le immagini caricate" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__nessuna__">Nessuna immagine</SelectItem>
              {immagini.map((img) => <SelectItem key={img.id} value={img.url}>{img.filename}</SelectItem>)}
              {value && !immagini.some((i) => i.url === value) && <SelectItem value={value}>{value}</SelectItem>}
            </SelectContent>
          </Select>
          <Input value={value || ''} onChange={(e) => onChange(e.target.value || null)} placeholder="oppure incolla un indirizzo https://..." />
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ prodotti */
function Prodotti({ immagini }) {
  const [prodotti, setProdotti] = useState([]);
  const [albero, setAlbero] = useState([]);
  const [allergeni, setAllergeni] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState(null);
  const [nuovo, setNuovo] = useState(null);
  const [salvando, setSalvando] = useState(false);

  const load = useCallback(async () => {
    try {
      const [piatti, menu] = await Promise.all([prodottiPiatti(), caricaMenu()]);
      setProdotti(piatti.products); setAlbero(menu.categories); setAllergeni(menu.allergens);
    } catch (err) { toast.error('Errore', { description: messaggioErrore(err, 'Catalogo non caricato') }); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const sottocategorie = useMemo(() => albero.flatMap((c) => (c.subcategories || []).map((s) => ({ ...s, categoria: c.nameIT }))), [albero]);
  const filtrati = useMemo(() => {
    const q = search.toLowerCase();
    return prodotti.filter((p) => [p.nameIT, p.name, p.price, p.categoryName, p.subcategoryName].some((v) => String(v || '').toLowerCase().includes(q)));
  }, [prodotti, search]);

  const toggleAllergene = (obj, setObj, id) => setObj({ ...obj, allergens: (obj.allergens || []).includes(id) ? obj.allergens.filter((a) => a !== id) : [...(obj.allergens || []), id] });

  const salvaModifica = async () => {
    setSalvando(true);
    try {
      const { id, subcategory_id, nameIT, name, price, description, descriptionIT, allergens, image } = editing;
      await aggiornaProdotto(id, { nameIT, name, price, description: description || '', descriptionIT: descriptionIT || '', allergens: allergens || [], image: image || '' }, subcategory_id);
      toast.success('Prodotto aggiornato', { description: nameIT });
      setEditing(null); load();
    } catch (err) { toast.error('Errore', { description: messaggioErrore(err, 'Salvataggio non riuscito') }); } finally { setSalvando(false); }
  };
  const salvaNuovo = async () => {
    if (!nuovo.nameIT?.trim() || !nuovo.price?.trim() || !nuovo.subcategory_id) { toast.error('Compila nome, prezzo e sottocategoria'); return; }
    setSalvando(true);
    try {
      const sotto = sottocategorie.find((s) => String(s.id) === String(nuovo.subcategory_id));
      await creaProdotto({ ...nuovo, name: nuovo.name || nuovo.nameIT, allergens: nuovo.allergens || [], category_id: sotto.category_id, subcategory_id: sotto.id });
      toast.success('Prodotto creato', { description: nuovo.nameIT });
      setNuovo(null); load();
    } catch (err) { toast.error('Errore', { description: messaggioErrore(err, 'Creazione non riuscita') }); } finally { setSalvando(false); }
  };
  const elimina = async (p) => {
    if (!window.confirm(`Eliminare "${p.nameIT}" dal menu?`)) return;
    try { await eliminaProdotto(p.id); load(); } catch (err) { toast.error('Errore', { description: messaggioErrore(err, 'Eliminazione non riuscita') }); }
  };

  const FormProdotto = ({ obj, setObj, nuovoProdotto }) => (
    <div className="space-y-4 mt-2">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="space-y-2"><Label>Nome italiano</Label><Input value={obj.nameIT || ''} onChange={(e) => setObj({ ...obj, nameIT: e.target.value })} /></div>
        <div className="space-y-2"><Label>Nome inglese</Label><Input value={obj.name || ''} onChange={(e) => setObj({ ...obj, name: e.target.value })} /></div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="space-y-2"><Label>Prezzo (es. 3.50€)</Label><Input value={obj.price || ''} onChange={(e) => setObj({ ...obj, price: e.target.value })} /></div>
        <div className="space-y-2">
          <Label>Sottocategoria</Label>
          <Select value={obj.subcategory_id ? String(obj.subcategory_id) : ''} onValueChange={(v) => setObj({ ...obj, subcategory_id: Number(v) })}>
            <SelectTrigger><SelectValue placeholder="Scegli" /></SelectTrigger>
            <SelectContent>{sottocategorie.map((s) => <SelectItem key={s.id} value={String(s.id)}>{s.categoria} → {s.nameIT}</SelectItem>)}</SelectContent>
          </Select>
        </div>
      </div>
      <div className="space-y-2"><Label>Descrizione italiana</Label><Textarea rows={2} value={obj.descriptionIT || ''} onChange={(e) => setObj({ ...obj, descriptionIT: e.target.value })} /></div>
      <div className="space-y-2"><Label>Descrizione inglese</Label><Textarea rows={2} value={obj.description || ''} onChange={(e) => setObj({ ...obj, description: e.target.value })} /></div>
      <SelettoreImmagine value={obj.image} onChange={(v) => setObj({ ...obj, image: v })} immagini={immagini} />
      <div className="space-y-2">
        <Label>Allergeni</Label>
        <div className="flex flex-wrap gap-2 p-3 border border-[#e6e0d4] rounded-lg">
          {allergeni.map((a) => (
            <button key={a.id} type="button" onClick={() => toggleAllergene(obj, setObj, a.id)} className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${(obj.allergens || []).includes(a.id) ? 'bg-[#d4af37] text-black' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}>
              {a.icon} {a.nameIT}
            </button>
          ))}
        </div>
      </div>
      <div className="flex gap-2 pt-2">
        <Button onClick={nuovoProdotto ? salvaNuovo : salvaModifica} disabled={salvando} className={`flex-1 ${BTN}`}><Save className="w-4 h-4 mr-2" /> {salvando ? 'Salvataggio...' : 'Salva'}</Button>
        <Button onClick={() => (nuovoProdotto ? setNuovo(null) : setEditing(null))} variant="outline"><X className="w-4 h-4 mr-2" /> Annulla</Button>
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="pt-6 flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-3 h-4 w-4 text-gray-400" />
            <Input placeholder="Cerca per nome, prezzo, categoria..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-10" />
          </div>
          <Button onClick={() => setNuovo({ allergens: [], subcategory_id: sottocategorie[0]?.id })} className={BTN} disabled={sottocategorie.length === 0}><Plus className="w-4 h-4 mr-2" /> Nuovo prodotto</Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Prodotti ({filtrati.length})</CardTitle></CardHeader>
        <CardContent>
          {loading ? <Loader2 className="w-6 h-6 animate-spin text-[#5b7a6b]" /> : (
            <div className="space-y-2 max-h-[600px] overflow-y-auto">
              {filtrati.map((p) => (
                <div key={p.id} className="flex items-center justify-between p-3 border border-[#e6e0d4] rounded-lg hover:bg-[#faf7f0] transition-colors gap-3">
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    {p.image && <img src={p.image} alt={p.nameIT} className="w-14 h-14 object-cover rounded" />}
                    <div className="min-w-0">
                      <h4 className="font-semibold text-gray-900 truncate">{p.nameIT}</h4>
                      <p className="text-sm text-gray-500 truncate">{p.name}</p>
                      <div className="flex items-center gap-3 mt-1 flex-wrap">
                        <span className="text-sm font-medium text-[#8a6f47]">{p.price}</span>
                        <span className="text-xs text-gray-400">{p.categoryName} → {p.subcategoryName}</span>
                      </div>
                      {(p.allergens || []).length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {p.allergens.map((id) => { const a = allergeni.find((x) => x.id === id); return a ? <span key={id} className="text-xs bg-orange-100 text-orange-800 px-2 py-0.5 rounded">{a.icon} {a.nameIT}</span> : null; })}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-1">
                    <Button size="sm" variant="outline" onClick={() => setEditing({ ...p })}><Edit className="w-4 h-4" /></Button>
                    <Button size="sm" variant="outline" onClick={() => elimina(p)}><Trash2 className="w-4 h-4 text-[#d35f4e]" /></Button>
                  </div>
                </div>
              ))}
              {!loading && filtrati.length === 0 && <p className="text-center text-gray-400 py-8">Nessun prodotto{prodotti.length === 0 ? ': crea prima categorie e sottocategorie, oppure importa i dati dal vecchio menu (scheda Backup)' : ' trovato'}.</p>}
            </div>
          )}
        </CardContent>
      </Card>

      <Categorie albero={albero} immagini={immagini} onChange={load} />

      <Dialog open={!!editing} onOpenChange={() => setEditing(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Modifica prodotto</DialogTitle></DialogHeader>
          {editing && <FormProdotto obj={editing} setObj={setEditing} />}
        </DialogContent>
      </Dialog>
      <Dialog open={!!nuovo} onOpenChange={() => setNuovo(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Nuovo prodotto</DialogTitle></DialogHeader>
          {nuovo && <FormProdotto obj={nuovo} setObj={setNuovo} nuovoProdotto />}
        </DialogContent>
      </Dialog>
    </div>
  );
}

/* ------------------------------------------------------------------ categorie e sottocategorie */
function Categorie({ albero, immagini, onChange }) {
  const [form, setForm] = useState(null); // {tipo:'categoria'|'sottocategoria', id?, name, nameIT, image, category_id}
  const [salvando, setSalvando] = useState(false);

  const salva = async () => {
    if (!form.nameIT?.trim()) { toast.error('Inserisci il nome italiano'); return; }
    setSalvando(true);
    const body = { name: form.name || form.nameIT, nameIT: form.nameIT, image: form.image || '' };
    try {
      if (form.tipo === 'categoria') form.id ? await aggiornaCategoria(form.id, body) : await creaCategoria(body);
      else form.id ? await aggiornaSottocategoria(form.id, body) : await creaSottocategoria({ ...body, category_id: form.category_id });
      toast.success('Salvato'); setForm(null); onChange();
    } catch (err) { toast.error('Errore', { description: messaggioErrore(err, 'Salvataggio non riuscito') }); } finally { setSalvando(false); }
  };
  const elimina = async (tipo, item) => {
    const cosa = tipo === 'categoria' ? 'la categoria e TUTTE le sue sottocategorie e prodotti' : 'la sottocategoria e TUTTI i suoi prodotti';
    if (!window.confirm(`Eliminare ${cosa} "${item.nameIT}"?`)) return;
    try { tipo === 'categoria' ? await eliminaCategoria(item.id) : await eliminaSottocategoria(item.id); onChange(); }
    catch (err) { toast.error('Errore', { description: messaggioErrore(err, 'Eliminazione non riuscita') }); }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Categorie e sottocategorie</span>
          <Button size="sm" onClick={() => setForm({ tipo: 'categoria', name: '', nameIT: '', image: null })} className={BTN}><FolderPlus className="w-4 h-4 mr-2" /> Nuova categoria</Button>
        </CardTitle>
        <CardDescription>La struttura che il cliente vede nel menu: categoria → sottocategoria → prodotti.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {albero.length === 0 && <p className="text-gray-400 text-sm">Nessuna categoria.</p>}
        {albero.map((c) => (
          <div key={c.id} className="border border-[#e6e0d4] rounded-lg p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-3 min-w-0">
                {c.image && <img src={c.image} alt="" className="w-10 h-10 object-cover rounded" />}
                <div className="min-w-0"><p className="font-semibold truncate">{c.nameIT}</p><p className="text-xs text-gray-500 truncate">{c.name}</p></div>
              </div>
              <div className="flex gap-1 flex-shrink-0">
                <Button size="sm" variant="outline" onClick={() => setForm({ tipo: 'sottocategoria', category_id: c.id, name: '', nameIT: '', image: null })}><Plus className="w-4 h-4" /></Button>
                <Button size="sm" variant="outline" onClick={() => setForm({ tipo: 'categoria', ...c })}><Edit className="w-4 h-4" /></Button>
                <Button size="sm" variant="outline" onClick={() => elimina('categoria', c)}><Trash2 className="w-4 h-4 text-[#d35f4e]" /></Button>
              </div>
            </div>
            <div className="mt-2 pl-4 space-y-1">
              {(c.subcategories || []).map((s) => (
                <div key={s.id} className="flex items-center justify-between gap-2 text-sm py-1 border-t border-[#f0ebe0]">
                  <span className="truncate">{s.nameIT} <span className="text-gray-400">({(s.items || []).length} prodotti)</span></span>
                  <div className="flex gap-1 flex-shrink-0">
                    <Button size="sm" variant="ghost" onClick={() => setForm({ tipo: 'sottocategoria', ...s })}><Edit className="w-4 h-4" /></Button>
                    <Button size="sm" variant="ghost" onClick={() => elimina('sottocategoria', s)}><Trash2 className="w-4 h-4 text-[#d35f4e]" /></Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </CardContent>
      <Dialog open={!!form} onOpenChange={() => setForm(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{form?.id ? 'Modifica' : 'Nuova'} {form?.tipo}</DialogTitle></DialogHeader>
          {form && (
            <div className="space-y-3">
              <div className="space-y-2"><Label>Nome italiano</Label><Input value={form.nameIT || ''} onChange={(e) => setForm({ ...form, nameIT: e.target.value })} /></div>
              <div className="space-y-2"><Label>Nome inglese</Label><Input value={form.name || ''} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
              <SelettoreImmagine value={form.image} onChange={(v) => setForm({ ...form, image: v })} immagini={immagini} />
            </div>
          )}
          <DialogFooter><Button onClick={salva} disabled={salvando} className={BTN}>Salva</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

/* ------------------------------------------------------------------ immagini */
function Immagini({ immagini, ricarica, loading }) {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);

  const upload = async () => {
    if (!file) return;
    setUploading(true);
    try {
      const r = await caricaImmagine(file);
      toast.success('Immagine caricata', { description: `${r.filename} — pronta per prodotti e categorie` });
      setFile(null); document.getElementById('menu-file-input').value = ''; ricarica();
    } catch (err) { toast.error('Errore', { description: messaggioErrore(err, "Impossibile caricare l'immagine") }); } finally { setUploading(false); }
  };
  const elimina = async (img) => {
    if (!window.confirm(`Eliminare l'immagine "${img.filename}"? I prodotti che la usano resteranno senza foto.`)) return;
    try { await eliminaImmagine(img.id); ricarica(); } catch (err) { toast.error('Errore', { description: messaggioErrore(err, 'Eliminazione non riuscita') }); }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><Upload className="w-5 h-5" /> Carica nuova immagine</CardTitle><CardDescription>JPG, PNG, WEBP o GIF fino a 10 MB. Un file identico gia' presente non viene duplicato.</CardDescription></CardHeader>
        <CardContent className="space-y-4">
          <div className="border-2 border-dashed border-[#e6e0d4] rounded-lg p-8 text-center">
            <ImageIcon className="w-12 h-12 mx-auto text-gray-400 mb-4" />
            <input id="menu-file-input" type="file" accept="image/*" onChange={(e) => setFile(e.target.files?.[0] || null)} className="hidden" />
            <label htmlFor="menu-file-input" className="cursor-pointer text-[#5b7a6b] hover:text-[#3f5a4e] font-medium">Seleziona un'immagine</label>
            {file && <div className="mt-4 p-3 bg-[#faf7f0] rounded-lg"><p className="font-medium text-gray-900">{file.name}</p><p className="text-sm text-gray-500">{dimensione(file.size)}</p></div>}
          </div>
          <Button onClick={upload} disabled={!file || uploading} className={`w-full ${BTN}`} size="lg">{uploading ? 'Caricamento...' : 'Carica immagine'}</Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="flex items-center justify-between"><span>Immagini caricate ({immagini.length})</span><Button variant="outline" size="sm" onClick={ricarica}><RefreshCw className="w-4 h-4 mr-2" /> Aggiorna</Button></CardTitle></CardHeader>
        <CardContent>
          {loading ? <div className="text-center py-8 text-gray-500">Caricamento...</div> : immagini.length === 0 ? (
            <div className="text-center py-8 text-gray-500"><ImageIcon className="w-12 h-12 mx-auto mb-2 text-gray-300" /><p>Nessuna immagine caricata</p></div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              {immagini.map((img) => (
                <div key={img.id} className="border border-[#e6e0d4] rounded-lg overflow-hidden group relative">
                  <div className="aspect-square bg-gray-100"><img src={img.url} alt={img.filename} className="w-full h-full object-cover" /></div>
                  <div className="p-2 bg-white"><p className="text-xs font-medium truncate" title={img.filename}>{img.filename}</p><p className="text-xs text-gray-500">{dimensione(img.size || 0)}</p></div>
                  <button onClick={() => elimina(img)} className="absolute top-2 right-2 bg-[#d35f4e] text-white rounded p-1.5 opacity-0 group-hover:opacity-100 transition-opacity" title="Elimina"><Trash2 className="w-4 h-4" /></button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ QR code */
function QrCodePannello() {
  const [menuUrl, setMenuUrl] = useState('');
  const [ssid, setSsid] = useState('');
  const [password, setPassword] = useState('');
  const [security, setSecurity] = useState('WPA');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    configQr().then((c) => {
      setMenuUrl(c.menu_url || `${window.location.origin}/menu`);
      setSsid(c.wifi?.ssid || ''); setPassword(c.wifi?.password || ''); setSecurity(c.wifi?.security || 'WPA');
    }).catch((err) => toast.error('Errore', { description: messaggioErrore(err, 'Configurazione non caricata') })).finally(() => setLoading(false));
  }, []);

  const salva = async () => {
    setSaving(true);
    try { await salvaConfigQr({ menu_url: menuUrl, wifi: { ssid, password, security, hidden: false } }); toast.success('Configurazione salvata'); }
    catch (err) { toast.error('Errore', { description: messaggioErrore(err, 'Salvataggio non riuscito') }); } finally { setSaving(false); }
  };
  const scarica = (id, nome) => {
    const svg = document.getElementById(id)?.querySelector('svg');
    if (!svg) return;
    const blob = new Blob([new XMLSerializer().serializeToString(svg)], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = `ceraldi_${nome}_qr.svg`; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  };
  const wifiString = `WIFI:T:${security};S:${ssid};P:${password};H:false;;`;

  if (loading) return <Loader2 className="w-6 h-6 animate-spin text-[#5b7a6b]" />;
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="space-y-6">
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><QrCode className="w-5 h-5" /> QR code del menu</CardTitle><CardDescription>Indirizzo codificato nel QR da stampare sui tavoli.</CardDescription></CardHeader>
          <CardContent className="space-y-2"><Label htmlFor="menuUrl">Indirizzo del menu</Label><Input id="menuUrl" type="url" value={menuUrl} onChange={(e) => setMenuUrl(e.target.value)} /></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><Wifi className="w-5 h-5" /> QR code WiFi</CardTitle><CardDescription>I clienti si collegano inquadrando il codice, senza digitare la password.</CardDescription></CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2"><Label htmlFor="ssid">Nome rete (SSID)</Label><Input id="ssid" value={ssid} onChange={(e) => setSsid(e.target.value)} /></div>
            <div className="space-y-2"><Label htmlFor="wifipwd">Password</Label><Input id="wifipwd" type="text" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
            <div className="space-y-2">
              <Label>Sicurezza</Label>
              <Select value={security} onValueChange={setSecurity}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="WPA">WPA/WPA2</SelectItem><SelectItem value="WEP">WEP</SelectItem><SelectItem value="nopass">Senza password</SelectItem></SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>
        <Button onClick={salva} disabled={saving} className={`w-full ${BTN}`} size="lg"><Save className="w-4 h-4 mr-2" /> {saving ? 'Salvataggio...' : 'Salva configurazione'}</Button>
      </div>
      <div className="space-y-6">
        <Card>
          <CardHeader><CardTitle>Anteprima QR menu</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div id="qr-menu" className="flex justify-center p-6 bg-white rounded-lg border-2 border-[#e6e0d4]"><QRCodeSVG value={menuUrl || ' '} size={224} level="H" /></div>
            <div className="flex gap-2">
              <Button onClick={() => scarica('qr-menu', 'menu')} variant="outline" className="flex-1"><Download className="w-4 h-4 mr-2" /> Scarica SVG</Button>
              <Button onClick={() => window.open(menuUrl, '_blank')} variant="outline" className="flex-1">Apri il menu</Button>
            </div>
            <p className="font-mono break-all text-xs text-gray-500 text-center">{menuUrl}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Anteprima QR WiFi</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div id="qr-wifi" className="flex justify-center p-6 bg-white rounded-lg border-2 border-[#e6e0d4]"><QRCodeSVG value={wifiString} size={224} level="H" /></div>
            <Button onClick={() => scarica('qr-wifi', 'wifi')} variant="outline" className="w-full"><Download className="w-4 h-4 mr-2" /> Scarica SVG</Button>
            <div className="bg-[#faf7f0] p-4 rounded-lg space-y-1 text-sm">
              <div className="flex justify-between"><span className="text-gray-600">Rete:</span><span className="font-semibold">{ssid || '—'}</span></div>
              <div className="flex justify-between"><span className="text-gray-600">Sicurezza:</span><span className="font-semibold">{security}</span></div>
              <div className="flex justify-between"><span className="text-gray-600">Password:</span><span className="font-mono">{'•'.repeat(password.length)}</span></div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ backup e migrazione */
function BackupPannello({ ruolo }) {
  const admin = eAdmin(ruolo);
  const [stato, setStato] = useState(null);
  const [esportando, setEsportando] = useState(false);
  const [ripristinando, setRipristinando] = useState(false);
  const [job, setJob] = useState(null);
  const [dryRun, setDryRun] = useState(true);

  const caricaStato = useCallback(() => statoDati().then(setStato).catch(() => {}), []);
  useEffect(() => { caricaStato(); }, [caricaStato]);

  useEffect(() => {
    if (!job || !['queued', 'running'].includes(job.status)) return undefined;
    const iv = setInterval(() => statoMigrazione(job.id).then(setJob).catch(() => {}), 2000);
    return () => clearInterval(iv);
  }, [job]);
  useEffect(() => { if (job && !['queued', 'running'].includes(job.status)) caricaStato(); }, [job, caricaStato]);

  const esporta = async () => {
    setEsportando(true);
    try {
      const dati = await esportaBackup();
      const blob = new Blob([JSON.stringify(dati)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = `menu_backup_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.json`; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
      toast.success('Backup scaricato');
    } catch (err) { toast.error('Errore', { description: messaggioErrore(err, 'Esportazione non riuscita') }); } finally { setEsportando(false); }
  };
  const ripristina = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (!window.confirm(`ATTENZIONE: ripristinare il menu dal file "${file.name}"?\n\nCategorie, prodotti, sale, ordini e immagini attuali verranno sostituiti.`)) return;
    setRipristinando(true);
    try {
      const json = JSON.parse(await file.text());
      const r = await ripristinaBackup(json);
      toast.success('Menu ripristinato', { description: Object.entries(r.ripristinato || {}).map(([k, v]) => `${k}: ${v}`).join(', ') });
      caricaStato();
    } catch (err) { toast.error('Errore', { description: err instanceof SyntaxError ? 'File non valido' : messaggioErrore(err, 'Ripristino non riuscito') }); } finally { setRipristinando(false); }
  };
  const migra = async () => {
    if (!dryRun && !window.confirm('Importare i dati dal vecchio Supabase del menu? Le collezioni del menu verranno sostituite con quelle della sorgente (il magazzino bar compreso).')) return;
    try { setJob(await avviaMigrazione({ dry_run: dryRun, con_immagini: true })); }
    catch (err) { toast.error('Errore', { description: messaggioErrore(err, 'Migrazione non avviata') }); }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><Database className="w-5 h-5" /> Dati del menu nel registro unico</CardTitle></CardHeader>
        <CardContent>
          {!stato ? <Loader2 className="w-5 h-5 animate-spin text-[#5b7a6b]" /> : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              {Object.entries(stato.collezioni || {}).map(([k, v]) => <div key={k} className="border border-[#e6e0d4] rounded-lg p-3"><p className="text-xs text-gray-500 truncate">{k}</p><p className="text-xl font-bold text-[#3f5a4e]">{v}</p></div>)}
              <div className="border border-[#e6e0d4] rounded-lg p-3"><p className="text-xs text-gray-500">immagini nell'archivio</p><p className="text-xl font-bold text-[#3f5a4e]">{stato.immagini?.count ?? stato.immagini?.blobs ?? '—'}</p></div>
            </div>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Backup JSON</CardTitle><CardDescription>Un solo file con categorie, prodotti, allergeni, sale, ordini, configurazione QR e immagini. Il magazzino bar è di Lotti e resta fuori.</CardDescription></CardHeader>
        <CardContent className="flex flex-col sm:flex-row gap-3">
          <Button onClick={esporta} disabled={esportando} className={BTN}><Download className="w-4 h-4 mr-2" /> {esportando ? 'Esportazione...' : 'Scarica backup'}</Button>
          {admin && (
            <label className={`inline-flex items-center justify-center gap-2 rounded-md border border-[#c4894a] text-[#8a6f47] px-4 py-2 text-sm font-medium cursor-pointer hover:bg-[#fdf6e3] ${ripristinando ? 'opacity-50 pointer-events-none' : ''}`}>
              <RefreshCw className={`w-4 h-4 ${ripristinando ? 'animate-spin' : ''}`} /> Ripristina da file
              <input type="file" accept="application/json,.json" className="hidden" onChange={ripristina} />
            </label>
          )}
        </CardContent>
      </Card>
      {admin && (
        <Card>
          <CardHeader><CardTitle>Importa dal vecchio menu (Supabase dell'app Menu)</CardTitle><CardDescription>Legge le tabelle menu_* e il magazzino bar di Lotti dalla sorgente configurata su Render (MENU_SUPABASE_URL / MENU_SUPABASE_KEY), scarica le immagini nell'archivio e confronta i conteggi. La sorgente non viene mai modificata.</CardDescription></CardHeader>
          <CardContent className="space-y-3">
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} /> Solo prova (conta senza scrivere)</label>
            <Button onClick={migra} disabled={job && ['queued', 'running'].includes(job.status)} className={BTN}>{job && ['queued', 'running'].includes(job.status) ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> In corso...</> : dryRun ? 'Avvia prova' : 'Avvia importazione'}</Button>
            {job && (
              <div className="text-sm border border-[#e6e0d4] rounded-lg p-3 space-y-1">
                <p><strong>Stato:</strong> {job.status}{job.dry_run ? ' (prova)' : ''} — avviata {dataOra(job.avviato_il)}</p>
                {job.errore && <p className="text-[#d35f4e]">{job.errore}</p>}
                {job.esito && (
                  <div className="overflow-x-auto">
                    <table className="text-xs w-full">
                      <thead><tr><th className="text-left p-1">Tabella</th><th className="text-right p-1">Sorgente</th><th className="text-right p-1">Destinazione</th></tr></thead>
                      <tbody>{Object.entries(job.esito.tabelle || {}).map(([t, v]) => <tr key={t}><td className="p-1">{t}</td><td className="p-1 text-right">{v.sorgente}</td><td className={`p-1 text-right ${v.sorgente !== v.destinazione ? 'text-[#d35f4e] font-bold' : ''}`}>{v.destinazione}</td></tr>)}</tbody>
                    </table>
                    <p className="mt-1">Immagini scaricate: {job.esito.immagini_scaricate} — non scaricate: {job.esito.immagini_non_scaricate} — conteggi {job.esito.coincide ? 'coincidono' : 'NON coincidono'}</p>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ pagina */
export default function Gestione({ ruolo }) {
  const [immagini, setImmagini] = useState([]);
  const [loadingImg, setLoadingImg] = useState(true);
  const ricaricaImmagini = useCallback(() => {
    setLoadingImg(true);
    elencoImmagini().then((r) => setImmagini(r.images || [])).catch(() => {}).finally(() => setLoadingImg(false));
  }, []);
  useEffect(() => { ricaricaImmagini(); }, [ricaricaImmagini]);

  return (
    <div>
      <h2 className="text-xl font-bold text-[#2a3329] mb-1">Gestione menu</h2>
      <p className="text-sm text-gray-500 mb-4">Prodotti, immagini, QR code e backup del menu digitale</p>
      <Tabs defaultValue="prodotti" className="w-full">
        <TabsList className="grid w-full grid-cols-4 mb-4">
          <TabsTrigger value="prodotti">Prodotti</TabsTrigger>
          <TabsTrigger value="immagini">Immagini</TabsTrigger>
          <TabsTrigger value="qrcode">QR code</TabsTrigger>
          <TabsTrigger value="backup">Backup</TabsTrigger>
        </TabsList>
        <TabsContent value="prodotti"><Prodotti immagini={immagini} /></TabsContent>
        <TabsContent value="immagini"><Immagini immagini={immagini} ricarica={ricaricaImmagini} loading={loadingImg} /></TabsContent>
        <TabsContent value="qrcode"><QrCodePannello /></TabsContent>
        <TabsContent value="backup"><BackupPannello ruolo={ruolo} /></TabsContent>
      </Tabs>
    </div>
  );
}
