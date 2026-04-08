import React from 'react'
import { Receipt } from 'lucide-react'
import UploadPage from '../components/UploadPage'
import { formatEuro, colors } from '../lib/utils'

const TIPO_BADGE = {
  normale:         { label: 'Normale',         color: colors.success,  bg: '#dcfce7' },
  acconto:         { label: 'Acconto',          color: '#d97706',       bg: '#fef3c7' },
  saldo:           { label: 'Saldo',            color: '#2563eb',       bg: '#dbeafe' },
  tredicesima:     { label: '13ª',              color: '#7c3aed',       bg: '#ede9fe' },
  quattordicesima: { label: '14ª',              color: '#7c3aed',       bg: '#ede9fe' },
}

const columns = [
  {
    key: 'periodo', label: 'Periodo',
    render: r => r.mese && r.anno ? `${String(r.mese).padStart(2,'0')}/${r.anno}` : '—'
  },
  { key: 'cognome', label: 'Cognome' },
  { key: 'nome', label: 'Nome' },
  { key: 'codice_fiscale', label: 'C.F.', mono: true },
  {
    key: 'tipo_erogazione', label: 'Tipo',
    render: r => {
      const cfg = TIPO_BADGE[r.tipo_erogazione] || TIPO_BADGE.normale
      return (
        <span style={{ fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 10,
          color: cfg.color, background: cfg.bg }}>
          {cfg.label}
        </span>
      )
    }
  },
  { key: 'lordo',  label: 'Lordo',  align: 'right', render: r => formatEuro(r.lordo) },
  { key: 'netto',  label: 'Netto',  align: 'right', render: r => formatEuro(r.netto) },
  { key: 'irpef',  label: 'IRPEF',  align: 'right', render: r => formatEuro(r.irpef) },
  {
    key: 'irpef_acconto', label: 'Acc. IRPEF', align: 'right',
    render: r => r.irpef_acconto ? formatEuro(r.irpef_acconto) : '—'
  },
  {
    key: 'contributi_inps', label: 'INPS dip.', align: 'right',
    render: r => r.contributi_inps ? formatEuro(r.contributi_inps) : '—'
  },
  {
    key: 'irpef_addizionale_regionale', label: 'Add. Reg.', align: 'right',
    render: r => r.irpef_addizionale_regionale ? formatEuro(r.irpef_addizionale_regionale) : '—'
  },
  {
    key: 'anticipi_tfr', label: 'Ant. TFR', align: 'right',
    render: r => r.anticipi_tfr ? formatEuro(r.anticipi_tfr) : '—'
  },
]

export default function Cedolini() {
  return (
    <UploadPage
      title="Cedolini"
      icon={Receipt}
      acceptExt=".pdf"
      uploadUrl="/api/cedolini/upload-pdf"
      listUrl="/api/cedolini"
      columns={columns}
    />
  )
}
