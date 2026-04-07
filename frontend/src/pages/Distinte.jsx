import React from 'react'
import { Banknote } from 'lucide-react'
import UploadPage from '../components/UploadPage'
import { formatEuro } from '../lib/utils'

const columns = [
  { key: 'data_distinta', label: 'Data' },
  { key: 'n_pagamenti', label: 'N° pagamenti' },
  { key: 'totale', label: 'Totale', align: 'right', render: r => formatEuro(r.totale) },
  { key: 'banca', label: 'Banca', render: r => r.banca || 'Banco BPM' },
  { key: 'riconciliati', label: 'Riconciliati', render: r => r.riconciliati || 0 },
  { key: 'filename', label: 'File', mono: true },
]

export default function Distinte() {
  return (
    <UploadPage
      title="Distinte Pagamento"
      icon={Banknote}
      acceptExt=".pdf"
      uploadUrl="/api/distinte/upload-pdf"
      listUrl="/api/distinte"
      columns={columns}
    />
  )
}
