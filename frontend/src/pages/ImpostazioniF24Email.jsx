import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Switch } from '../components/ui/switch';
import { Badge } from '../components/ui/badge';
import { PageLayout } from '../components/PageLayout';
import { 
  Settings, Mail, Plus, Trash2, Save, RefreshCw, Play, 
  Clock, CheckCircle, AlertCircle, Loader2, Tag
} from 'lucide-react';
import api from '../api';

const TIPI_MITTENTE = [
  { value: 'commercialista', label: 'Commercialista' },
  { value: 'consulente_lavoro', label: 'Consulente Lavoro' },
  { value: 'altro', label: 'Altro' }
];

const CATEGORIE_F24 = [
  { value: 'fiscale', label: 'Fiscale (IRPEF, IVA, IRAP)' },
  { value: 'contributivo', label: 'Contributivo (INPS, INAIL)' },
  { value: 'altro', label: 'Altro' }
];

// ===== COMPONENTE GMAIL SETTINGS =====
function GmailSettingsSection() {
  const [cfg, setCfg] = useState(null);
  const [form, setForm] = useState({ imap_user: '', gmail_app_password: '', imap_host: 'imap.gmail.com' });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [msg, setMsg] = useState(null);
  const [showPass, setShowPass] = useState(false);

  useEffect(() => {
    api.get('/api/settings/gmail')
      .then(r => {
        setCfg(r.data);
        setForm(f => ({ ...f, imap_user: r.data.imap_user || '', imap_host: r.data.imap_host || 'imap.gmail.com' }));
      })
      .catch(() => {});
  }, []);

  const salva = async () => {
    setSaving(true);
    setMsg(null);
    try {
      const res = await api.post('/api/settings/gmail', form);
      setMsg({ ok: res.data.status === 'ok', testo: res.data.messaggio });
      if (res.data.status === 'ok') setCfg(c => ({ ...c, has_password: true, sorgente: 'database', imap_user: form.imap_user }));
    } catch (e) {
      setMsg({ ok: false, testo: e.response?.data?.detail || 'Errore durante il salvataggio' });
    } finally {
      setSaving(false);
    }
  };

  const testConnessione = async () => {
    setTesting(true);
    setMsg(null);
    try {
      const res = await api.post('/api/settings/gmail/test');
      setMsg({ ok: res.data.ok, testo: res.data.messaggio || res.data.error });
    } catch {
      setMsg({ ok: false, testo: 'Errore durante il test' });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div style={{ maxWidth: 860, margin: '0 auto', padding: '16px 0' }}>
      <Card>
        <CardHeader>
          <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Mail className="w-5 h-5 text-blue-600" />
            Credenziali Gmail IMAP
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p style={{ fontSize: 13, color: '#64748b', marginBottom: 16, lineHeight: 1.6 }}>
            Inserisci la Gmail App Password per permettere al sistema di scaricare automaticamente
            le email con le fatture. Vai su <strong>Account Google → Sicurezza → Verifica in 2 passaggi → App Password</strong> per generare una nuova password.
            La password viene salvata nel database (non nel codice).
          </p>

          {cfg && (
            <div style={{ marginBottom: 16, padding: '8px 12px', borderRadius: 8, background: cfg.has_password ? '#f0fdf4' : '#fff7ed', border: `1px solid ${cfg.has_password ? '#bbf7d0' : '#fed7aa'}` }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: cfg.has_password ? '#16a34a' : '#d97706' }}>
                {cfg.has_password
                  ? `Credenziali presenti — Sorgente: ${cfg.sorgente} — Utente: ${cfg.imap_user}`
                  : 'Nessuna credenziale configurata — il download email è disattivato'}
              </span>
            </div>
          )}

          <div style={{ display: 'grid', gap: 12 }}>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Email Gmail</label>
              <Input
                value={form.imap_user}
                onChange={e => setForm(f => ({ ...f, imap_user: e.target.value }))}
                placeholder="ceraldigroupsrl@gmail.com"
                type="email"
              />
            </div>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>App Password Gmail (16 caratteri)</label>
              <div style={{ display: 'flex', gap: 8 }}>
                <Input
                  value={form.gmail_app_password}
                  onChange={e => setForm(f => ({ ...f, gmail_app_password: e.target.value.replace(/\s/g, '') }))}
                  placeholder="abcdabcdabcdabcd"
                  type={showPass ? 'text' : 'password'}
                  style={{ flex: 1, fontFamily: 'monospace' }}
                />
                <Button variant="outline" size="sm" onClick={() => setShowPass(s => !s)} style={{ flexShrink: 0 }}>
                  {showPass ? 'Nascondi' : 'Mostra'}
                </Button>
              </div>
              <p style={{ fontSize: 11, color: '#94a3b8', margin: '4px 0 0' }}>
                Incolla la App Password senza spazi. Es: <code>abcdabcdabcdabcd</code>
              </p>
            </div>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>Server IMAP</label>
              <Input
                value={form.imap_host}
                onChange={e => setForm(f => ({ ...f, imap_host: e.target.value }))}
                placeholder="imap.gmail.com"
              />
            </div>
          </div>

          {msg && (
            <div style={{ marginTop: 12, padding: '8px 12px', borderRadius: 8, background: msg.ok ? '#f0fdf4' : '#fef2f2', border: `1px solid ${msg.ok ? '#bbf7d0' : '#fecaca'}`, fontSize: 13, color: msg.ok ? '#16a34a' : '#dc2626' }}>
              {msg.ok ? '✓ ' : '✗ '}{msg.testo}
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
            <Button onClick={salva} disabled={saving || !form.imap_user || !form.gmail_app_password} style={{ background: '#1e3a5f', color: '#fff' }}>
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Save className="w-4 h-4 mr-2" />}
              Salva credenziali
            </Button>
            <Button variant="outline" onClick={testConnessione} disabled={testing || saving}>
              {testing ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <RefreshCw className="w-4 h-4 mr-2" />}
              Testa connessione
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}



export default function ImpostazioniF24Email() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [settings, setSettings] = useState(null);
  const [stato, setStato] = useState(null);
  const [logs, setLogs] = useState([]);
  const [newKeyword, setNewKeyword] = useState({});
  const [showAddMittente, setShowAddMittente] = useState(false);
  const [newMittente, setNewMittente] = useState({
    email: '',
    nome: '',
    tipo: 'commercialista',
    categoria_f24: 'fiscale',
    parole_chiave: [],
    attivo: true
  });

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [settingsRes, statoRes, logsRes] = await Promise.all([
        api.get('/api/f24-email-settings/impostazioni'),
        api.get('/api/f24-email-settings/stato-sistema'),
        api.get('/api/f24-email-settings/log-scansioni?limit=10')
      ]);
      // Normalizza mittenti: se sono stringhe, convertili in oggetti
      const rawSettings = settingsRes.data;
      if (rawSettings && Array.isArray(rawSettings.mittenti)) {
        rawSettings.mittenti = rawSettings.mittenti.map(m =>
          typeof m === 'string'
            ? { email: m, nome: m, tipo: 'altro', categoria_f24: 'generico', attivo: true, parole_chiave: [] }
            : m
        );
      }
      setSettings(rawSettings);
      setStato(statoRes.data);
      setLogs(logsRes.data.logs || []);
    } catch (err) {
      console.error('Errore caricamento impostazioni:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const saveSettings = async () => {
    setSaving(true);
    try {
      await api.post('/api/f24-email-settings/impostazioni', {
        mittenti: settings.mittenti,
        scan_interval_minuti: settings.scan_interval_minuti,
        giorni_indietro: settings.giorni_indietro,
        auto_scan_attivo: settings.auto_scan_attivo
      });
      alert('Impostazioni salvate!');
      fetchData();
    } catch (err) {
      console.error('Errore salvataggio:', err);
      alert('Errore salvataggio: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  };

  const toggleAutoScan = async (attivo) => {
    try {
      await api.post(`/api/f24-email-settings/toggle-auto-scan?attivo=${attivo}`);
      setSettings(prev => ({ ...prev, auto_scan_attivo: attivo }));
      fetchData();
    } catch (err) {
      console.error('Errore toggle auto-scan:', err);
    }
  };

  const runManualScan = async () => {
    setScanning(true);
    try {
      const res = await api.post('/api/f24-email-settings/scan-manuale');
      const d = res.data;
      alert(`Scansione completata!\n\nEmail trovate: ${d.download?.email_trovate || 0}\nAllegati scaricati: ${d.download?.allegati_scaricati || 0}\nF24 inseriti: ${d.processamento?.f24_inseriti || 0}`);
      fetchData();
    } catch (err) {
      console.error('Errore scansione:', err);
      alert('Errore scansione: ' + (err.response?.data?.detail || err.message));
    } finally {
      setScanning(false);
    }
  };

  const addMittente = async () => {
    if (!newMittente.email || !newMittente.nome) {
      alert('Inserisci email e nome');
      return;
    }
    try {
      await api.post('/api/f24-email-settings/aggiungi-mittente', newMittente);
      setShowAddMittente(false);
      setNewMittente({
        email: '',
        nome: '',
        tipo: 'commercialista',
        categoria_f24: 'fiscale',
        parole_chiave: [],
        attivo: true
      });
      fetchData();
    } catch (err) {
      alert('Errore: ' + (err.response?.data?.detail || err.message));
    }
  };

  const removeMittente = async (email) => {
    if (!window.confirm(`Rimuovere ${email}?`)) return;
    try {
      await api.delete(`/api/f24-email-settings/rimuovi-mittente/${encodeURIComponent(email)}`);
      fetchData();
    } catch (err) {
      alert('Errore: ' + (err.response?.data?.detail || err.message));
    }
  };

  const updateMittente = (index, field, value) => {
    setSettings(prev => {
      const newMittenti = [...prev.mittenti];
      newMittenti[index] = { ...newMittenti[index], [field]: value };
      return { ...prev, mittenti: newMittenti };
    });
  };

  const addKeywordToMittente = (index) => {
    const keyword = newKeyword[index]?.trim();
    if (!keyword) return;
    
    setSettings(prev => {
      const newMittenti = [...prev.mittenti];
      const parole = newMittenti[index].parole_chiave || [];
      if (!parole.includes(keyword)) {
        newMittenti[index].parole_chiave = [...parole, keyword];
      }
      return { ...prev, mittenti: newMittenti };
    });
    setNewKeyword(prev => ({ ...prev, [index]: '' }));
  };

  const removeKeyword = (mittenteIndex, keyword) => {
    setSettings(prev => {
      const newMittenti = [...prev.mittenti];
      newMittenti[mittenteIndex].parole_chiave = 
        (newMittenti[mittenteIndex].parole_chiave || []).filter(k => k !== keyword);
      return { ...prev, mittenti: newMittenti };
    });
  };

  if (loading) {
    return (
      <PageLayout title="Impostazioni F24 Email" subtitle="Configura download automatico F24 da email">
        <div className="flex justify-center items-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout title="Impostazioni F24 Email" subtitle="Configura download automatico F24 da email">
      <div className="space-y-6" data-testid="f24-email-settings">
        
        {/* Status Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Settings className="w-5 h-5" />
                Stato Sistema
              </div>
              <div className="flex items-center gap-3">
                <Button variant="outline" size="sm" onClick={fetchData}>
                  <RefreshCw className="w-4 h-4 mr-2" />
                  Aggiorna
                </Button>
                <Button 
                  onClick={runManualScan} 
                  disabled={scanning}
                  data-testid="scan-manuale-btn"
                >
                  {scanning ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <Play className="w-4 h-4 mr-2" />
                  )}
                  Scansiona Ora
                </Button>
              </div>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-4 bg-gray-50 rounded-lg">
                <div className="text-sm text-gray-500">Scansione Auto</div>
                <div className="flex items-center gap-2 mt-1">
                  <Switch 
                    checked={settings?.auto_scan_attivo || false}
                    onCheckedChange={toggleAutoScan}
                    data-testid="auto-scan-toggle"
                  />
                  <span className={`font-medium ${settings?.auto_scan_attivo ? 'text-green-600' : 'text-gray-400'}`}>
                    {settings?.auto_scan_attivo ? 'Attiva' : 'Disattiva'}
                  </span>
                </div>
              </div>
              <div className="p-4 bg-gray-50 rounded-lg">
                <div className="text-sm text-gray-500 flex items-center gap-1">
                  <Clock className="w-3 h-3" /> Intervallo
                </div>
                <div className="font-semibold mt-1">{settings?.scan_interval_minuti || 10} minuti</div>
              </div>
              <div className="p-4 bg-gray-50 rounded-lg">
                <div className="text-sm text-gray-500">Mittenti Configurati</div>
                <div className="font-semibold mt-1">{stato?.mittenti_configurati || 0}</div>
              </div>
              <div className="p-4 bg-gray-50 rounded-lg">
                <div className="text-sm text-gray-500">F24 da Pagare</div>
                <div className="font-semibold mt-1 text-red-600">{stato?.statistiche?.f24_da_pagare || 0}</div>
              </div>
            </div>

            {stato?.ultima_scansione && (
              <div className="mt-4 p-3 bg-blue-50 rounded-lg text-sm">
                <div className="flex items-center gap-2">
                  {stato.ultima_scansione.success ? (
                    <CheckCircle className="w-4 h-4 text-green-500" />
                  ) : (
                    <AlertCircle className="w-4 h-4 text-red-500" />
                  )}
                  <span>
                    Ultima scansione: {new Date(stato.ultima_scansione.timestamp).toLocaleString('it-IT')}
                    {' - '}{stato.ultima_scansione.tipo}
                  </span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Configurazione Intervallo */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock className="w-5 h-5" />
              Configurazione Scansione
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="text-sm font-medium text-gray-700 block mb-2">
                  Intervallo scansione (minuti)
                </label>
                <Input
                  type="number"
                  min="5"
                  max="60"
                  value={settings?.scan_interval_minuti || 10}
                  onChange={(e) => setSettings(prev => ({ 
                    ...prev, 
                    scan_interval_minuti: parseInt(e.target.value) || 10 
                  }))}
                  data-testid="scan-interval-input"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 block mb-2">
                  Giorni indietro da cercare
                </label>
                <Input
                  type="number"
                  min="1"
                  max="365"
                  value={settings?.giorni_indietro || 7}
                  onChange={(e) => setSettings(prev => ({ 
                    ...prev, 
                    giorni_indietro: parseInt(e.target.value) || 7 
                  }))}
                  data-testid="giorni-indietro-input"
                />
              </div>
              <div className="flex items-end">
                <Button onClick={saveSettings} disabled={saving} className="w-full" data-testid="save-settings-btn">
                  {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
                  Salva Impostazioni
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Mittenti Configurati */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Mail className="w-5 h-5" />
                Mittenti Configurati
              </div>
              <Button size="sm" onClick={() => setShowAddMittente(true)} data-testid="add-mittente-btn">
                <Plus className="w-4 h-4 mr-2" />
                Aggiungi Mittente
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {/* Form nuovo mittente */}
            {showAddMittente && (
              <div className="mb-6 p-4 border rounded-lg bg-blue-50">
                <h4 className="font-medium mb-3">Nuovo Mittente</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <Input
                    placeholder="Email mittente"
                    value={newMittente.email}
                    onChange={(e) => setNewMittente(prev => ({ ...prev, email: e.target.value }))}
                    data-testid="new-mittente-email"
                  />
                  <Input
                    placeholder="Nome"
                    value={newMittente.nome}
                    onChange={(e) => setNewMittente(prev => ({ ...prev, nome: e.target.value }))}
                    data-testid="new-mittente-nome"
                  />
                  <Select 
                    value={newMittente.tipo} 
                    onValueChange={(v) => setNewMittente(prev => ({ ...prev, tipo: v }))}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {TIPI_MITTENTE.map(t => (
                        <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select 
                    value={newMittente.categoria_f24} 
                    onValueChange={(v) => setNewMittente(prev => ({ ...prev, categoria_f24: v }))}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {CATEGORIE_F24.map(c => (
                        <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex gap-2 mt-3">
                  <Button size="sm" onClick={addMittente} data-testid="confirm-add-mittente-btn">
                    <Plus className="w-4 h-4 mr-1" /> Aggiungi
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setShowAddMittente(false)}>
                    Annulla
                  </Button>
                </div>
              </div>
            )}

            {/* Lista mittenti */}
            <div className="space-y-4">
              {(settings?.mittenti || []).map((mittente, index) => (
                <div 
                  key={mittente.email} 
                  className={`p-4 border rounded-lg ${mittente.attivo ? 'bg-white' : 'bg-gray-50 opacity-60'}`}
                  data-testid={`mittente-card-${index}`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <Mail className="w-4 h-4 text-blue-500" />
                        <span className="font-medium">{mittente.nome}</span>
                        <Badge variant={mittente.tipo === 'commercialista' ? 'default' : 'secondary'}>
                          {TIPI_MITTENTE.find(t => t.value === mittente.tipo)?.label || mittente.tipo}
                        </Badge>
                        <Badge variant="outline">
                          {CATEGORIE_F24.find(c => c.value === mittente.categoria_f24)?.label || mittente.categoria_f24}
                        </Badge>
                      </div>
                      <div className="text-sm text-gray-500 mb-3">{mittente.email}</div>
                      
                      {/* Parole chiave */}
                      <div className="flex flex-wrap items-center gap-2">
                        <Tag className="w-4 h-4 text-gray-400" />
                        {(mittente.parole_chiave || []).map(kw => (
                          <Badge 
                            key={kw} 
                            variant="outline" 
                            className="cursor-pointer hover:bg-red-50"
                            onClick={() => removeKeyword(index, kw)}
                          >
                            {kw} <span className="ml-1 text-red-400">x</span>
                          </Badge>
                        ))}
                        <div className="flex items-center gap-1">
                          <Input
                            placeholder="Nuova parola chiave"
                            className="w-36 h-7 text-sm"
                            value={newKeyword[index] || ''}
                            onChange={(e) => setNewKeyword(prev => ({ ...prev, [index]: e.target.value }))}
                            onKeyPress={(e) => e.key === 'Enter' && addKeywordToMittente(index)}
                          />
                          <Button 
                            size="sm" 
                            variant="ghost" 
                            className="h-7 px-2"
                            onClick={() => addKeywordToMittente(index)}
                          >
                            <Plus className="w-3 h-3" />
                          </Button>
                        </div>
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-2">
                      <Switch
                        checked={mittente.attivo}
                        onCheckedChange={(v) => updateMittente(index, 'attivo', v)}
                      />
                      <Button 
                        size="sm" 
                        variant="ghost" 
                        className="text-red-500 hover:text-red-700"
                        onClick={() => removeMittente(mittente.email)}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
              
              {(!settings?.mittenti || settings.mittenti.length === 0) && (
                <div className="text-center py-8 text-gray-500">
                  Nessun mittente configurato. Aggiungi il primo mittente.
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Log scansioni */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <RefreshCw className="w-5 h-5" />
              Log Scansioni Recenti
            </CardTitle>
          </CardHeader>
          <CardContent>
            {logs.length === 0 ? (
              <div className="text-center py-6 text-gray-500">
                Nessuna scansione effettuata
              </div>
            ) : (
              <div className="space-y-2">
                {logs.map((log, index) => (
                  <div 
                    key={index} 
                    className={`p-3 rounded-lg flex items-center justify-between ${
                      log.success ? 'bg-green-50' : 'bg-red-50'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      {log.success ? (
                        <CheckCircle className="w-4 h-4 text-green-500" />
                      ) : (
                        <AlertCircle className="w-4 h-4 text-red-500" />
                      )}
                      <span className="text-sm">
                        {new Date(log.timestamp).toLocaleString('it-IT')}
                      </span>
                      <Badge variant="outline">{log.tipo}</Badge>
                    </div>
                    {log.risultato?.processamento && (
                      <span className="text-xs text-gray-500">
                        F24: {log.risultato.processamento.f24_inseriti || 0}
                      </span>
                    )}
                    {log.errore && (
                      <span className="text-xs text-red-500">{log.errore}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ===== SEZIONE GMAIL APP PASSWORD ===== */}
      <GmailSettingsSection />

    </PageLayout>
  );
}
