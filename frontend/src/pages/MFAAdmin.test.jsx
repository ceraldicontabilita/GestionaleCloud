import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import MFAAdmin from './MFAAdmin';

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

vi.mock('../api', () => ({
  default: { get: apiGet, post: apiPost },
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ applyMfaStepUp: vi.fn() }),
}));

describe('MFAAdmin', () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
    apiGet.mockResolvedValue({ data: { enabled: false } });
  });

  async function openSetup() {
    apiPost.mockResolvedValueOnce({
      data: {
        setup_id: 'TEST01',
        otpauth_uri: 'otpauth://totp/test?secret=AAAAAAAAAAAAAAAA',
        secret: 'AAAAAAAAAAAAAAAA',
      },
    });
    render(<MFAAdmin />);
    await screen.findByText('MFA non ancora configurata');
    fireEvent.click(screen.getByRole('button', { name: 'Configura MFA' }));
    return screen.findByLabelText('Codice numerico di 6 cifre generato da Authenticator');
  }

  it('mantiene il pulsante di attivazione accanto al campo e lo abilita con 6 cifre', async () => {
    const codeInput = await openSetup();
    const activate = screen.getByRole('button', { name: 'Attiva MFA' });

    expect(activate).toBeDisabled();
    fireEvent.change(codeInput, { target: { value: '123456' } });

    expect(activate).toBeEnabled();
    expect(activate.parentElement).toBe(codeInput.parentElement);
  });

  it('conferma anche premendo Invio e mostra un errore di rete distinto', async () => {
    const codeInput = await openSetup();
    apiPost.mockRejectedValueOnce({ request: {} });

    fireEvent.change(codeInput, { target: { value: '123456' } });
    fireEvent.keyDown(codeInput, { key: 'Enter', code: 'Enter' });

    await waitFor(() => expect(apiPost).toHaveBeenLastCalledWith('/api/auth/mfa/setup/confirm', { code: '123456' }));
    expect(await screen.findByText(/Il server non ha risposto/)).toBeInTheDocument();
  });
});
