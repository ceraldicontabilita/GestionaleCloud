import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Login from './Login';

const auth = vi.hoisted(() => ({
  loginWithPin: vi.fn(), verifyMfaLogin: vi.fn(), isAuthenticated: false,
}));
const navigate = vi.hoisted(() => vi.fn());
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }));

describe('PIN condiviso e MFA ERP', () => {
  beforeEach(() => vi.clearAllMocks());

  it('non apre ERP prima della verifica MFA richiesta dal server', async () => {
    auth.loginWithPin.mockResolvedValue({ mfa_required: true, challenge_token: 'synthetic-challenge' });
    auth.verifyMfaLogin.mockResolvedValue({});
    render(<Login />);
    fireEvent.change(screen.getByLabelText('PIN'), { target: { value: '74926183' } });
    fireEvent.click(screen.getByRole('button', { name: 'Accedi' }));
    const code = await screen.findByLabelText('Codice MFA');
    expect(auth.loginWithPin).toHaveBeenCalledWith('74926183');
    expect(navigate).not.toHaveBeenCalled();
    fireEvent.change(code, { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: 'Verifica e accedi' }));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/', { replace: true }));
    expect(auth.verifyMfaLogin).toHaveBeenCalledWith('synthetic-challenge', '123456');
  });

  it('mostra il blocco tentativi senza navigare', async () => {
    auth.loginWithPin.mockRejectedValue({ response: { status: 429, data: { detail: 'Troppi tentativi' } } });
    render(<Login />);
    fireEvent.change(screen.getByLabelText('PIN'), { target: { value: '74926183' } });
    fireEvent.click(screen.getByRole('button', { name: 'Accedi' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Troppi tentativi');
    expect(navigate).not.toHaveBeenCalled();
    expect(screen.getByLabelText('PIN')).toHaveValue('');
  });
});
