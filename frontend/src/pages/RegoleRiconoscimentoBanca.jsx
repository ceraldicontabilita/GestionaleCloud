import React, { useCallback, useEffect, useMemo, useState } from 'react';
import api from '../api';
import { COLORS, BORDER_RADIUS } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { Button, Badge, Input, Select, StatCard, TableWrap, Table, Th, Td } from '../components/ds';

// Regole di riconoscimento IMPARATE per i movimenti bancari (19/09/2026):
// il titolare "insegna" a chi appartiene un movimento (es. "questo e' di
// Nexi") anche quando il motore generico lo riconoscerebbe solo con una
// parola chiave ("Commissioni bancarie"). La scelta si memorizza e vince
// sempre sul riconoscimento generico ai prossimi import; eliminarla non
// tocca i movimenti gia' categorizzati da essa.

function formattaData(valore) {
  const testo = String(valore || '').slice(0, 10);
  const [anno, mese, giorno] = testo.split('-');
  return anno && mese && giorno ? `${giorno}/${mese}/${anno}` : testo;
}

function formattaImporto(valore) {
  const numero = Number(valore || 0);
  return numero.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function nomeFornitore(fornitore) {
  return fornitore.denominazione || fornitore.ragione_sociale || fornitore.nome || fornitore.id;
}

function RigaInsegnaMovimento({ movimento, fornitori, onSalvato }) {
  const [fornitoreId, setFornitoreId] = useState('');
  const [categoriaLibera, setCategoriaLibera] = useState('');
  const [salvando, setSalvando] = useState(false);
  const [errore, setErrore] = useState('');

  const salva = async () => {
    const fornitore = fornitori.find(f => f.id === fornitoreId);
    if (!fornitore && !categoriaLibera.trim()) {
      setErrore('Scegli un fornitore o scrivi una categoria');
      return;
    }
    setSalvando(true);
    setErrore('');
    try {
      const payload = fornitore
        ? { entita_tipo: 'fornitore', entita_id: fornitore.id, entita_nome: nomeFornitore(fornitore) }
        : { entita_tipo: 'categoria', entita_nome: categoriaLibera.trim(), categoria: categoriaLibera.trim() };
      await api.post(`/api/regole-riconoscimento-banca/da-movimento/${encodeURIComponent(movimento.id)}`, payload);
      setFornitoreId('');
      setCategoriaLibera('');
      await onSalvato();
    } catch (err) {
      setErrore(err?.response?.data?.detail || 'Errore nel salvataggio della regola');
    }
    setSalvando(false);
  };

  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
      <Select
        value={fornitoreId}
        onChange={e => { setFornitoreId(e.target.value); if (e.target.value) setCategoriaLibera(''); }}
        style={{ minWidth: 170 }}
      >
        <option value="">-- fornitore --</option>
        {fornitori.map(f => (
          <option key={f.id} value={f.id}>{nomeFornitore(f)}</option>
        ))}
      </Select>
      <span style={{ color: COLORS.textMuted, fontSize: 12 }}>oppure</span>
      <Input
        placeholder="categoria libera"
        value={categoriaLibera}
        onChange={e => { setCategoriaLibera(e.target.value); if (e.target.value) setFornitoreId(''); }}
        style={{ minWidth: 130, width: 130 }}
      />
      <Button size="sm" variant="success" onClick={salva} disabled={salvando}>
        {salvando ? 'Salvo...' : 'A chi appartiene?'}
      </Button>
      {errore && <span style={{ color: COLORS.danger, fontSize: 12 }}>{errore}</span>}
    </div>
  );
}

