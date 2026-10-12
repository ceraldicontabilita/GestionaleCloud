import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { EsitoSchedeFiscali, FiscalitaFornitore, SupplierModal } from './Fornitori';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
afterEach(cleanup);

const profilo = {
  partita_iva: '04225090156',
  attivita: 'Produzione e commercio di caramelle',
  stato: 'verificato',
  ateco: { codice: null, versione: '2025', stato: 'non_verificato' },
  regola_iva: 'merci_attivita',
  fonti: [{ url: 'https://www.perfetti.test/azienda', titolo: 'Sito ufficiale', verificata_il: '2026-10-12' }],
};

describe('fiscalità nell’anagrafica fornitori', () => {
  it('distingue attività verificata e ATECO non verificato, senza inventare una percentuale', () => {
    render(<FiscalitaFornitore profilo={profilo} />);
    expect(screen.getByText('Produzione e commercio di caramelle', { exact: false })).toBeTruthy();
    expect(screen.getByText('Verificate nelle fonti', { exact: false })).toBeTruthy();
    expect(screen.getByText('Non verificato · versione 2025', { exact: false })).toBeTruthy();
    expect(screen.getByText(/L’ATECO descrive l’attività del fornitore e non prova la detraibilità/)).toBeTruthy();
    expect(screen.queryByText(/100%/)).toBeNull();
    expect(screen.getByRole('link', { name: 'Sito ufficiale' }).href).toBe('https://www.perfetti.test/azienda');
  });

  it('non trasforma fonti con protocolli arbitrari in link cliccabili', () => {
    render(<FiscalitaFornitore profilo={{ ...profilo, fonti: [{ titolo: 'Fonte non valida', url: 'javascript:alert(1)' }] }} />);
    expect(screen.getByText('Fonte non valida')).toBeTruthy();
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('senza profilo lascia esplicita la verifica da fare', () => {
    render(<FiscalitaFornitore />);
    expect(screen.getByText(/Profilo fiscale da acquisire/)).toBeTruthy();
    expect(screen.queryByText(/100%/)).toBeNull();
  });

  it('il salvataggio degli altri dati non invia il profilo fiscale in sola lettura', () => {
    const save = vi.fn();
    render(<SupplierModal isOpen onClose={() => {}} onSave={save} saving={false}
      supplier={{ id: 's1', ragione_sociale: 'Perfetti', profilo_fiscale: profilo, email: 'prima@example.test' }} />);
    fireEvent.change(screen.getByDisplayValue('prima@example.test'), { target: { value: 'dopo@example.test' } });
    fireEvent.click(screen.getByRole('button', { name: 'Salva' }));
    expect(save.mock.calls[0][0].email).toBe('dopo@example.test');
    expect(save.mock.calls[0][0]).not.toHaveProperty('profilo_fiscale');
  });
});

describe('anteprima aggiornamento schede fiscali', () => {
  const report = { dry_run: true, da_aggiornare: 2, aggiornate: 0, invariate: 3, protette: 1,
    non_trovate: 4, conflitti: 1, dettagli: [{ nome: 'Perfetti', partita_iva: '04225090156', motivo: 'Profilo da aggiungere' }] };

  it('presenta il risultato prima di richiedere l’applicazione', () => {
    const apply = vi.fn();
    render(<EsitoSchedeFiscali report={report} onApply={apply} onClose={() => {}} />);
    expect(screen.getByText(/Questa anteprima non ha modificato dati/)).toBeTruthy();
    expect(screen.getByText(/Senza corrispondenza: 4 · Conflitti: 1/)).toBeTruthy();
    expect(apply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Applica a 2 schede' }));
    expect(apply).toHaveBeenCalledOnce();
  });

  it('non propone applicazioni dopo l’aggiornamento o senza schede da aggiornare', () => {
    const { rerender } = render(<EsitoSchedeFiscali report={{ ...report, da_aggiornare: 0 }} />);
    expect(screen.queryByRole('button', { name: /Applica/ })).toBeNull();
    rerender(<EsitoSchedeFiscali report={{ ...report, dry_run: false, aggiornate: 2 }} />);
    expect(screen.getByText('Schede fiscali aggiornate')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Applica/ })).toBeNull();
  });
});
