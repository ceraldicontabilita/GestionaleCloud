import React from 'react';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { afterEach, describe, it, expect, vi } from 'vitest';
import PinModal from './PinModal';

afterEach(cleanup);

describe('Modale PIN comune', () => {
  it('accetta PIN lunghi senza inviare prematuramente alla sesta cifra', async () => {
    const verify = vi.fn().mockResolvedValue({});
    render(<PinModal onVerify={verify} />);
    fireEvent.change(screen.getByLabelText('PIN'), { target: { value: '12345678' } });
    expect(verify).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Accedi' }));
    await waitFor(() => expect(verify).toHaveBeenCalledWith('12345678', null));
    await waitFor(() => expect(screen.getByLabelText('PIN')).toHaveValue(''));
  });

  it('non invia due richieste mentre la verifica è in corso', async () => {
    let resolve;
    const verify = vi.fn(() => new Promise(r => { resolve = r; }));
    render(<PinModal onVerify={verify} />);
    fireEvent.change(screen.getByLabelText('PIN'), { target: { value: '1234' } });
    const form = screen.getByLabelText('PIN').closest('form');
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(verify).toHaveBeenCalledTimes(1);
    resolve({});
    await waitFor(() => expect(screen.getByRole('dialog')).toHaveAttribute('aria-busy', 'false'));
  });

  it('mantiene la scelta di identità e verifica nuovamente il PIN con ID', async () => {
    const verify = vi.fn().mockResolvedValueOnce({ choices: [{ id: 'op-a', name: 'Operatore A' }] }).mockResolvedValueOnce({});
    render(<PinModal onVerify={verify} />);
    fireEvent.change(screen.getByLabelText('PIN'), { target: { value: '1234' } });
    fireEvent.click(screen.getByRole('button', { name: 'Accedi' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Operatore A' }));
    await waitFor(() => expect(verify).toHaveBeenLastCalledWith('1234', 'op-a'));
  });

  it('mostra il blocco server e cancella il PIN dopo un errore', async () => {
    render(<PinModal onVerify={() => Promise.reject(new Error('Troppi tentativi'))} />);
    fireEvent.change(screen.getByLabelText('PIN'), { target: { value: '1234' } });
    fireEvent.click(screen.getByRole('button', { name: 'Accedi' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Troppi tentativi');
    expect(screen.getByLabelText('PIN')).toHaveValue('');
  });

  it('chiude con Escape, ripristina focus e scorrimento', () => {
    const trigger = document.createElement('button');
    document.body.appendChild(trigger);
    trigger.focus();
    const cancel = vi.fn();
    const { unmount } = render(<PinModal onVerify={vi.fn()} onCancel={cancel} />);
    expect(screen.getByLabelText('PIN')).toHaveFocus();
    fireEvent.keyDown(screen.getByLabelText('PIN'), { key: 'Escape' });
    expect(cancel).toHaveBeenCalledOnce();
    unmount();
    expect(trigger).toHaveFocus();
    expect(document.body.style.overflow).not.toBe('hidden');
    trigger.remove();
  });

  it('permette il tastierino, limita le cifre e non conserva il PIN in storage', () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem');
    render(<PinModal maxLength={4} onVerify={vi.fn()} />);
    for (const key of ['1','2','3','4','5']) fireEvent.click(screen.getByRole('button', { name: key, exact: true }));
    expect(screen.getByLabelText('PIN')).toHaveValue('1234');
    fireEvent.click(screen.getByRole('button', { name: 'Cancella ultima cifra' }));
    expect(screen.getByLabelText('PIN')).toHaveValue('123');
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
