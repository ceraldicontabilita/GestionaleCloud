import React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import api from '../../api';
import CollectionDossier from './CollectionDossier';

vi.mock('../../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const dossier = (changes = {}) => ({
  claim_id: 'cartella/1', collection_number: '123456',
  path: { code: 'ORDINARY_TAX', label: 'Controllo fiscale e cartella', steps: [
    { code: 'ORIGIN', label: 'Obbligo originario', status: 'DOCUMENTED' },
    { code: 'NOTICE', label: 'Avviso bonario', status: 'NOT_DOCUMENTED' },
    { code: 'ROLE', label: 'Ruolo', status: 'NOT_DOCUMENTED' },
  ] },
  timeline: [
    { id: 'model', event_type: 'F24_MODEL', label: 'Modello F24 del commercialista',
      date: '2022-02-14', date_kind: 'PREPARATION_DATE', evidence_level: 'MODEL_ONLY',
      document_id: 'F24-1', url: '/api/originale/f24/F24-1', filename: 'F24 storico.pdf', amount_cents: 100000 },
    { id: 'receipt', event_type: 'QUIETANZA_F24', label: 'Quietanza parziale da attribuire',
      date: '2023-01-16', date_kind: 'PAYMENT_DATE', evidence_level: 'DOCUMENTARY',
      document_id: 'Q-1', amount_cents: 40000, notes: ['Quota da attribuire: non chiude il debito originario.'] },
    { id: 'bank', event_type: 'BANK_MATCH', label: 'Movimento collegato alla quietanza',
      date: '2023-01-18', date_kind: 'BANK_BOOKING_DATE', evidence_level: 'BANK' },
    { id: 'snapshot', event_type: 'PORTAL_SNAPSHOT', label: 'Situazione acquisita da AdeR',
      date: '2024-06-01', date_kind: 'PORTAL_CAPTURE_DATE', evidence_level: 'PORTAL',
      notes: ['Residuo del portale: 0,00 €. Il solo saldo non prova il pagamento.'] },
  ],
  undated: [{ id: 'role', event_type: 'ROLE', label: 'Estratto del ruolo senza data',
    date: null, date_kind: null, evidence_level: 'EVENT', document_id: 'ROLE-1' }],
  findings: [{ code: 'PARTIAL', severity: 'warning', message: 'Pagamento parziale: verificare il residuo e gli accessori.' }],
  safety: { payment_inferred: false, requests_submitted: false },
  ...changes,
});

const openDossier = () => fireEvent.click(screen.getByText('Cronologia del fascicolo'));

