import React from 'react'
import { Landmark } from 'lucide-react'
import UploadPage from '../components/UploadPage'
import { formatEuro } from '../lib/utils'

const columns = [
  { key: 'data_operazione', label: 'Data' },
  { key: 'data_valuta', label: 'Valuta' },
  { key: 'descrizione', label: 'Descrizione' },
  { key: 'categoria', label: 'Categoria' },
  { key: 'dare', label: 'Dare', align: 'right', render: r => r.dare ? formatEuro(r.dare) : '' },
  { key: 'avere', label: 'Avere', align: 'right', render: r => r.avere ? formatEuro(r.avere) : '' },
]

export default function EstrattoConto() {
  return (
    <UploadPage
      title="Estratto Conto"
      icon={Landmark}
      acceptExt=".pdf"
      uploadUrl="/api/estratto-conto/upload-pdf"
      listUrl="/api/estratto-conto"
      columns={columns}
    />
  )
}
