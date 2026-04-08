import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import TopNav from './components/TopNav'
import Dipendenti from './pages/Dipendenti'
import DettaglioDipendente from './pages/DettaglioDipendente'
import Pignoramenti from './pages/Pignoramenti'
import Fatture from './pages/Fatture'
import Cedolini from './pages/Cedolini'
import EstrattoConto from './pages/EstrattoConto'
import F24Page from './pages/F24'
import AlertFiscali from './pages/AlertFiscali'
import F24PrivatiPage from './pages/F24Privati'
import Corrispettivi from './pages/Corrispettivi'
import Verbali from './pages/Verbali'
import Distinte from './pages/Distinte'
import ImportaDocumenti from './pages/ImportaDocumenti'
import Mittenti from './pages/Mittenti'
import { s } from './lib/utils'

export default function App() {
  return (
    <BrowserRouter>
      <div style={s.page}>
        <TopNav />
        <div style={s.container}>
          <Routes>
            <Route path="/" element={<Navigate to="/importa" replace />} />
            <Route path="/importa" element={<ImportaDocumenti />} />
            <Route path="/dipendenti" element={<Dipendenti />} />
            <Route path="/dipendenti/:id" element={<DettaglioDipendente />} />
            <Route path="/pignoramenti" element={<Pignoramenti />} />
            <Route path="/fatture" element={<Fatture />} />
            <Route path="/cedolini" element={<Cedolini />} />
            <Route path="/estratto-conto" element={<EstrattoConto />} />
            <Route path="/f24" element={<F24Page />} />
            <Route path="/corrispettivi" element={<Corrispettivi />} />
            <Route path="/verbali" element={<Verbali />} />
            <Route path="/distinte" element={<Distinte />} />
            <Route path="/mittenti" element={<Mittenti />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  )
}
