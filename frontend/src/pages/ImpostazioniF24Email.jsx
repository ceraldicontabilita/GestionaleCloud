import React, { useState, useEffect, useCallback } from 'react';
import { PageLayout } from '../components/PageLayout';
import { COLORS, SHADOWS, BORDER_RADIUS, FONT, useIsMobile } from '../lib/utils';
import { Button, Badge, StatCard, Card, PageHeader, Input, Select, TableWrap, Table, Th, Td, RowActions, RowActionButton } from '../components/ds';
import { toast } from 'sonner';
import { useConfirm } from '../components/ui/ConfirmDialog';
import {
  Settings,
  Mail,
  Plus,
  Trash2,
  Save,
  RefreshCw,
  Play,
  Clock,
  CheckCircle,
  AlertCircle,
  Loader2,
} from 'lucide-react';
import api from '../api';

const TIPI_MITTENTE = [
  { value: 'commercialista', label: 'Commercialista' },
  { value: 'consulente_lavoro', label: 'Consulente Lavoro' },
  { value: 'altro', label: 'Altro' },
];

const CATEGORIE_F24 = [
  { value: 'fiscale', label: 'Fiscale (IRPEF, IVA, IRAP)' },
  { value: 'contributivo', label: 'Contributivo (INPS, INAIL)' },
  { value: 'altro', label: 'Altro' },
];

/* ---- Toggle nativo ---- */
function Toggle({ checked, onChange, testId }) {
  return (
    <div
      data-testid={testId}
      onClick={() => onChange(!checked)}
      style={{
        width: 44,
        height: 24,
        borderRadius: BORDER_RADIUS.full,
        background: checked ? COLORS.success : COLORS.border,
        position: 'relative',
        cursor: 'pointer',
        transition: 'background 0.2s',
        flexShrink: 0,
      }}
    >
      <div
        style={{
          width: 18,
          height: 18,
          borderRadius: '50%',
          background: COLORS.white,
          position: 'absolute',
          top: 3,
          left: checked ? 23 : 3,
          transition: 'left 0.2s',
          boxShadow: SHADOWS.sm,
        }}
      />
    </div>
  );
}

/* ---- Stili locali riutilizzabili ---- */
const statBoxStyle = {
  padding: '12px 16px',
  background: COLORS.bgAlt,
  borderRadius: BORDER_RADIUS.md,
  border: `1px solid ${COLORS.border}`,
};
const labelStyle = {
  fontSize: 12,
  fontWeight: 600,
  color: COLORS.gray[700],
  display: 'block',
  marginBottom: 4,
};

