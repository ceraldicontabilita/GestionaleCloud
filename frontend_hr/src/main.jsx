import React, { useEffect, useState } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import App from './App.jsx'
import PortaleDipendente from './PortaleDipendente.jsx'
import Landing from './Landing.jsx'
import { entraDalGestionale, loginGestionale } from './sessioneGruppo.js'
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
// Il gate controlla SIA il ruolo SIA la validità/scadenza del token (la
// protezione reale resta comunque lato server). Senza token valido
// l'amministratore non digita un secondo PIN: si prova la sessione del
// Gestionale e, se manca, si passa dal suo login che poi riporta qui.
function sessioneValida(roles) {
  const role = localStorage.getItem('pt_role')
  const token = localStorage.getItem('pt_token')
  if (!tokenValido(token)) {
    localStorage.removeItem('pt_token')
    localStorage.removeItem('pt_role')
    localStorage.removeItem('pt_name')
    return false
  }
  return roles.includes(role)
}

function RequireRole({ children, roles }) {
  const { pathname } = useLocation()
  const [stato, setStato] = useState(() => (sessioneValida(roles) ? 'ok' : 'verifica'))

  useEffect(() => {
    if (stato !== 'verifica') return
    let vivo = true
    entraDalGestionale().then((esito) => { if (vivo) setStato(esito) })
    return () => { vivo = false }
  }, [stato])

  if (stato === 'ok' && sessioneValida(roles)) return children
  if (stato === 'verifica') return <div className="muted" role="status" style={{ padding: 24, textAlign: 'center' }}>Verifica dell'accesso in corso…</div>
  if (stato === 'non_disponibile') return (
    <div style={{ padding: 24, textAlign: 'center' }}>
      <p>Servizio temporaneamente non disponibile.</p>
      <button className="btn" style={{ minHeight: 44 }} onClick={() => setStato('verifica')}>Riprova</button>
    </div>
  )
  // Nessuna sessione del Gestionale: chi puo' entrare solo nei Turni torna al
  // portale col proprio PIN, l'amministratore passa dal login del Gestionale.
  if (roles.includes('responsabile_turni')) return <Navigate to="/portale" replace />
  window.location.assign(loginGestionale(`/hr${pathname}`))
  return null
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