describe('Cronologia della posizione di riscossione', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    api.get.mockResolvedValue({ data: dossier() });
  });

  it('carica soltanto all’apertura e riusa il fascicolo già caricato', async () => {
    render(<CollectionDossier claimId="cartella/1" />);
    expect(api.get).not.toHaveBeenCalled();
    openDossier();
    await screen.findByText('Modello F24 del commercialista');
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(api.get).toHaveBeenCalledWith('/api/fiscal/collections/cartella%2F1/dossier');
    openDossier();
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Documenti in ordine di data' })).not.toBeInTheDocument());
    openDossier();
    await screen.findByText('Modello F24 del commercialista');
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(api.post).not.toHaveBeenCalled();
  });

  it('mantiene l’ordine ricevuto, le diverse date e i documenti senza data separati', async () => {
    render(<CollectionDossier claimId="cartella/1" />);
    openDossier();
    const timeline = await screen.findByRole('region', { name: 'Documenti in ordine di data' });
    const events = within(timeline).getAllByRole('listitem');
    expect(events).toHaveLength(4);
    expect(events[0]).toHaveTextContent('14/02/2022 · Modello F24 del commercialista');
    expect(events[0]).toHaveTextContent('Data di predisposizione');
    expect(events[1]).toHaveTextContent('16/01/2023 · Quietanza parziale da attribuire');
    expect(events[1]).toHaveTextContent('Data del pagamento');
    expect(events[2]).toHaveTextContent('Data contabile bancaria');
    expect(events[3]).toHaveTextContent('Data della consultazione');
    const undated = screen.getByRole('region', { name: 'Documenti senza data documentata' });
    expect(within(undated).getByText('Estratto del ruolo senza data')).toBeInTheDocument();
    expect(undated.querySelector('time')).toBeNull();
    expect(within(timeline).queryByText('Estratto del ruolo senza data')).not.toBeInTheDocument();
  });

  it('distingue modello, quietanza, banca e portale senza dichiarare pagata la cartella', async () => {
    render(<CollectionDossier claimId="cartella/1" />);
    openDossier();
    await screen.findByText('Modello: non prova il pagamento');
    expect(screen.getByText('Quietanza documentale')).toBeInTheDocument();
    expect(screen.getByText('Movimento bancario')).toBeInTheDocument();
    expect(screen.getByText('Fotografia del portale')).toBeInTheDocument();
    expect(screen.getByText('Quota da attribuire: non chiude il debito originario.')).toBeInTheDocument();
    expect(screen.getByText('Pagamento parziale: verificare il residuo e gli accessori.')).toBeInTheDocument();
    expect(screen.queryByText(/^(pagato|pagata|chiusa|sgravio inviato)$/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Il collegamento non invia richieste di sgravio/)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('distingue il documento mancante dal passaggio non previsto senza inventarne l’assenza storica', async () => {
    api.get.mockResolvedValue({ data: dossier({ path: { code: 'INPS', label: 'Avviso di addebito INPS', steps: [
      { code: 'NOTICE', label: 'Avviso bonario', status: 'NOT_DOCUMENTED' },
      { code: 'ROLE', label: 'Ruolo separato', status: 'NOT_APPLICABLE' },
      { code: 'ENFORCEABLE_NOTICE', label: 'Avviso di addebito', status: 'DOCUMENTED' },
    ] } }) });
    render(<CollectionDossier claimId="cartella/1" />);
    openDossier();
    await screen.findByText('Avviso di addebito INPS');
    const path = screen.getByRole('region', { name: 'Percorso della posizione' });
    expect(within(path).getByText('Avviso bonario').closest('li')).toHaveTextContent('Documento non presente nel fascicolo');
    expect(within(path).getByText('Ruolo separato').closest('li')).toHaveTextContent('Passaggio non previsto per questo percorso');
    expect(within(path).getByText('Avviso di addebito').closest('li')).toHaveTextContent('Documento presente');
    expect(within(path).getByText(/non dimostra che il passaggio non sia avvenuto/)).toBeInTheDocument();
    expect(screen.queryByText(/NOT_DOCUMENTED|NOT_APPLICABLE|DOCUMENTED/)).not.toBeInTheDocument();
  });

  it('apre il modello con il suo URL canonico e gli altri documenti nel visualizzatore esistente', async () => {
    const onOpen = vi.fn();
    const onOpenUrl = vi.fn();
    render(<CollectionDossier claimId="cartella/1" onOpen={onOpen} onOpenUrl={onOpenUrl} />);
    openDossier();
    fireEvent.click(await screen.findByRole('button', { name: 'Apri F24 storico.pdf' }));
    expect(onOpenUrl).toHaveBeenCalledWith('/api/originale/f24/F24-1', 'F24 storico.pdf');
    expect(onOpen).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Apri Quietanza parziale da attribuire' }));
    expect(onOpen).toHaveBeenCalledWith('Q-1', 'Quietanza parziale da attribuire');
    fireEvent.click(screen.getByRole('button', { name: 'Apri Estratto del ruolo senza data' }));
    expect(onOpen).toHaveBeenLastCalledWith('ROLE-1', 'Estratto del ruolo senza data');
  });

  it('non passa URL esterni o eseguibili al client autenticato', async () => {
    const onOpenUrl = vi.fn();
    api.get.mockResolvedValue({ data: dossier({ undated: [], timeline: [
      { id: 'external', label: 'Documento esterno', evidence_level: 'EVENT', url: 'https://other.example/api/private' },
      { id: 'script', label: 'Documento non valido', evidence_level: 'EVENT', url: 'javascript:alert(1)' },
      { id: 'relative-host', label: 'Altro host', evidence_level: 'EVENT', url: '//other.example/api/private' },
      { id: 'backslash', label: 'Indirizzo ambiguo', evidence_level: 'EVENT', url: '/api/\\other.example/private' },
    ] }) });
    render(<CollectionDossier claimId="cartella/1" onOpenUrl={onOpenUrl} />);
    openDossier();
    await screen.findByText('Documento esterno');
    expect(screen.queryByRole('button', { name: /Apri/ })).not.toBeInTheDocument();
    expect(onOpenUrl).not.toHaveBeenCalled();
  });

  it('mostra caricamento, errore e permette di riprovare senza mutare la posizione', async () => {
    let reject;
    api.get.mockImplementationOnce(() => new Promise((resolve, rejectRequest) => { reject = rejectRequest; }));
    render(<CollectionDossier claimId="cartella/1" />);
    openDossier();
    expect(await screen.findByRole('status')).toHaveTextContent('Caricamento della cronologia');
    await act(async () => reject(new Error('offline')));
    expect(await screen.findByRole('alert')).toHaveTextContent('Non è stato possibile caricare');
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Riprova' }));
    await screen.findByText('Modello F24 del commercialista');
    expect(api.get).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('non mostra un documento inventato quando il fascicolo non ha eventi datati', async () => {
    api.get.mockResolvedValue({ data: dossier({ timeline: [], undated: [], findings: [] }) });
    render(<CollectionDossier claimId="cartella/1" />);
    openDossier();
    expect(await screen.findByText('Nessun documento con data documentata presente nel fascicolo.')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Documenti senza data documentata' })).not.toBeInTheDocument();
  });

  it('aggiorna su richiesta mostrando i nuovi documenti senza registrare pagamenti', async () => {
    const updated = dossier();
    updated.timeline = [...updated.timeline, {
      id: 'new-receipt', event_type: 'QUIETANZA_F24', label: 'Nuova quietanza acquisita',
      date: '2026-10-17', date_kind: 'PAYMENT_DATE', evidence_level: 'DOCUMENTARY',
    }];
    api.get.mockResolvedValueOnce({ data: dossier() }).mockResolvedValueOnce({ data: updated });
    render(<CollectionDossier claimId="cartella/1" />);
    openDossier();
    fireEvent.click(await screen.findByRole('button', { name: 'Aggiorna cronologia' }));
    expect(await screen.findByText('Nuova quietanza acquisita')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledTimes(2);
    expect(api.get).toHaveBeenNthCalledWith(2, '/api/fiscal/collections/cartella%2F1/dossier');
    expect(api.post).not.toHaveBeenCalled();
  });

  it('un originale dell’avviso non viene etichettato come quietanza', async () => {
    api.get.mockResolvedValue({ data: dossier({ undated: [], timeline: [{
      id: 'notice', event_type: 'ORIGINAL_NOTICE', label: 'Avviso bonario originale',
      date: '2023-01-01', date_kind: 'DOCUMENT_DATE', evidence_level: 'DOCUMENTARY',
    }] }) });
    render(<CollectionDossier claimId="cartella/1" />);
    openDossier();
    await screen.findByText('Avviso bonario originale');
    expect(screen.getByText('Prova documentale')).toBeInTheDocument();
    expect(screen.queryByText('Quietanza documentale')).not.toBeInTheDocument();
  });

  it('ignora risposte tardive della posizione precedente', async () => {
    let resolvePrevious;
    api.get.mockImplementationOnce(() => new Promise(resolve => { resolvePrevious = resolve; }));
    const { rerender } = render(<CollectionDossier claimId="cartella/1" />);
    openDossier();
    await screen.findByRole('status');
    api.get.mockResolvedValueOnce({ data: dossier({ claim_id: 'cartella/2', timeline: [], undated: [] }) });
    rerender(<CollectionDossier claimId="cartella/2" />);
    await screen.findByText('Nessun documento con data documentata presente nel fascicolo.');
    await act(async () => resolvePrevious({ data: dossier() }));
    expect(screen.queryByText('Modello F24 del commercialista')).not.toBeInTheDocument();
    expect(api.get).toHaveBeenLastCalledWith('/api/fiscal/collections/cartella%2F2/dossier');
  });
});