/* ===== SEZIONE GMAIL ===== */
function GmailSettingsSection() {
  const [cfg, setCfg] = useState(null);
  const [form, setForm] = useState({
    imap_user: '',
    gmail_app_password: '',
    imap_host: 'imap.gmail.com',
  });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [msg, setMsg] = useState(null);
  const [showPass, setShowPass] = useState(false);

  useEffect(() => {
    api
      .get('/api/settings/gmail')
      .then(r => {
        setCfg(r.data);
        setForm(f => ({
          ...f,
          imap_user: r.data.imap_user || '',
          imap_host: r.data.imap_host || 'imap.gmail.com',
        }));
      })
      .catch(() => {});
  }, []);

  const salva = async () => {
    setSaving(true);
    setMsg(null);
    try {
      const res = await api.post('/api/settings/gmail', form);
      setMsg({ ok: res.data.status === 'ok', testo: res.data.messaggio });
      if (res.data.status === 'ok')
        setCfg(c => ({
          ...c,
          has_password: true,
          sorgente: 'database',
          imap_user: form.imap_user,
        }));
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
    <div style={{ marginTop: 4 }}>
      <Card title="Credenziali Gmail IMAP" icon={<Mail size={16} color={COLORS.info} />}>
        <p style={{ fontSize: 13, color: COLORS.textMuted, marginBottom: 16, lineHeight: 1.6 }}>
          Inserisci la Gmail App Password per permettere al sistema di scaricare automaticamente
          le email con le fatture. Vai su{' '}
          <strong>Account Google → Sicurezza → Verifica in 2 passaggi → App Password</strong>. La
          password viene salvata nel database (non nel codice).
        </p>

        {cfg && (
          <div
            style={{
              marginBottom: 16,
              padding: '8px 12px',
              borderRadius: BORDER_RADIUS.md,
              background: cfg.has_password ? COLORS.successLight : COLORS.warningLight,
              border: `1px solid ${cfg.has_password ? COLORS.success : COLORS.warning}`,
            }}
          >
            <span
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: cfg.has_password ? COLORS.success : COLORS.warning,
              }}
            >
              {cfg.has_password
                ? `Credenziali presenti — Sorgente: ${cfg.sorgente} — Utente: ${cfg.imap_user}`
                : 'Nessuna credenziale configurata — il download email è disattivato'}
            </span>
          </div>
        )}

        <div style={{ display: 'grid', gap: 12 }}>
          <div>
            <label style={labelStyle}>Email Gmail</label>
            <Input
              value={form.imap_user}
              onChange={e => setForm(f => ({ ...f, imap_user: e.target.value }))}
              placeholder="ceraldigroupsrl@gmail.com"
              type="email"
            />
          </div>
          <div>
            <label style={labelStyle}>App Password Gmail (16 caratteri)</label>
            <div style={{ display: 'flex', gap: 8 }}>
              <Input
                value={form.gmail_app_password}
                onChange={e =>
                  setForm(f => ({ ...f, gmail_app_password: e.target.value.replace(/\s/g, '') }))
                }
                placeholder="abcdabcdabcdabcd"
                type={showPass ? 'text' : 'password'}
                style={{ flex: 1, fontFamily: FONT.mono }}
              />
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setShowPass(s => !s)}
                style={{ flexShrink: 0 }}
              >
                {showPass ? 'Nascondi' : 'Mostra'}
              </Button>
            </div>
            <p style={{ fontSize: 11, color: COLORS.textSubtle, margin: '4px 0 0' }}>
              Incolla la App Password senza spazi. Es: <code>abcdabcdabcdabcd</code>
            </p>
          </div>
          <div>
            <label style={labelStyle}>Server IMAP</label>
            <Input
              value={form.imap_host}
              onChange={e => setForm(f => ({ ...f, imap_host: e.target.value }))}
              placeholder="imap.gmail.com"
            />
          </div>
        </div>

        {msg && (
          <div
            style={{
              marginTop: 12,
              padding: '8px 12px',
              borderRadius: BORDER_RADIUS.md,
              background: msg.ok ? COLORS.successLight : COLORS.dangerLight,
              border: `1px solid ${msg.ok ? COLORS.success : COLORS.danger}`,
              fontSize: 13,
              color: msg.ok ? COLORS.success : COLORS.danger,
            }}
          >
            {msg.ok ? '✓ ' : '✗ '}
            {msg.testo}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
          <Button
            variant="primary"
            onClick={salva}
            disabled={saving || !form.imap_user || !form.gmail_app_password}
            iconLeft={
              saving ? (
                <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />
              ) : (
                <Save size={14} />
              )
            }
          >
            Salva credenziali
          </Button>
          <Button
            variant="secondary"
            onClick={testConnessione}
            disabled={testing || saving}
            iconLeft={
              testing ? (
                <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />
              ) : (
                <RefreshCw size={14} />
              )
            }
          >
            Testa connessione
          </Button>
        </div>
      </Card>
    </div>
  );
}

