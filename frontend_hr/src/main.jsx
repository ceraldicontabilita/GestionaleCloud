import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import App from './App.jsx'
import PortaleDipendente from './PortaleDipendente.jsx'
import Landing from './Landing.jsx'
import './index.css'

// Legge la scadenza (exp) dal JWT senza verificarne la firma (la verifica vera
// è lato server). Serve solo a riportare al PIN quando la sessione è scaduta.
function tokenValido(token) {
  if (!token) return false
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return !payload.exp || payload.exp * 1000 > Date.now()
  } catch {
    return false
  }
}

// L'area gestione è riservata all'admin. Eccezione: il responsabile turni può
// entrare SOLO nella pagina Turni dell'azienda (nient'altro).
// Il gate controlla SIA il ruolo SIA la validità/scadenza del token: a sessione
// scaduta si torna al PIN (la protezione reale resta comunque lato server).
function RequireRole({ children, roles }) {
  const hasWindow = typeof window !== 'undefined'
  const role = hasWindow ? localStorage.getItem('pt_role') : null
  const token = hasWindow ? localStorage.getItem('pt_token') : null
  if (!roles.includes(role) || !tokenValido(token)) {
    if (hasWindow && !tokenValido(token)) {
      localStorage.removeItem('pt_token')
      localStorage.removeItem('pt_role')
      localStorage.removeItem('pt_name')
    }
    return <Navigate to="/portale" replace />
  }
  return children
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <BrowserRouter basename="/hr">
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/portale" element={<PortaleDipendente />} />
      <Route path="/dipendenti/turni" element={<RequireRole roles={['admin','responsabile_turni']}><App page="turni" /></RequireRole>} />
      <Route path="/dipendenti" element={<RequireRole roles={['admin']}><App page="dashboard" /></RequireRole>} />
      <Route path="/dipendenti/:page" element={<RequireRole roles={['admin']}><App /></RequireRole>} />
    </Routes>
  </BrowserRouter>
)
