import React, { useState, useEffect } from 'react';
import { PageLayout } from '../components/PageLayout';
import { COLORS, SHADOWS, BORDER_RADIUS, FONT } from '../lib/utils';
import { Button, Card, PageHeader, Input } from '../components/ds';
import { Bot, Save, RefreshCw, Loader2 } from 'lucide-react';
import api from '../api';

const labelStyle = {
  fontSize: 12,
  fontWeight: 600,
  color: COLORS.gray[700],
  display: 'block',
  marginBottom: 4,
};

export default function ImpostazioniAI() {
  const [cfg, setCfg] = useState(null);
  const [apiKey, setApiKey] = useState('');
  const [modello, setModello] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [msg, setMsg] = useState(null);

  const carica = () => {
    api
      .get('/api/settings/anthropic')
      .then(r => {
        setCfg(r.data);
        setModello(r.data.modello || '');
      })
      .catch(() => {});
  };
  useEffect(carica, []);

  const salva = async () => {
    setSaving(true);
    setMsg(null);
    try {
      const res = await api.post('/api/settings/anthropic', {
        api_key: apiKey.trim(),
        modello: modello.trim(),
      });
      setMsg({ ok: res.data.status === 'ok', testo: res.data.messaggio });
      setApiKey('');
      carica();
    } catch (e) {
      setMsg({ ok: false, testo: e.response?.data?.detail || 'Errore durante il salvataggio' });
    } finally {
      setSaving(false);
    }
  };

  const testa = async () => {
    setTesting(true);
    setMsg(null);
    try {
      const res = await api.post('/api/settings/anthropic/test');
      setMsg({ ok: res.data.ok, testo: res.data.messaggio || res.data.error });
    } catch {
      setMsg({ ok: false, testo: 'Errore durante il test' });
    } finally {
      setTesting(false);
    }
  };

  return (
    <PageLayout>
      <div style={{ maxWidth: 760 }} data-testid="impostazioni-ai">
        <PageHeader
          title="Assistente AI"
          subtitle="Attiva l'intelligenza artificiale della chat (Anthropic)"
          style={{ marginBottom: 20 }}
        />

        <Card title="Chiave API Anthropic" icon={<Bot size={16} color={COLORS.info} />}>
          <p style={{ fontSize: 13, color: COLORS.textMuted, marginBottom: 16, lineHeight: 1.6 }}>
            Incolla qui la tua chiave API Anthropic: la chat capirà le domande in
            linguaggio naturale (come parlare con un assistente) invece di rispondere
            solo a comandi fissi. La chiave viene salvata <strong>cifrata</strong> nel
            database, non nel codice. La ottieni da{' '}
            <strong>console.anthropic.com → API Keys</strong>.
          </p>

          {cfg && (
            <div
              style={{
                marginBottom: 16,
                padding: '8px 12px',
                borderRadius: BORDER_RADIUS.md,
                background: cfg.configurata ? COLORS.successLight : COLORS.warningLight,
                border: `1px solid ${cfg.configurata ? COLORS.success : COLORS.warning}`,
              }}
            >
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: cfg.configurata ? COLORS.success : COLORS.warning,
                }}
              >
                {cfg.configurata
                  ? `Assistente AI attivo — chiave da: ${cfg.fonte} — modello: ${cfg.modello}`
                  : 'Assistente AI non attivo — la chat risponde solo a comandi fissi'}
              </span>
            </div>
          )}

          <div style={{ display: 'grid', gap: 12 }}>
            <div>
              <label style={labelStyle}>Chiave API (inizia con sk-)</label>
              <div style={{ display: 'flex', gap: 8 }}>
                <Input
                  value={apiKey}
                  onChange={e => setApiKey(e.target.value)}
                  placeholder="sk-ant-..."
                  type={showKey ? 'text' : 'password'}
                  style={{ flex: 1, fontFamily: FONT.mono }}
                />
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowKey(s => !s)}
                  style={{ flexShrink: 0 }}
                >
                  {showKey ? 'Nascondi' : 'Mostra'}
                </Button>
              </div>
            </div>
            <div>
              <label style={labelStyle}>Modello (opzionale)</label>
              <Input
                value={modello}
                onChange={e => setModello(e.target.value)}
                placeholder="claude-sonnet-5"
              />
              <p style={{ fontSize: 11, color: COLORS.textSubtle, margin: '4px 0 0' }}>
                Lascia vuoto per usare il modello predefinito (claude-sonnet-5).
              </p>
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
              disabled={saving || !apiKey.trim()}
              iconLeft={
                saving ? (
                  <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />
                ) : (
                  <Save size={14} />
                )
              }
            >
              Salva e attiva
            </Button>
            <Button
              variant="secondary"
              onClick={testa}
              disabled={testing || saving}
              iconLeft={
                testing ? (
                  <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />
                ) : (
                  <RefreshCw size={14} />
                )
              }
            >
              Testa chiave
            </Button>
          </div>
        </Card>
      </div>
    </PageLayout>
  );
}
