import React, { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import SelettorPeriodo from './SelettorPeriodo';
import { statoMese } from '../../lib/periodoCommercialista';

function Prova({ iniziale, onAnno = () => {} }) {
  const [stato, setStato] = useState(iniziale);
  return <SelettorPeriodo stato={stato} anno={2026} onChange={setStato} onAnno={onAnno} />;
}

describe('SelettorPeriodo', () => {
  it('mese: tendina del mese e riepilogo per esteso', () => {
    render(<Prova iniziale={statoMese(2026, 9)} />);
    expect(screen.getByRole('radio', { name: 'Mese' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByLabelText('Mese')).toHaveValue('9');
    expect(screen.getByTestId('periodo-riepilogo')).toHaveTextContent('Settembre 2026: dal 01/09/2026 al 30/09/2026');
  });

  it('trimestre: scelta I-IV', () => {
    render(<Prova iniziale={statoMese(2026, 9)} />);
    fireEvent.click(screen.getByRole('radio', { name: 'Trimestre' }));
    fireEvent.change(screen.getByLabelText('Trimestre'), { target: { value: '4' } });
    expect(screen.getByTestId('periodo-riepilogo')).toHaveTextContent('4° trimestre 2026: dal 01/10/2026 al 31/12/2026');
  });

  it('anno: intero anno e cambio anno verso il selettore globale', () => {
    const onAnno = vi.fn();
    render(<Prova iniziale={statoMese(2026, 9)} onAnno={onAnno} />);
    fireEvent.click(screen.getByRole('radio', { name: 'Anno' }));
    expect(screen.getByTestId('periodo-riepilogo')).toHaveTextContent('Intero anno 2026: dal 01/01/2026 al 31/12/2026');
    fireEvent.change(screen.getByLabelText('Anno'), { target: { value: '2025' } });
    expect(onAnno).toHaveBeenCalledWith(2025);
  });

  it('personalizzato: due date gg/mm/aaaa con le barre inserite da sole', () => {
    render(<Prova iniziale={statoMese(2026, 9)} />);
    fireEvent.click(screen.getByRole('radio', { name: 'Personalizzato' }));
    fireEvent.change(screen.getByLabelText('Dal'), { target: { value: '15082026' } });
    fireEvent.change(screen.getByLabelText('Al'), { target: { value: '05092026' } });
    expect(screen.getByLabelText('Dal')).toHaveValue('15/08/2026');
    expect(screen.getByTestId('periodo-riepilogo')).toHaveTextContent('dal 15/08/2026 al 05/09/2026');
  });

  it('personalizzato: date invertite = avviso scritto, non solo colore', () => {
    render(<Prova iniziale={statoMese(2026, 9)} />);
    fireEvent.click(screen.getByRole('radio', { name: 'Personalizzato' }));
    fireEvent.change(screen.getByLabelText('Dal'), { target: { value: '05092026' } });
    fireEvent.change(screen.getByLabelText('Al'), { target: { value: '15082026' } });
    expect(screen.getByRole('alert')).toHaveTextContent(/dopo/);
  });
});
