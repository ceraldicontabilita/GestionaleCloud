import React from 'react';
import { useNavigate } from 'react-router-dom';
import { LockKeyhole, Delete, X } from 'lucide-react';
import axios from 'axios';
import { createPinModal } from '../../../frontend_shared/PinModal';

const PinModal = createPinModal(React, { LockKeyhole, Delete, X });
const BACKEND_URL = process.env.REACT_APP_MENU_BACKEND_URL;

export default function AdminLoginPage() {
  const navigate = useNavigate();
  const login = async pin => {
    let response;
    try {
      response = await axios.post(`${BACKEND_URL}/api/qrcode/login`, { pin });
    } catch (error) {
      const detail = error?.response?.data?.detail;
      throw new Error(!error.response ? 'Connessione assente — riprova'
        : typeof detail === 'string' ? detail : 'Accesso non riuscito. Riprova.');
    }
    if (!response.data.success || !response.data.token) {
      throw new Error(response.data.message || 'PIN non valido');
    }
    localStorage.setItem('admin_token', response.data.token);
    navigate('/admin');
  };
  return <PinModal title="Accesso Menu" subtitle="Inserisci il PIN di GestionaleCloud"
    color="#5b7a6b" onVerify={login} />;
}
