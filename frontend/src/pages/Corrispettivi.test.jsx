import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import Corrispettivi, {
  chiaveCorrispettivo, imponibileItem, ivaItem, trovaCorrispettivo,
} from './Corrispettivi';

vi.mock('../api', () => ({
  default: { get: vi.fn() },
}));

vi.mock('../contexts/AnnoContext', () => ({
  useAnnoGlobale: () => ({ anno: 2026 }),
}));

const dueChiusure = [
  { id: 'corr-a', data: '2026-09-06', matricola_rt: 'RT-PRIMA', totale: 100, pagato_contanti: 100 },
  { id: 'corr-b', data: '2026-09-06', matricola_rt: 'RT-SECONDA', totale: 50, pagato_contanti: 50 },
];

describe('Due chiusure RT nello stesso giorno', () => {
  beforeEach(() => {
    window.location.hash = '';
    api.get.mockResolvedValue({ data: dueChiusure });
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
  });

  it('seleziona per id, non per data', () => {
    expect(chiaveCorrispettivo(dueChiusure[1])).toBe('corr-b');
    expect(trovaCorrispettivo(dueChiusure, 'corr-b')).toBe(dueChiusure[1]);
    // Un vecchio link con la data resta valido e apre la prima riga.
    expect(trovaCorrispettivo(dueChiusure, '2026-09-06')).toBe(dueChiusure[0]);
    expect(trovaCorrispettivo(dueChiusure, '')).toBeNull();
  });

  it('apre la seconda chiusura del giorno', async () => {
    render(<Corrispettivi />);
    const bottoni = await screen.findAllByRole('button', { name: 'Vedi corrispettivo 2026-09-06' });
    expect(bottoni).toHaveLength(2);

    fireEvent.click(bottoni[1]);

    expect(await screen.findByText('Matricola RT: RT-SECONDA')).toBeInTheDocument();
    expect(window.location.hash).toContain('selected=corr-b');
    const aperti = screen.getAllByRole('button', { name: 'Vedi corrispettivo 2026-09-06' })
      .filter(b => within(b).queryByText('Aperto'));
    expect(aperti).toHaveLength(1);
  });
});

describe('Compatibilita IVA corrispettivi storici', () => {
  it('riconosce il vecchio totale_iva che conteneva in realta imponibile', () => {
    const storico = { totale: 1851.71, totale_iva: 1683.37 };

    expect(imponibileItem(storico)).toBe(1683.37);
    expect(ivaItem(storico)).toBeCloseTo(168.34, 2);
  });

  it('mantiene separati imponibile e IVA nei record canonici', () => {
    const canonico = {
      totale: 110,
      totale_imponibile: 100,
      totale_iva: 10,
    };

    expect(imponibileItem(canonico)).toBe(100);
    expect(ivaItem(canonico)).toBe(10);
  });

  it('non riclassifica una vera IVA priva di imponibile', () => {
    const parziale = { totale: 110, totale_iva: 10 };

    expect(imponibileItem(parziale)).toBe(0);
    expect(ivaItem(parziale)).toBe(10);
  });
});
