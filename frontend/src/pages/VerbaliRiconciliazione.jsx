import React, { useState, useEffect, useCallback } from 'react';
import api from '../api';
import { useConfirm } from '../components/ui/ConfirmDialog';
import { formatEuro, formatDateIT, COLORS, SHADOWS, BORDER_RADIUS, FONT } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import {
  Button,
  Badge,
  Card,
  Input,
  Select,
  StatCard,
  TableWrap,
  Table,
  Th,
  Td,
} from '../components/ds';

const STATI_VERBALE = {
  da_scaricare: { label: 'Da Scaricare', variant: 'warning', icon: '📧' },
  salvato: { label: 'Documento salvato', variant: 'neutral', icon: '📄' },
  fattura_ricevuta: { label: 'Fattura Ricevuta', variant: 'info', icon: '📄' },
  pagato: { label: 'Pagato', variant: 'success', icon: '💳' },
  pagato_attesa_quietanza: {
    label: 'Pagato (att. quietanza)',
    variant: 'warning',
    icon: '⏳',
  },
  // Compatibilità di lettura finché la migrazione dei record storici termina.
  pagato_attesa_fattura: {
    label: 'Pagato (att. quietanza)',
    variant: 'warning',
    icon: '⏳',
  },
  riconciliato: { label: 'Riconciliato', variant: 'success', icon: '✅' },
  da_verificare: { label: 'Da verificare', variant: 'warning', icon: '⚠️' },
  sconosciuto: { label: 'Da verificare', variant: 'warning', icon: '⚠️' },
};