export default function RegoleRiconoscimentoBanca() {
  const [movimenti, setMovimenti] = useState([]);
  const [fornitori, setFornitori] = useState([]);
  const [regole, setRegole] = useState([]);
  const [loading, setLoading] = useState(true);
  const [soloSenzaCategoria, setSoloSenzaCategoria] = useState(true);
  const [message, setMessage] = useState(null);

  const caricaMovimenti = useCallback(async () => {
    const res = await api.get('/api/estratto-conto-movimenti/movimenti', { params: { limit: 300 } });
    setMovimenti(res.data?.movimenti || []);
  }, []);

  const caricaRegole = useCallback(async () => {
    const res = await api.get('/api/regole-riconoscimento-banca');
    setRegole(res.data || []);
  }, []);

  const caricaFornitori = useCallback(async () => {
    const res = await api.get('/api/suppliers', { params: { limit: 500, attivo: true } });
    setFornitori(res.data || []);
  }, []);

  const caricaTutto = useCallback(async () => {
    try {
      await Promise.all([caricaMovimenti(), caricaRegole(), caricaFornitori()]);
    } catch (err) {
      console.error('Errore caricamento regole di riconoscimento banca:', err);
      setMessage({ type: 'error', text: 'Errore nel caricamento dei dati' });
    }
  }, [caricaMovimenti, caricaRegole, caricaFornitori]);

  useEffect(() => {
    setLoading(true);
    caricaTutto().finally(() => setLoading(false));
  }, [caricaTutto]);

  const handleSalvatoRegola = async () => {
    setMessage({ type: 'success', text: 'Regola salvata: applicata a questo movimento e ai prossimi simili' });
    await Promise.all([caricaMovimenti(), caricaRegole()]);
  };

  const handleEliminaRegola = async id => {
    if (!window.confirm(
      "Eliminare questa regola? I movimenti gia' categorizzati da essa restano come sono: "
      + 'la regola smette solo di applicarsi ai prossimi movimenti.'
    )) return;
    try {
      await api.delete(`/api/regole-riconoscimento-banca/${encodeURIComponent(id)}`);
      setMessage({ type: 'success', text: 'Regola eliminata' });
      await caricaRegole();
    } catch (err) {
      setMessage({ type: 'error', text: "Errore nell'eliminazione della regola" });
    }
  };

  const righeDaInsegnare = useMemo(() => {
    const lista = soloSenzaCategoria
      ? movimenti.filter(m => !m.categoria)
      : movimenti.filter(m => !m.categoria || m.categoria_auto);
    return lista.slice(0, 60);
  }, [movimenti, soloSenzaCategoria]);

  const senzaCategoriaTotale = useMemo(
    () => movimenti.filter(m => !m.categoria).length,
    [movimenti]
  );

  if (loading) {
    return (
      <PageLayout title="Regole di riconoscimento banca">
        <div style={{ padding: 24, textAlign: 'center', color: COLORS.textMuted }}>Caricamento...</div>
      </PageLayout>
    );
  }

  return (
    <PageLayout
      title="Regole di riconoscimento banca"
      subtitle="Insegna a chi appartiene un movimento: la scelta vince sempre sul riconoscimento generico"
    >
      <div data-testid="regole-riconoscimento-banca-page">
        {message && (
          <div
            style={{
              padding: 14,
              borderRadius: BORDER_RADIUS.md,
              marginBottom: 16,
              background: message.type === 'error' ? COLORS.dangerLight : COLORS.successLight,
              color: message.type === 'error' ? COLORS.danger : COLORS.success,
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }}
          >
            {message.text}
            <Button variant="ghost" size="sm" onClick={() => setMessage(null)}>chiudi</Button>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 24 }}>
          <StatCard label="Regole salvate" value={regole.length} accent="info" />
          <StatCard label="Movimenti recenti senza categoria" value={senzaCategoriaTotale} accent="warning" />
        </div>

        <section style={{ marginBottom: 32 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
            <h2 style={{ margin: 0, fontSize: 18, color: COLORS.text }}>Movimenti da insegnare</h2>
            <label style={{ fontSize: 13, color: COLORS.textMuted, display: 'flex', alignItems: 'center', gap: 6 }}>
              <input
                type="checkbox"
                checked={soloSenzaCategoria}
                onChange={e => setSoloSenzaCategoria(e.target.checked)}
              />
              Solo senza categoria (nascondi quelli gia' riconosciuti in automatico)
            </label>
          </div>
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th>Data</Th>
                  <Th>Causale</Th>
                  <Th align="right">Importo</Th>
                  <Th>Categoria attuale</Th>
                  <Th>A chi appartiene?</Th>
                </tr>
              </thead>
              <tbody>
                {righeDaInsegnare.map(m => (
                  <tr key={m.id}>
                    <Td style={{ whiteSpace: 'nowrap' }}>{formattaData(m.data)}</Td>
                    <Td style={{ maxWidth: 320 }} title={m.descrizione_originale || m.descrizione}>
                      {(m.descrizione_originale || m.descrizione || '').slice(0, 90)}
                    </Td>
                    <Td align="right" style={{ fontFamily: 'monospace' }}>
                      {formattaImporto(m.importo)}
                    </Td>
                    <Td>
                      {m.categoria
                        ? <Badge variant={m.categoria_auto ? 'info' : 'neutral'}>{m.categoria}</Badge>
                        : <Badge variant="warning">senza categoria</Badge>}
                    </Td>
                    <Td>
                      <RigaInsegnaMovimento movimento={m} fornitori={fornitori} onSalvato={handleSalvatoRegola} />
                    </Td>
                  </tr>
                ))}
                {righeDaInsegnare.length === 0 && (
                  <tr><Td colSpan={5} style={{ textAlign: 'center', color: COLORS.textMuted }}>
                    Nessun movimento da insegnare fra i {movimenti.length} piu' recenti
                  </Td></tr>
                )}
              </tbody>
            </Table>
          </TableWrap>
        </section>

        <section>
          <h2 style={{ margin: '0 0 12px', fontSize: 18, color: COLORS.text }}>Regole salvate</h2>
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th>Pattern</Th>
                  <Th>A chi appartiene</Th>
                  <Th>Categoria</Th>
                  <Th>Creata</Th>
                  <Th align="center">Azioni</Th>
                </tr>
              </thead>
              <tbody>
                {regole.map(r => (
                  <tr key={r.id}>
                    <Td style={{ fontWeight: 500 }}>{r.pattern}</Td>
                    <Td>
                      <Badge variant={r.entita_tipo === 'fornitore' ? 'info' : 'neutral'}>
                        {r.entita_nome || r.entita_id || '-'}
                      </Badge>
                    </Td>
                    <Td>{r.categoria || '-'}</Td>
                    <Td style={{ fontSize: 12, color: COLORS.textMuted }}>
                      {r.creata_il ? formattaData(r.creata_il) : '-'}{r.creata_da ? ` - ${r.creata_da}` : ''}
                    </Td>
                    <Td align="center">
                      <Button variant="danger" size="sm" onClick={() => handleEliminaRegola(r.id)}>
                        Elimina
                      </Button>
                    </Td>
                  </tr>
                ))}
                {regole.length === 0 && (
                  <tr><Td colSpan={5} style={{ textAlign: 'center', color: COLORS.textMuted }}>
                    Nessuna regola salvata
                  </Td></tr>
                )}
              </tbody>
            </Table>
          </TableWrap>
        </section>
      </div>
    </PageLayout>
  );
}
