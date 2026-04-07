import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import TopNav from './components/TopNav'
import Dipendenti from './pages/Dipendenti'
import DettaglioDipendente from './pages/DettaglioDipendente'
import Pignoramenti from './pages/Pignoramenti'
import { s } from './lib/utils'

export default function App() {
  return (
    <BrowserRouter>
      <div style={s.page}>
        <TopNav />
        <div style={s.container}>
          <Routes>
            <Route path="/" element={<Navigate to="/dipendenti" replace />} />
            <Route path="/dipendenti" element={<Dipendenti />} />
            <Route path="/dipendenti/:id" element={<DettaglioDipendente />} />
            <Route path="/pignoramenti" element={<Pignoramenti />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  )
}
