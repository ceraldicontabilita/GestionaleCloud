import React, { useState } from 'react';
import {
  Search,
  Building2,
  MapPin,
  Mail,
  FileText,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Users,
  Euro,
} from 'lucide-react';
import api from '../api';
import { toast } from 'sonner';

export default function Visure() {
  const isMobile = useIsMobile();
  const [searchType, setSearchType] = useState('piva'); // piva | nome
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      toast.error('Inserisci un valore da cercare');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      if (searchType === 'piva') {
        const piva = searchQuery.replace(/\s/g, '');
        if (piva.length !== 11 || !/^\d+$/.test(piva)) {
          throw new Error('Partita IVA non valida (deve essere 11 cifre)');
        }

        const res = await api.get(`/api/openapi-imprese/info/${piva}?tipo=advanced`);
        setResult(res.data);
      } else {
        // Ricerca per nome
        const res = await api.get(
          `/api/openapi-imprese/cerca?query=${encodeURIComponent(searchQuery)}&limit=10`
        );
        setResult({ type: 'search', ...res.data });
      }
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Errore nella ricerca');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveToFornitori = async () => {
    if (!result?.data?.vatCode) {
      toast.error('Nessun dato da salvare');
      return;
    }

    try {
      setLoading(true);
      await api.post('/api/openapi-imprese/aggiorna-fornitore', {
        partita_iva: result.data.vatCode,
      });
      toast.success('Fornitore aggiornato/creato con successo!');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Errore nel salvataggio');
    } finally {
      setLoading(false);
    }
  };

  const renderCompanyInfo = (data, mappedData) => (
    <div
      style={{
        background: 'white',
        borderRadius: 16,
        padding: 24,
        boxShadow: '0 4px 20px rgba(0,0,0,0.08)',
      }}
    >
      {/* Header azienda */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          marginBottom: 24,
          paddingBottom: 24,
          borderBottom: '1px solid #e5e7eb',
        }}
      >
        <div>
          <h2
            style={{
              fontSize: 24,
              fontWeight: 700,
              color: '#111827',
              margin: 0,
              display: 'flex',
              alignItems: 'center',
              gap: 12,
            }}
          >
            <Building2 size={28} style={{ color: '#3b82f6' }} />
            {data.companyName}
          </h2>
          <p
            style={{
              color: '#6b7280',
              margin: '8px 0 0',
              fontSize: 14,
            }}
          >
            P.IVA: <strong style={{ fontFamily: 'monospace' }}>{data.vatCode}</strong>
            {data.taxCode && data.taxCode !== data.vatCode && (
              <>
                {' '}
                | C.F.: <strong style={{ fontFamily: 'monospace' }}>{data.taxCode}</strong>
              </>
            )}
          </p>
        </div>

        <div style={{ display: 'flex', gap: 12 }}>
          <span
            style={{
              padding: '8px 16px',
              borderRadius: 20,
              fontSize: 13,
              fontWeight: 600,
              background: data.activityStatus === 'ATTIVA' ? '#dcfce7' : '#fee2e2',
              color: data.activityStatus === 'ATTIVA' ? '#166534' : '#991b1b',
            }}
          >
            {data.activityStatus === 'ATTIVA' ? (
              <CheckCircle2 size={14} style={{ marginRight: 6 }} />
            ) : (
              <XCircle size={14} style={{ marginRight: 6 }} />
            )}
            {data.activityStatus || 'N/D'}
          </span>
        </div>
      </div>

      {/* Grid info */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)',
          gap: 20,
        }}
      >
        {/* Indirizzo */}
        <div
          style={{
            padding: 16,
            background: '#f8fafc',
            borderRadius: 12,
            border: '1px solid #e2e8f0',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <MapPin size={18} style={{ color: '#3b82f6' }} />
            <span style={{ fontWeight: 600, color: '#374151' }}>Sede Legale</span>
          </div>
          <p style={{ margin: 0, color: '#4b5563', fontSize: 14, lineHeight: 1.6 }}>
            {data.address?.registeredOffice?.streetName || '-'}
            <br />
            {data.address?.registeredOffice?.zipCode} {data.address?.registeredOffice?.town} (
            {data.address?.registeredOffice?.province})
          </p>
        </div>

        {/* Contatti */}
        <div
          style={{
            padding: 16,
            background: '#f8fafc',
            borderRadius: 12,
            border: '1px solid #e2e8f0',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Mail size={18} style={{ color: '#3b82f6' }} />
            <span style={{ fontWeight: 600, color: '#374151' }}>Contatti</span>
          </div>
          <p style={{ margin: 0, color: '#4b5563', fontSize: 14, lineHeight: 1.6 }}>
            <strong>SDI:</strong> {data.sdiCode || mappedData?.codice_sdi || '-'}
            <br />
            <strong>PEC:</strong> {mappedData?.pec || '-'}
          </p>
        </div>

        {/* Attività */}
        <div
          style={{
            padding: 16,
            background: '#f8fafc',
            borderRadius: 12,
            border: '1px solid #e2e8f0',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <FileText size={18} style={{ color: '#3b82f6' }} />
            <span style={{ fontWeight: 600, color: '#374151' }}>Attività</span>
          </div>
          <p style={{ margin: 0, color: '#4b5563', fontSize: 14, lineHeight: 1.6 }}>
            <strong>ATECO:</strong> {mappedData?.codice_ateco || '-'}
            <br />
            <span style={{ fontSize: 12 }}>{mappedData?.descrizione_ateco || '-'}</span>
          </p>
        </div>
      </div>

      {/* Dati economici se presenti */}
      {(mappedData?.fatturato || mappedData?.numero_dipendenti) && (
        <div
          style={{
            marginTop: 20,
            display: 'grid',
            gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)',
            gap: 20,
          }}
        >
          {mappedData?.fatturato && (
            <div
              style={{
                padding: 16,
                background: 'linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)',
                borderRadius: 12,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <Euro size={18} style={{ color: '#16a34a' }} />
                <span style={{ fontWeight: 600, color: '#166534' }}>Fatturato</span>
              </div>
              <p style={{ margin: 0, fontSize: 22, fontWeight: 700, color: '#166534' }}>
                €{Number(mappedData.fatturato).toLocaleString('it-IT')}
              </p>
            </div>
          )}

          {mappedData?.numero_dipendenti && (
            <div
              style={{
                padding: 16,
                background: 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)',
                borderRadius: 12,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <Users size={18} style={{ color: '#2563eb' }} />
                <span style={{ fontWeight: 600, color: '#1e40af' }}>Dipendenti</span>
              </div>
              <p style={{ margin: 0, fontSize: 22, fontWeight: 700, color: '#1e40af' }}>
                {mappedData.numero_dipendenti}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Azioni */}
      <div
        style={{
          marginTop: 24,
          paddingTop: 24,
          borderTop: '1px solid #e5e7eb',
          display: 'flex',
          justifyContent: 'flex-end',
          gap: 12,
        }}
      >
        <button
          onClick={handleSaveToFornitori}
          disabled={loading}
          style={{
            padding: '12px 24px',
            background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
            color: 'white',
            border: 'none',
            borderRadius: 10,
            cursor: 'pointer',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
          data-testid="btn-save-fornitore"
        >
          <CheckCircle2 size={18} />
          Salva in Fornitori
        </button>
      </div>
    </div>
  );

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1200, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1
          style={{
            fontSize: 28,
            fontWeight: 700,
            color: '#111827',
            margin: '0 0 8px 0',
          }}
        >
          🔍 Visure Aziendali
        </h1>
        <p style={{ color: '#6b7280', margin: 0 }}>
          Cerca informazioni su aziende italiane tramite Camera di Commercio
        </p>
      </div>

      {/* Search Box */}
      <div
        style={{
          background: 'white',
          borderRadius: 16,
          padding: 24,
          boxShadow: '0 4px 20px rgba(0,0,0,0.08)',
          marginBottom: 24,
        }}
      >
        <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
          <button
            onClick={() => setSearchType('piva')}
            style={{
              padding: '10px 20px',
              border: searchType === 'piva' ? '2px solid #3b82f6' : '2px solid #e5e7eb',
              background: searchType === 'piva' ? '#eff6ff' : 'white',
              color: searchType === 'piva' ? '#3b82f6' : '#6b7280',
              borderRadius: 10,
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            Partita IVA
          </button>
          <button
            onClick={() => setSearchType('nome')}
            style={{
              padding: '10px 20px',
              border: searchType === 'nome' ? '2px solid #3b82f6' : '2px solid #e5e7eb',
              background: searchType === 'nome' ? '#eff6ff' : 'white',
              color: searchType === 'nome' ? '#3b82f6' : '#6b7280',
              borderRadius: 10,
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            Nome Azienda
          </button>
        </div>

        <div style={{ display: 'flex', gap: 12 }}>
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onKeyPress={e => e.key === 'Enter' && handleSearch()}
            placeholder={searchType === 'piva' ? 'Es: 12485671007' : 'Es: OPENAPI SRL'}
            style={{
              flex: 1,
              padding: '14px 18px',
              border: '2px solid #e5e7eb',
              borderRadius: 12,
              fontSize: 16,
              fontFamily: searchType === 'piva' ? 'monospace' : 'inherit',
            }}
            data-testid="input-visura-search"
          />
          <button
            onClick={handleSearch}
            disabled={loading}
            style={{
              padding: '14px 28px',
              background: loading ? '#9ca3af' : 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)',
              color: 'white',
              border: 'none',
              borderRadius: 12,
              cursor: loading ? 'not-allowed' : 'pointer',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
            data-testid="btn-visura-search"
          >
            {loading ? <RefreshCw size={20} className="animate-spin" /> : <Search size={20} />}
            {loading ? 'Ricerca...' : 'Cerca'}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div
          style={{
            background: '#fef2f2',
            border: '1px solid #fecaca',
            borderRadius: 12,
            padding: 16,
            marginBottom: 24,
            color: '#991b1b',
          }}
        >
          <strong>Errore:</strong> {error}
        </div>
      )}

      {/* Risultato singola azienda */}
      {result &&
        result.success &&
        result.data &&
        !result.type &&
        renderCompanyInfo(result.data, result.campi_mappati)}

      {/* Risultati ricerca per nome */}
      {result && result.type === 'search' && (
        <div
          style={{
            background: 'white',
            borderRadius: 16,
            padding: 24,
            boxShadow: '0 4px 20px rgba(0,0,0,0.08)',
          }}
        >
          <h3 style={{ margin: '0 0 16px 0' }}>
            Trovati {result.count} risultati per "{searchQuery}"
          </h3>
          {result.results?.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {result.results.map((r, i) => (
                <div
                  key={i}
                  onClick={() => {
                    if (r.vatCode || r.id) {
                      setSearchType('piva');
                      setSearchQuery(r.vatCode || r.id);
                      handleSearch();
                    }
                  }}
                  style={{
                    padding: 16,
                    border: '1px solid #e5e7eb',
                    borderRadius: 10,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                  onMouseEnter={e => (e.target.style.background = '#f8fafc')}
                  onMouseLeave={e => (e.target.style.background = 'white')}
                >
                  <strong>{r.companyName || `ID: ${r.id}`}</strong>
                  {r.vatCode && (
                    <span style={{ marginLeft: 12, color: '#6b7280' }}>P.IVA: {r.vatCode}</span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p style={{ color: '#6b7280' }}>Nessun risultato trovato. Prova con la Partita IVA.</p>
          )}
        </div>
      )}
    </div>
  );
}