export default function VerbaliRiconciliazione() {
  const confirm = useConfirm();
  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState(null);
  const [verbali, setVerbali] = useState([]);
  const [filtroStato, setFiltroStato] = useState('');
  const [filtroTarga, setFiltroTarga] = useState('');
  const [soloRiconciliare, setSoloRiconciliare] = useState(false);
  const [ordinamento, setOrdinamento] = useState('data_verbale');
  const [selectedVerbale, setSelectedVerbale] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [collegandoDriver, setCollegandoDriver] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [checkingEmail, setCheckingEmail] = useState(false);
  const [migratingQuietanze, setMigratingQuietanze] = useState(false);

  // Nuovi state per associazione manuale
  const [dipendenti, setDipendenti] = useState([]);
  const [showAssociaModal, setShowAssociaModal] = useState(false);
  const [selectedTargaForAssoc, setSelectedTargaForAssoc] = useState('');
  const [selectedDriverId, setSelectedDriverId] = useState('');
  const [associating, setAssociating] = useState(false);

  const loadDashboard = useCallback(async () => {
    try {
      const res = await api.get('/api/verbali-riconciliazione/dashboard');
      setDashboard(res.data);
    } catch (e) {
      console.error('Error loading dashboard:', e);
    }
  }, []);

  const loadDipendenti = useCallback(async () => {
    try {
      const res = await api.get('/api/dipendenti');
      // Filtra solo dipendenti con nome valido
      const filtered = (res.data || []).filter(d => d.name || d.nome);
      setDipendenti(filtered);
    } catch (e) {
      console.error('Error loading dipendenti:', e);
    }
  }, []);

  const loadVerbali = useCallback(async () => {
    setLoading(true);
    try {
      let url = '/api/verbali-riconciliazione/lista?';
      if (filtroStato) url += `stato=${filtroStato}&`;
      if (filtroTarga) url += `targa=${filtroTarga}&`;
      if (soloRiconciliare) url += `da_riconciliare=true&`;
      url += `ordinamento=${ordinamento}&`;

      const res = await api.get(url);
      setVerbali(res.data.verbali || []);
    } catch (e) {
      console.error('Error loading verbali:', e);
      setError('Errore caricamento verbali');
    } finally {
      setLoading(false);
    }
  }, [filtroStato, filtroTarga, soloRiconciliare, ordinamento]);

  useEffect(() => {
    loadDashboard();
    loadVerbali();
    loadDipendenti();
  }, [loadDashboard, loadVerbali, loadDipendenti]);

  const handleScanFatture = async () => {
    setScanning(true);
    setError('');
    setSuccessMsg('');
    try {
      const res = await api.post('/api/verbali-riconciliazione/scan-fatture-verbali');
      setSuccessMsg(
        `Scan completato: ${res.data.fatture_analizzate} fatture, ${res.data.verbali_trovati} verbali trovati, ${res.data.associazioni_create} nuove associazioni`
      );
      loadDashboard();
      loadVerbali();
    } catch (e) {
      setError('Errore durante scan fatture');
    } finally {
      setScanning(false);
    }
  };

  const handleCheckEmail = async () => {
    setCheckingEmail(true);
    setError('');
    setSuccessMsg('');
    try {
      const res = await api.post('/api/verbali-riconciliazione/scan-email?days_back=30');
      const nuovi = res.data?.fase_2_nuovi?.verbali_nuovi || 0;
      const quietanze = res.data?.fase_1_completamenti?.quietanze_trovate || 0;
      setSuccessMsg(`Posta controllata: ${nuovi} nuovi verbali, ${quietanze} quietanze collegate.`);
      loadDashboard();
      loadVerbali();
    } catch (e) {
      setError(`Controllo posta non riuscito: ${e.response?.data?.detail || e.message}`);
    } finally {
      setCheckingEmail(false);
    }
  };

  const handleMigraQuietanze = async () => {
    setMigratingQuietanze(true);
    setError('');
    setSuccessMsg('');
    try {
      const res = await api.post('/api/verbali-riconciliazione/migra-attesa-quietanza');
      setSuccessMsg(
        `Stati aggiornati: ${res.data.zip_con_quietanza || 0} verbali ZIP pagati, ${res.data.in_attesa_quietanza || 0} in attesa quietanza.`
      );
      loadDashboard();
      loadVerbali();
    } catch (e) {
      setError(`Aggiornamento quietanze non riuscito: ${e.response?.data?.detail || e.message}`);
    } finally {
      setMigratingQuietanze(false);
    }
  };

  const handleCollegaDriver = async () => {
    setCollegandoDriver(true);
    setError('');
    setSuccessMsg('');
    try {
      const res = await api.post('/api/verbali-riconciliazione/collega-driver-massivo');
      setSuccessMsg(
        `Driver collegati: ${res.data.collegati_a_driver} verbali associati su ${res.data.verbali_analizzati} analizzati`
      );
      loadDashboard();
      loadVerbali();
    } catch (e) {
      setError('Errore durante collegamento driver');
    } finally {
      setCollegandoDriver(false);
    }
  };

  const [pulendoDuplicati, setPulendoDuplicati] = useState(false);

  const handlePulisciDuplicati = async () => {
    setPulendoDuplicati(true);
    setError('');
    setSuccessMsg('');
    try {
      const anteprima = await api.post('/api/verbali-riconciliazione/pulisci-duplicati?dry_run=true');
      const nGruppi = anteprima.data.gruppi_duplicati_trovati || 0;
      if (nGruppi === 0) {
        setSuccessMsg('Nessun verbale duplicato trovato');
        return;
      }
      // Azione distruttiva/irreversibile (unisce ed elimina righe duplicate): conferma esplicita obbligatoria.
      if (
        !(await confirm({
          title: 'Pulizia verbali duplicati',
          message: `Trovati ${nGruppi} verbali duplicati (${anteprima.data.documenti_eliminati} righe da unire). Procedere con la pulizia?`,
          variant: 'danger',
        }))
      ) {
        return;
      }
      const res = await api.post('/api/verbali-riconciliazione/pulisci-duplicati?dry_run=false');
      setSuccessMsg(
        `Puliti ${res.data.gruppi_processati} verbali duplicati (${res.data.documenti_eliminati} righe rimosse)`
      );
      loadDashboard();
      loadVerbali();
    } catch (e) {
      setError('Errore durante pulizia duplicati');
    } finally {
      setPulendoDuplicati(false);
    }
  };

  const handleRiconcilia = async numeroVerbale => {
    setError('');
    setSuccessMsg('');
    try {
      const encoded = encodeURIComponent(numeroVerbale);
      const preview = await api.post(
        `/api/verbali-riconciliazione/riconcilia/${encoded}?dry_run=true`
      );
      const proposte = preview.data.proposte || [];
      const blocchi = preview.data.motivi_blocco || [];
      if (proposte.length === 0) {
        setError(
          `Verbale ${numeroVerbale}: ${blocchi.join(' ') || 'nessuna prova univoca trovata; nessun dato modificato.'}`
        );
        return;
      }
      const confermato = await confirm({
        title: `Conferma collegamenti ${numeroVerbale}`,
        message: [
          ...proposte.map(item => `• ${item.descrizione}`),
          ...blocchi.map(item => `Blocco: ${item}`),
          'Il documento originale e gli importi non verificati non saranno modificati.',
        ].join('\n'),
        variant: 'warning',
      });
      if (!confermato) return;

      const res = await api.post(
        `/api/verbali-riconciliazione/riconcilia/${encoded}?dry_run=false`
      );
      setSuccessMsg(`Verbale ${numeroVerbale}: ${res.data.azioni?.join(', ') || 'Nessuna azione'}`);
      loadDashboard();
      loadVerbali();
      if (selectedVerbale?.numero_verbale === numeroVerbale) {
        setSelectedVerbale(res.data.verbale);
      }
    } catch (e) {
      setError(`Errore riconciliazione ${numeroVerbale}`);
    }
  };

  // Funzione per associare manualmente targa a driver
  const handleAssociaTargaDriver = async () => {
    if (!selectedTargaForAssoc || !selectedDriverId) {
      setError('Seleziona sia la targa che il driver');
      return;
    }

    setAssociating(true);
    setError('');
    try {
      const res = await api.post(
        `/api/auto-repair/collega-targa-driver?targa=${selectedTargaForAssoc}&driver_id=${selectedDriverId}`
      );
      setSuccessMsg(
        `Targa ${selectedTargaForAssoc} associata a ${res.data.driver}. ${res.data.verbali_aggiornati} verbali aggiornati.`
      );
      setShowAssociaModal(false);
      setSelectedTargaForAssoc('');
      setSelectedDriverId('');
      loadDashboard();
      loadVerbali();
    } catch (e) {
      setError(`Errore associazione: ${e.response?.data?.detail || e.message}`);
    } finally {
      setAssociating(false);
    }
  };

  // Ottieni targhe uniche senza driver dai verbali
  const getTargheSenzaDriver = () => {
    const targheSet = new Set();
    verbali.forEach(v => {
      if (v.targa && !v.driver_id) {
        targheSet.add(v.targa);
      }
    });
    return Array.from(targheSet).sort();
  };

  const getStatoInfo = stato => STATI_VERBALE[stato] || STATI_VERBALE['sconosciuto'];

  const renderImportoVerbale = verbale => {
    if (verbale.importo_verificato && verbale.importo !== null && verbale.importo !== undefined) {
      return formatEuro(verbale.importo);
    }
    if (verbale.importo_candidato_presente) {
      return <Badge variant="warning">OCR da verificare</Badge>;
    }
    return '-';
  };

  const renderDataVerbale = verbale => {
    if (verbale.data_verbale_verificata && verbale.data_verbale) {
      return formatDateIT(verbale.data_verbale);
    }
    if (verbale.data_verbale_candidato_presente) {
      return <Badge variant="warning">Data da verificare</Badge>;
    }
    return '-';
  };

  return (
    <PageLayout
      title="Riconciliazione Verbali Noleggio"
      subtitle="Gestione completa: Verbale → Fattura → Veicolo → Driver"
    >
      <div style={{ maxWidth: 1600, margin: '0 auto' }}>
        {/* Header con azioni */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            alignItems: 'center',
            marginBottom: 20,
            gap: 12,
            flexWrap: 'wrap',
          }}
        >
          <Button
            variant="primary"
            size="lg"
            onClick={handleCheckEmail}
            disabled={checkingEmail}
            data-testid="btn-controlla-email"
          >
            {checkingEmail ? '⏳ Controllo posta...' : '📧 Controlla adesso'}
          </Button>
          <Button
            variant="danger"
            size="lg"
            onClick={handleScanFatture}
            disabled={scanning}
            data-testid="btn-scan-fatture"
          >
            {scanning ? '⏳ Scanning...' : '🔍 Scan Fatture Noleggiatori'}
          </Button>
          <Button
            variant="info"
            size="lg"
            onClick={handleCollegaDriver}
            disabled={collegandoDriver}
            data-testid="btn-collega-driver"
          >
            {collegandoDriver ? '⏳ Collegando...' : '👤 Associa Driver'}
          </Button>
          <Button
            variant="success"
            size="lg"
            onClick={() => setShowAssociaModal(true)}
            data-testid="btn-associa-manuale"
          >
            🔗 Associazione Manuale
          </Button>
          <Button
            variant="secondary"
            size="lg"
            onClick={handleMigraQuietanze}
            disabled={migratingQuietanze}
            data-testid="btn-migra-quietanze"
            title="Sostituisce attesa fattura e riconosce le quietanze presenti nello ZIP"
          >
            {migratingQuietanze ? '⏳ Aggiornamento...' : '🧾 Aggiorna Quietanze'}
          </Button>
          <Button
            variant="secondary"
            size="lg"
            onClick={handlePulisciDuplicati}
            disabled={pulendoDuplicati}
            data-testid="btn-pulisci-duplicati"
            title="Unisce i verbali duplicati (stesso numero verbale in più righe)"
            style={{ background: COLORS.gray[500], color: '#fff', borderColor: COLORS.gray[500] }}
          >
            {pulendoDuplicati ? '⏳ Pulizia...' : '🧹 Pulisci Duplicati'}
          </Button>
        </div>

        {/* Modal Associazione Manuale */}
        {showAssociaModal && (
          <div
            style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: 'rgba(0,0,0,0.5)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 1000,
            }}
            onClick={() => setShowAssociaModal(false)}
          >
            <div
              style={{
                background: COLORS.card,
                borderRadius: BORDER_RADIUS.xl,
                padding: 24,
                width: '90%',
                maxWidth: 500,
                boxShadow: SHADOWS.modal,
              }}
              onClick={e => e.stopPropagation()}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 20,
                }}
              >
                <h2 style={{ margin: 0, fontSize: 20, fontWeight: 'bold', color: COLORS.primary }}>
                  🔗 Associa Targa a Driver
                </h2>
                <button
                  onClick={() => setShowAssociaModal(false)}
                  style={{
                    background: 'none',
                    border: 'none',
                    fontSize: 24,
                    cursor: 'pointer',
                    color: COLORS.textMuted,
                  }}
                >
                  ×
                </button>
              </div>

              <p style={{ fontSize: 14, color: COLORS.textMuted, marginBottom: 20 }}>
                Seleziona una targa e un driver per creare l'associazione. Tutti i verbali con
                questa targa verranno automaticamente collegati al driver.
              </p>

              <div style={{ marginBottom: 16 }}>
                <label
                  style={{
                    display: 'block',
                    fontSize: 14,
                    fontWeight: '600',
                    color: COLORS.gray[700],
                    marginBottom: 6,
                  }}
                >
                  Targa Veicolo
                </label>
                <Select
                  value={selectedTargaForAssoc}
                  onChange={e => setSelectedTargaForAssoc(e.target.value)}
                  style={{ width: '100%', padding: '12px 14px' }}
                  data-testid="select-targa-assoc"
                >
                  <option value="">-- Seleziona Targa --</option>
                  {getTargheSenzaDriver().map(t => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </Select>
              </div>

              <div style={{ marginBottom: 24 }}>
                <label
                  style={{
                    display: 'block',
                    fontSize: 14,
                    fontWeight: '600',
                    color: COLORS.gray[700],
                    marginBottom: 6,
                  }}
                >
                  Driver (Dipendente)
                </label>
                <Select
                  value={selectedDriverId}
                  onChange={e => setSelectedDriverId(e.target.value)}
                  style={{ width: '100%', padding: '12px 14px' }}
                  data-testid="select-driver-assoc"
                >
                  <option value="">-- Seleziona Driver --</option>
                  {dipendenti.map(d => (
                    <option key={d.id} value={d.id}>
                      {d.name || `${d.nome || ''} ${d.cognome || ''}`.trim()}
                    </option>
                  ))}
                </Select>
              </div>

              <div style={{ display: 'flex', gap: 12 }}>
                <Button variant="secondary" onClick={() => setShowAssociaModal(false)} style={{ flex: 1 }}>
                  Annulla
                </Button>
                <Button
                  variant="success"
                  onClick={handleAssociaTargaDriver}
                  disabled={associating || !selectedTargaForAssoc || !selectedDriverId}
                  style={{ flex: 1 }}
                  data-testid="btn-conferma-associazione"
                >
                  {associating ? '⏳ Associando...' : '✅ Associa'}
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Messaggi */}
        {error && (
          <div
            style={{
              padding: 16,
              background: COLORS.dangerLight,
              border: `1px solid ${COLORS.dangerLight}`,
              borderRadius: BORDER_RADIUS.md,
              color: COLORS.danger,
              marginBottom: 16,
            }}
          >
            ❌ {error}
            <button
              onClick={() => setError('')}
              style={{ float: 'right', background: 'none', border: 'none', cursor: 'pointer' }}
            >
              ✕
            </button>
          </div>
        )}
        {successMsg && (
          <div
            style={{
              padding: 16,
              background: COLORS.successLight,
              border: `1px solid ${COLORS.successLight}`,
              borderRadius: BORDER_RADIUS.md,
              color: COLORS.success,
              marginBottom: 16,
            }}
          >
            ✅ {successMsg}
            <button
              onClick={() => setSuccessMsg('')}
              style={{ float: 'right', background: 'none', border: 'none', cursor: 'pointer' }}
            >
              ✕
            </button>
          </div>
        )}

        {dashboard?.sorgenti?.avviso && (
          <Card
            role="status"
            aria-live="polite"
            style={{
              marginBottom: 20,
              borderLeft: `5px solid ${COLORS.warning}`,
              background: COLORS.warningLight,
            }}
          >
            <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
              <span aria-hidden="true" style={{ fontSize: 22, fontWeight: 800 }}>!</span>
              <div>
                <strong style={{ display: 'block', color: COLORS.text, marginBottom: 4 }}>
                  Sorgenti documentali da completare
                </strong>
                <span style={{ color: COLORS.textMuted }}>{dashboard.sorgenti.avviso}</span>
              </div>
            </div>
          </Card>
        )}

        {/* Dashboard Cards */}
        {dashboard && (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 16,
              marginBottom: 24,
            }}
          >
            <StatCard label="Totale Verbali" value={dashboard.riepilogo?.totale_verbali || 0} accent="danger" />
            <StatCard label="Da Riconciliare" value={dashboard.riepilogo?.da_riconciliare || 0} accent="warning" />
            <StatCard
              label="Riconciliati"
              value={dashboard.riepilogo?.per_stato?.riconciliato?.count || 0}
              accent="success"
            />
            <StatCard
              label="Importi verificati"
              value={formatEuro(dashboard.riepilogo?.totale_importo)}
              helper={`${dashboard.riepilogo?.importi_da_verificare || 0} importi OCR esclusi`}
              accent="info"
            />
          </div>
        )}

        {/* Filtri */}
        <Card style={{ marginBottom: 20 }}>
          <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
            <div>
              <label style={{ fontSize: 12, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}>
                Stato
              </label>
              <Select
                value={filtroStato}
                onChange={e => setFiltroStato(e.target.value)}
                style={{ minWidth: 180 }}
                data-testid="filtro-stato"
              >
                <option value="">Tutti gli stati</option>
                {Object.entries(STATI_VERBALE).map(([key, val]) => (
                  <option key={key} value={key}>
                    {val.icon} {val.label}
                  </option>
                ))}
              </Select>
            </div>

            <div>
              <label style={{ fontSize: 12, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}>
                Targa
              </label>
              <Input
                type="text"
                placeholder="es: GE911SC"
                value={filtroTarga}
                onChange={e => setFiltroTarga(e.target.value.toUpperCase())}
                style={{ width: 140 }}
                data-testid="filtro-targa"
              />
            </div>

            <div style={{ marginTop: 20 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={soloRiconciliare}
                  onChange={e => setSoloRiconciliare(e.target.checked)}
                  style={{ width: 18, height: 18 }}
                />
                <span style={{ fontSize: 14, fontWeight: '500' }}>Solo da riconciliare</span>
              </label>
            </div>

            <div>
              <label style={{ fontSize: 12, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}>
                Ordina per
              </label>
              <div style={{ display: 'flex', gap: 4 }}>
                {[
                  { key: 'numero_verbale', label: 'N. Verbale' },
                  { key: 'data_verbale', label: 'Data Verbale' },
                  { key: 'created_at', label: 'Inserimento' },
                ].map(opt => (
                  <Button
                    key={opt.key}
                    variant={ordinamento === opt.key ? 'primary' : 'secondary'}
                    size="sm"
                    onClick={() => setOrdinamento(opt.key)}
                    data-testid={`sort-${opt.key}`}
                  >
                    {opt.label}
                  </Button>
                ))}
              </div>
            </div>

            <Button variant="primary" onClick={loadVerbali} style={{ marginTop: 20, marginLeft: 'auto' }}>
              🔄 Aggiorna
            </Button>
          </div>
        </Card>

        {/* Content */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: selectedVerbale ? '1fr 400px' : '1fr',
            gap: 20,
          }}
        >
          {/* Lista Verbali */}
          <Card>
            <h2 style={{ margin: '0 0 16px 0', fontSize: 18, fontWeight: 'bold', color: COLORS.primary }}>
              📋 Verbali ({verbali.length})
            </h2>

            {loading ? (
              <div style={{ textAlign: 'center', padding: 40, color: COLORS.textMuted }}>
                ⏳ Caricamento...
              </div>
            ) : verbali.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 40, color: COLORS.textMuted }}>
                Nessun verbale trovato con i filtri selezionati
              </div>
            ) : (
              <TableWrap>
                <Table>
                  <thead>
                    <tr>
                      <Th>Verbale</Th>
                      <Th>Data</Th>
                      <Th>Targa</Th>
                      <Th>Driver</Th>
                      <Th>Fattura</Th>
                      <Th align="right">Importo</Th>
                      <Th align="center">Stato</Th>
                      <Th align="center">Azioni</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {verbali.map(v => {
                      const statoInfo = getStatoInfo(v.stato);
                      return (
                        <tr
                          key={v.id || v.numero_verbale}
                          style={{
                            background:
                              selectedVerbale?.numero_verbale === v.numero_verbale
                                ? COLORS.warningLight
                                : COLORS.card,
                            borderBottom: `1px solid ${COLORS.gray[100]}`,
                            cursor: 'pointer',
                          }}
                          onClick={() => setSelectedVerbale(v)}
                          data-testid={`verbale-row-${v.numero_verbale}`}
                        >
                          <Td style={{ fontWeight: 'bold', color: COLORS.danger, fontFamily: FONT.mono }}>
                            {v.numero_verbale}
                          </Td>
                          <Td>
                            <span style={{ fontSize: 12, color: COLORS.gray[600] }}>
                              {renderDataVerbale(v)}
                            </span>
                          </Td>
                          <Td>
                            <span style={{ fontWeight: '600', color: COLORS.primary }}>{v.targa || '-'}</span>
                          </Td>
                          <Td>
                            {v.driver_nome || v.driver ? (
                              <span
                                style={{
                                  fontWeight: '500',
                                  color: COLORS.success,
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 4,
                                }}
                              >
                                👤 {v.driver_nome || v.driver}
                              </span>
                            ) : (
                              <span style={{ color: COLORS.warning, fontStyle: 'italic', fontSize: 12 }}>
                                Da associare
                              </span>
                            )}
                          </Td>
                          <Td>
                            {v.fattura_numero ? (
                              <div>
                                <div style={{ fontWeight: '500' }}>{v.fattura_numero}</div>
                                <div style={{ fontSize: 11, color: COLORS.textSubtle }}>{v.fornitore}</div>
                              </div>
                            ) : (
                              <span style={{ color: COLORS.textSubtle }}>-</span>
                            )}
                          </Td>
                          <Td align="right" mono style={{ fontWeight: '600' }}>
                            {renderImportoVerbale(v)}
                          </Td>
                          <Td align="center">
                            <Badge variant={statoInfo.variant}>
                              {statoInfo.icon} {statoInfo.label}
                            </Badge>
                          </Td>
                          <Td align="center">
                            <Button
                              variant={v.stato === 'riconciliato' ? 'secondary' : 'info'}
                              size="sm"
                              onClick={e => {
                                e.stopPropagation();
                                handleRiconcilia(v.numero_verbale);
                              }}
                              disabled={v.stato === 'riconciliato'}
                              data-testid={`btn-riconcilia-${v.numero_verbale}`}
                            >
                              🔎 Cerca prove
                            </Button>
                          </Td>
                        </tr>
                      );
                    })}
                  </tbody>
                </Table>
              </TableWrap>
            )}
          </Card>

          {/* Dettaglio Verbale */}
          {selectedVerbale && (
            <Card>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 16,
                }}
              >
                <h2 style={{ margin: 0, fontSize: 16, fontWeight: 'bold', color: COLORS.primary }}>
                  📌 Dettaglio Verbale
                </h2>
                <button
                  onClick={() => setSelectedVerbale(null)}
                  style={{
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    fontSize: 18,
                    color: COLORS.textMuted,
                  }}
                >
                  ✕
                </button>
              </div>

              <div style={{ marginBottom: 16 }}>
                <div
                  style={{
                    fontSize: 20,
                    fontWeight: 'bold',
                    color: COLORS.danger,
                    fontFamily: FONT.mono,
                  }}
                >
                  {selectedVerbale.numero_verbale}
                </div>
                <div style={{ marginTop: 8 }}>
                  <Badge variant={getStatoInfo(selectedVerbale.stato).variant}>
                    {getStatoInfo(selectedVerbale.stato).icon} {getStatoInfo(selectedVerbale.stato).label}
                  </Badge>
                </div>
              </div>

              <div style={{ background: COLORS.bgAlt, borderRadius: BORDER_RADIUS.md, padding: 16 }}>
                <div style={{ display: 'grid', gap: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: COLORS.textMuted }}>Targa:</span>
                    <strong>{selectedVerbale.targa || '-'}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: COLORS.textMuted }}>Importo Verbale:</span>
                    <strong style={{ color: COLORS.danger }}>
                      {renderImportoVerbale(selectedVerbale)}
                    </strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: COLORS.textMuted }}>Importo Notifica:</span>
                    <strong>
                      {selectedVerbale.importo_notifica ? formatEuro(selectedVerbale.importo_notifica) : '-'}
                    </strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: COLORS.textMuted }}>Data Verbale:</span>
                    <strong>{renderDataVerbale(selectedVerbale)}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: COLORS.textMuted }}>Data Pagamento:</span>
                    <strong>{formatDateIT(selectedVerbale.data_pagamento) || '-'}</strong>
                  </div>
                </div>
              </div>

              {/* Fattura associata */}
              {selectedVerbale.fattura_numero && (
                <div style={{ marginTop: 16 }}>
                  <h4
                    style={{
                      margin: '0 0 8px 0',
                      fontSize: 14,
                      fontWeight: '600',
                      color: COLORS.primary,
                    }}
                  >
                    📄 Fattura Associata
                  </h4>
                  <div style={{ background: COLORS.infoLight, borderRadius: BORDER_RADIUS.md, padding: 12 }}>
                    <div style={{ fontWeight: 'bold' }}>{selectedVerbale.fattura_numero}</div>
                    <div style={{ fontSize: 12, color: COLORS.info }}>{selectedVerbale.fornitore}</div>
                  </div>
                </div>
              )}

              {/* Driver associato */}
              {selectedVerbale.driver_nome && (
                <div style={{ marginTop: 16 }}>
                  <h4
                    style={{
                      margin: '0 0 8px 0',
                      fontSize: 14,
                      fontWeight: '600',
                      color: COLORS.primary,
                    }}
                  >
                    👤 Driver Associato
                  </h4>
                  <div style={{ background: COLORS.successLight, borderRadius: BORDER_RADIUS.md, padding: 12 }}>
                    <div style={{ fontWeight: 'bold', color: COLORS.success }}>{selectedVerbale.driver_nome}</div>
                  </div>
                </div>
              )}

              {/* Azioni */}
              <div style={{ marginTop: 20, display: 'flex', gap: 10 }}>
                <Button
                  variant={selectedVerbale.stato === 'riconciliato' ? 'secondary' : 'info'}
                  onClick={() => handleRiconcilia(selectedVerbale.numero_verbale)}
                  disabled={selectedVerbale.stato === 'riconciliato'}
                  style={{ flex: 1 }}
                >
                  🔎 Cerca prove e proponi
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => window.open(`/verbali-noleggio/${selectedVerbale.numero_verbale}`, '_blank')}
                >
                  📄 Dettaglio
                </Button>
              </div>
            </Card>
          )}
        </div>

        {/* Info Box */}
        <div
          style={{
            marginTop: 24,
            padding: 20,
            background: COLORS.warningLight,
            borderRadius: BORDER_RADIUS.lg,
            fontSize: 14,
          }}
        >
          <h3 style={{ margin: '0 0 12px 0', fontSize: 16, color: COLORS.warning }}>
            ℹ️ Flusso Riconciliazione Verbali
          </h3>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
              gap: 16,
            }}
          >
            <div>
              <strong>📧 Scenario A - Pago Prima:</strong>
              <ol style={{ margin: '8px 0 0 16px', padding: 0, color: COLORS.warning }}>
                <li>Driver trova verbale sul parabrezza</li>
                <li>Pago subito (prima della fattura)</li>
                <li>Scarico da posta → Salvo verbale</li>
                <li>Arriva fattura → La associo</li>
                <li>Riconcilio: Verbale + Fattura + Pagamento</li>
              </ol>
            </div>
            <div>
              <strong>📄 Scenario B - Fattura Prima:</strong>
              <ol style={{ margin: '8px 0 0 16px', padding: 0, color: COLORS.warning }}>
                <li>Arriva fattura dal noleggiatore</li>
                <li>Estraggo numero verbale dalla descrizione</li>
                <li>Pago il verbale</li>
                <li>Riconcilio: Fattura + Verbale + Pagamento</li>
              </ol>
            </div>
          </div>
          <div style={{ marginTop: 12, fontSize: 13, color: COLORS.warning }}>
            <strong>Catena:</strong> Verbale → Fattura (spese notifica) → Veicolo (targa) → Driver (dipendente)
          </div>
        </div>
      </div>
    </PageLayout>
  );
}