/* ===== PAGINA PRINCIPALE ===== */
export default function ImpostazioniF24Email() {
  const isMobile = useIsMobile();
  const confirm = useConfirm();
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
    attivo: true,
  });

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [settingsRes, statoRes, logsRes] = await Promise.all([
        api.get('/api/f24-email-settings/impostazioni'),
        api.get('/api/f24-email-settings/stato-sistema'),
        api.get('/api/f24-email-settings/log-scansioni?limit=10'),
      ]);
      const rawSettings = settingsRes.data;
      if (rawSettings && Array.isArray(rawSettings.mittenti)) {
        rawSettings.mittenti = rawSettings.mittenti.map(m =>
          typeof m === 'string'
            ? {
                email: m,
                nome: m,
                tipo: 'altro',
                categoria_f24: 'generico',
                attivo: true,
                parole_chiave: [],
              }
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
        auto_scan_attivo: settings.auto_scan_attivo,
      });
      toast.success('Impostazioni salvate!');
      fetchData();
    } catch (err) {
      toast.error('Errore salvataggio: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  };

  const toggleAutoScan = async attivo => {
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
      toast.success(
        `Scansione completata!\n\nEmail trovate: ${d.download?.email_trovate || 0}\nAllegati scaricati: ${d.download?.allegati_scaricati || 0}\nF24 inseriti: ${d.processamento?.f24_inseriti || 0}`
      );
      fetchData();
    } catch (err) {
      toast.error('Errore scansione: ' + (err.response?.data?.detail || err.message));
    } finally {
      setScanning(false);
    }
  };

  const addMittente = async () => {
    if (!newMittente.email || !newMittente.nome) {
      toast.warning('Inserisci email e nome');
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
        attivo: true,
      });
      fetchData();
    } catch (err) {
      toast.error('Errore: ' + (err.response?.data?.detail || err.message));
    }
  };

  const removeMittente = async email => {
    const ok = await confirm({
      title: 'Rimuovi mittente',
      message: `Rimuovere ${email}?`,
      confirmText: 'Rimuovi',
    });
    if (!ok) return;
    try {
      await api.delete(`/api/f24-email-settings/rimuovi-mittente/${encodeURIComponent(email)}`);
      fetchData();
    } catch (err) {
      toast.error('Errore: ' + (err.response?.data?.detail || err.message));
    }
  };

  const updateMittente = (index, field, value) => {
    setSettings(prev => {
      const newMittenti = [...prev.mittenti];
      newMittenti[index] = { ...newMittenti[index], [field]: value };
      return { ...prev, mittenti: newMittenti };
    });
  };

  const addKeywordToMittente = index => {
    const keyword = newKeyword[index]?.trim();
    if (!keyword) return;
    setSettings(prev => {
      const newMittenti = [...prev.mittenti];
      const parole = newMittenti[index].parole_chiave || [];
      if (!parole.includes(keyword)) newMittenti[index].parole_chiave = [...parole, keyword];
      return { ...prev, mittenti: newMittenti };
    });
    setNewKeyword(prev => ({ ...prev, [index]: '' }));
  };

  const removeKeyword = (mittenteIndex, keyword) => {
    setSettings(prev => {
      const newMittenti = [...prev.mittenti];
      newMittenti[mittenteIndex].parole_chiave = (
        newMittenti[mittenteIndex].parole_chiave || []
      ).filter(k => k !== keyword);
      return { ...prev, mittenti: newMittenti };
    });
  };

  if (loading) {
    return (
      <PageLayout>
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60, color: COLORS.textSubtle }}>
          <Loader2 size={32} style={{ animation: 'spin 1s linear infinite' }} />
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout>
      <div style={{ maxWidth: 1100 }} data-testid="f24-email-settings">
        {/* HEADER */}
        <PageHeader
          title="Impostazioni Email"
          subtitle="Configura download automatico F24 da email"
          style={{ marginBottom: 20 }}
        />

        {/* === STATO SISTEMA === */}
        <Card
          title="Stato Sistema"
          icon={<Settings size={16} color={COLORS.primary} />}
          style={{ marginBottom: 20 }}
          actions={
            <div style={{ display: 'flex', gap: 8 }}>
              <Button
                variant="secondary"
                size="sm"
                onClick={fetchData}
                iconLeft={<RefreshCw size={13} />}
              >
                Aggiorna
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={runManualScan}
                disabled={scanning}
                data-testid="scan-manuale-btn"
                iconLeft={
                  scanning ? (
                    <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} />
                  ) : (
                    <Play size={13} />
                  )
                }
              >
                Scansiona Ora
              </Button>
            </div>
          }
        >
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)',
              gap: 12,
              marginBottom: 16,
            }}
          >
            <div style={statBoxStyle}>
              <div style={{ fontSize: 11, color: COLORS.textMuted, marginBottom: 4 }}>
                Scansione Auto
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Toggle
                  checked={settings?.auto_scan_attivo || false}
                  onChange={toggleAutoScan}
                  testId="auto-scan-toggle"
                />
                <span
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: settings?.auto_scan_attivo ? COLORS.success : COLORS.textSubtle,
                  }}
                >
                  {settings?.auto_scan_attivo ? 'Attiva' : 'Disattiva'}
                </span>
              </div>
            </div>
            <StatCard
              icon={<Clock size={11} />}
              label="Intervallo"
              value={`${settings?.scan_interval_minuti || 10} min`}
              accent="none"
              style={{ padding: '12px 16px' }}
            />
            <StatCard
              label="Mittenti Configurati"
              value={(settings?.mittenti || []).length}
              accent="none"
              style={{ padding: '12px 16px' }}
            />
            <StatCard
              label="F24 da Pagare"
              value={stato?.statistiche?.f24_da_pagare || 0}
              accent="danger"
              style={{ padding: '12px 16px' }}
            />
          </div>
          {stato?.ultima_scansione && (
            <div
              style={{
                padding: '8px 12px',
                background: COLORS.infoLight,
                borderRadius: BORDER_RADIUS.md,
                fontSize: 12,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                color: COLORS.info,
              }}
            >
              {stato.ultima_scansione.success ? (
                <CheckCircle size={14} color={COLORS.success} />
              ) : (
                <AlertCircle size={14} color={COLORS.danger} />
              )}
              Ultima scansione:{' '}
              {new Date(stato.ultima_scansione.timestamp).toLocaleString('it-IT').replaceAll('/', '-')} —{' '}
              {stato.ultima_scansione.tipo}
            </div>
          )}
        </Card>

        {/* === CONFIGURAZIONE === */}
        <Card
          title="Configurazione Scansione"
          icon={<Clock size={16} color={COLORS.primary} />}
          style={{ marginBottom: 20 }}
        >
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr 1fr',
              gap: 16,
            }}
          >
            <div>
              <label style={labelStyle}>Intervallo scansione (minuti)</label>
              <Input
                type="number"
                min="5"
                max="120"
                value={settings?.scan_interval_minuti || 10}
                onChange={e =>
                  setSettings(prev => ({
                    ...prev,
                    scan_interval_minuti: parseInt(e.target.value) || 10,
                  }))
                }
                data-testid="scan-interval-input"
              />
            </div>
            <div>
              <label style={labelStyle}>Giorni indietro da cercare</label>
              <Input
                type="number"
                min="1"
                max="365"
                value={settings?.giorni_indietro || 7}
                onChange={e =>
                  setSettings(prev => ({
                    ...prev,
                    giorni_indietro: parseInt(e.target.value) || 7,
                  }))
                }
                data-testid="giorni-indietro-input"
              />
            </div>
            <div style={{ display: 'flex', alignItems: 'flex-end' }}>
              <Button
                variant="primary"
                onClick={saveSettings}
                disabled={saving}
                data-testid="save-settings-btn"
                style={{ width: '100%', justifyContent: 'center' }}
                iconLeft={
                  saving ? (
                    <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />
                  ) : (
                    <Save size={14} />
                  )
                }
              >
                Salva Impostazioni
              </Button>
            </div>
          </div>
        </Card>

        {/* === MITTENTI === */}
        <Card
          title={`Mittenti Configurati (${(settings?.mittenti || []).length})`}
          icon={<Mail size={16} color={COLORS.primary} />}
          style={{ marginBottom: 20 }}
          actions={
            <Button
              variant="primary"
              size="sm"
              onClick={() => setShowAddMittente(true)}
              data-testid="add-mittente-btn"
              iconLeft={<Plus size={13} />}
            >
              Aggiungi Mittente
            </Button>
          }
        >
          {/* Form nuovo mittente */}
          {showAddMittente && (
            <div
              style={{
                marginBottom: 20,
                padding: 16,
                borderRadius: BORDER_RADIUS.lg,
                background: COLORS.infoLight,
                border: `1px solid ${COLORS.info}`,
              }}
            >
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 12, color: COLORS.info }}>
                Nuovo Mittente
              </div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
                  gap: 10,
                }}
              >
                <Input
                  placeholder="Email mittente"
                  value={newMittente.email}
                  onChange={e => setNewMittente(prev => ({ ...prev, email: e.target.value }))}
                  data-testid="new-mittente-email"
                />
                <Input
                  placeholder="Nome (opzionale)"
                  value={newMittente.nome}
                  onChange={e => setNewMittente(prev => ({ ...prev, nome: e.target.value }))}
                  data-testid="new-mittente-nome"
                />
                <Select
                  value={newMittente.tipo}
                  onChange={e => setNewMittente(prev => ({ ...prev, tipo: e.target.value }))}
                  style={{ width: '100%' }}
                >
                  {TIPI_MITTENTE.map(t => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </Select>
                <Select
                  value={newMittente.categoria_f24}
                  onChange={e =>
                    setNewMittente(prev => ({ ...prev, categoria_f24: e.target.value }))
                  }
                  style={{ width: '100%' }}
                >
                  {CATEGORIE_F24.map(c => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={addMittente}
                  data-testid="confirm-add-mittente-btn"
                  iconLeft={<Plus size={13} />}
                >
                  Aggiungi
                </Button>
                <Button variant="secondary" size="sm" onClick={() => setShowAddMittente(false)}>
                  Annulla
                </Button>
              </div>
            </div>
          )}

          {/* Lista mittenti */}
          {(settings?.mittenti || []).length === 0 ? (
            <div style={{ textAlign: 'center', padding: '32px 0', color: COLORS.textSubtle, fontSize: 13 }}>
              Nessun mittente configurato. Aggiungine uno.
            </div>
          ) : (
            <TableWrap>
              <Table>
                <thead>
                  <tr>
                    <Th>EMAIL</Th>
                    <Th>TIPO</Th>
                    <Th>PAROLE CHIAVE</Th>
                    <Th align="center">ATTIVO</Th>
                    <Th></Th>
                  </tr>
                </thead>
                <tbody>
                  {(settings?.mittenti || []).map((mittente, index) => (
                    <tr
                      key={mittente.email || index}
                      style={{ opacity: mittente.attivo ? 1 : 0.5 }}
                      data-testid={`mittente-card-${index}`}
                    >
                      <Td>
                        <div style={{ fontSize: 13, fontWeight: 500, color: COLORS.text }}>
                          {mittente.email}
                        </div>
                        {mittente.nome && mittente.nome !== mittente.email && (
                          <div style={{ fontSize: 11, color: COLORS.textSubtle }}>{mittente.nome}</div>
                        )}
                      </Td>
                      <Td>
                        <Badge variant={mittente.tipo === 'commercialista' ? 'info' : 'neutral'}>
                          {TIPI_MITTENTE.find(t => t.value === mittente.tipo)?.label ||
                            mittente.tipo ||
                            'Altro'}
                        </Badge>
                      </Td>
                      <Td>
                        <div
                          style={{
                            display: 'flex',
                            flexWrap: 'wrap',
                            gap: 4,
                            alignItems: 'center',
                          }}
                        >
                          {(mittente.parole_chiave || []).map(kw => (
                            <Badge
                              key={kw}
                              variant="neutral"
                              style={{ display: 'flex', alignItems: 'center', gap: 4 }}
                            >
                              {kw}
                              <button
                                onClick={() => removeKeyword(index, kw)}
                                style={{
                                  background: 'none',
                                  border: 'none',
                                  cursor: 'pointer',
                                  color: COLORS.danger,
                                  padding: 0,
                                  fontSize: 12,
                                }}
                              >
                                ×
                              </button>
                            </Badge>
                          ))}
                          <div style={{ display: 'flex', gap: 4 }}>
                            <input
                              placeholder="+ parola"
                              style={{
                                width: 100,
                                height: 26,
                                fontSize: 11,
                                padding: '0 8px',
                                borderRadius: BORDER_RADIUS.sm,
                                border: `1px solid ${COLORS.border}`,
                                fontFamily: FONT.family,
                              }}
                              value={newKeyword[index] || ''}
                              onChange={e =>
                                setNewKeyword(prev => ({ ...prev, [index]: e.target.value }))
                              }
                              onKeyDown={e => e.key === 'Enter' && addKeywordToMittente(index)}
                            />
                            <RowActionButton
                              variant="neutral"
                              onClick={() => addKeywordToMittente(index)}
                              style={{ width: 26, height: 26 }}
                            >
                              <Plus size={12} />
                            </RowActionButton>
                          </div>
                        </div>
                      </Td>
                      <Td align="center">
                        <Toggle
                          checked={mittente.attivo}
                          onChange={v => updateMittente(index, 'attivo', v)}
                        />
                      </Td>
                      <Td align="center">
                        <RowActions style={{ justifyContent: 'center' }}>
                          <RowActionButton variant="danger" onClick={() => removeMittente(mittente.email)}>
                            <Trash2 size={15} />
                          </RowActionButton>
                        </RowActions>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableWrap>
          )}
        </Card>

        {/* === LOG SCANSIONI === */}
        <Card
          title="Log Scansioni Recenti"
          icon={<RefreshCw size={16} color={COLORS.primary} />}
          style={{ marginBottom: 20 }}
        >
          {logs.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '24px 0', color: COLORS.textSubtle, fontSize: 13 }}>
              Nessuna scansione effettuata
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {logs.map((log, index) => (
                <div
                  key={index}
                  style={{
                    padding: '10px 14px',
                    borderRadius: BORDER_RADIUS.md,
                    background: log.success ? COLORS.successLight : COLORS.dangerLight,
                    border: `1px solid ${log.success ? COLORS.success : COLORS.danger}`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    fontSize: 12,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    {log.success ? (
                      <CheckCircle size={14} color={COLORS.success} />
                    ) : (
                      <AlertCircle size={14} color={COLORS.danger} />
                    )}
                    <span style={{ color: COLORS.gray[700] }}>
                      {new Date(log.timestamp).toLocaleString('it-IT').replaceAll('/', '-')}
                    </span>
                    <Badge variant="neutral">{log.tipo}</Badge>
                  </div>
                  <div style={{ display: 'flex', gap: 12, color: COLORS.textMuted }}>
                    {log.risultato?.processamento && (
                      <span>F24: {log.risultato.processamento.f24_inseriti || 0}</span>
                    )}
                    {log.errore && <span style={{ color: COLORS.danger }}>{log.errore}</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* === GMAIL SETTINGS === */}
        <GmailSettingsSection />
      </div>
    </PageLayout>
  );
}
