import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { PageLayout } from '../components/PageLayout';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { Badge } from '../components/ui/badge';
import { Download, RefreshCw, FileText, Mail, Search, Play, CheckCircle, XCircle, Loader2, Eye } from 'lucide-react';
import api from '../api';
import { STYLES, COLORS, button, badge, formatEuro, formatDateIT } from '../lib/utils';

const CATEGORIES = {
  f24: { label: 'F24', color: 'bg-blue-500' },
  fattura: { label: 'Fattura', color: 'bg-green-500' },
  busta_paga: { label: 'Busta Paga', color: 'bg-purple-500' },
  estratto_conto: { label: 'Estratto Conto', color: 'bg-orange-500' },
  quietanza: { label: 'Quietanza', color: 'bg-cyan-500' },
  bonifico: { label: 'Bonifico', color: 'bg-indigo-500' },
  verbale: { label: 'Verbale', color: 'bg-red-500' },
  certificato_medico: { label: 'Certificato Medico', color: 'bg-pink-500' },
  cartella_esattoriale: { label: 'Cartella Esattoriale', color: 'bg-yellow-500' },
  altro: { label: 'Non Classificato', color: 'bg-gray-500' }
};

export default function EmailDownloadManager() {
  const [status, setStatus] = useState(null);
  const [stats, setStats] = useState({});
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [daysBack, setDaysBack] = useState(365);

  // Fetch status
  const fetchStatus = useCallback(async () => {
    try {
      const res = await api.get('/api/email-download/status');
      setStatus(res.data);
    } catch (err) {
      console.error('Errore fetch status:', err);
    }
  }, []);

  // Fetch stats
  const fetchStats = useCallback(async () => {
    try {
      const res = await api.get('/api/email-download/statistiche');
      setStats(res.data);
    } catch (err) {
      console.error('Errore fetch stats:', err);
    }
  }, []);

  // Fetch documents
  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (selectedCategory) params.append('category', selectedCategory);
      params.append('limit', '200');
      
      const res = await api.get(`/api/email-download/documenti-non-associati?${params}`);
      setDocuments(res.data.documenti || []);
    } catch (err) {
      console.error('Errore fetch documenti:', err);
    } finally {
      setLoading(false);
    }
  }, [selectedCategory]);

  useEffect(() => {
    fetchStatus();
    fetchStats();
    fetchDocuments();
    
    // Poll status every 30 seconds if download in progress (ridotto per evitare problemi)
    const interval = setInterval(() => {
      fetchStatus();
    }, 30000);
    
    return () => clearInterval(interval);
  }, [fetchStatus, fetchStats, fetchDocuments]);

  useEffect(() => {
    fetchDocuments();
  }, [selectedCategory, fetchDocuments]);

  // Start full download
  const startDownload = async () => {
    setDownloading(true);
    try {
      await api.post(`/api/email-download/start-full-download?days_back=${daysBack}`);
      fetchStatus();
    } catch (err) {
      console.error('Errore avvio download:', err);
      alert('Errore avvio download: ' + (err.response?.data?.detail || err.message));
    } finally {
      setDownloading(false);
    }
  };

  // Auto associate
  const autoAssociate = async () => {
    setLoading(true);
    try {
      const res = await api.post('/api/email-download/auto-associa');
      alert(`Auto-associazione completata!\n\nAssociati: ${res.data.stats?.associated || 0}\nSaltati: ${res.data.stats?.skipped || 0}\nErrori: ${res.data.stats?.errors || 0}`);
      fetchStats();
      fetchDocuments();
    } catch (err) {
      console.error('Errore auto-associazione:', err);
      alert('Errore auto-associazione');
    } finally {
      setLoading(false);
    }
  };

  // View PDF
  const viewPdf = (doc) => {
    const url = `/api/email-download/pdf/${doc.source_collection}/${doc.id}`;
    window.open(url, '_blank');
  };

  // Filter documents
  const filteredDocs = documents.filter(doc => {
    if (searchTerm) {
      const search = searchTerm.toLowerCase();
      return doc.filename?.toLowerCase().includes(search) ||
             doc.email_subject?.toLowerCase().includes(search) ||
             doc.email_from?.toLowerCase().includes(search);
    }
    return true;
  });

  return (
    <PageLayout title="Gestione Email e Allegati" subtitle="Scarica tutti i PDF dalla posta e associali ai documenti">
    <div className="space-y-6" data-testid="email-download-manager">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold">Gestione Email e Allegati</h1>
          <p className="text-gray-500">Scarica tutti i PDF dalla posta e associali ai documenti</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => { fetchStatus(); fetchStats(); fetchDocuments(); }}>
            <RefreshCw className="w-4 h-4 mr-2" />
            Aggiorna
          </Button>
        </div>
      </div>

      {/* Status Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Download className="w-5 h-5" />
            Download Completo Email
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4 mb-4">
            <div className="flex items-center gap-2">
              <span>Giorni indietro:</span>
              <Input
                type="number"
                value={daysBack}
                onChange={(e) => setDaysBack(parseInt(e.target.value) || 365)}
                className="w-24"
              />
            </div>
            <Button 
              onClick={startDownload} 
              disabled={downloading || status?.in_progress}
              data-testid="start-download-btn"
            >
              {status?.in_progress ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Download in corso...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 mr-2" />
                  Avvia Download Completo
                </>
              )}
            </Button>
            <Button variant="outline" onClick={autoAssociate} disabled={loading}>
              <CheckCircle className="w-4 h-4 mr-2" />
              Auto-Associa PDF
            </Button>
            <Button 
              variant="outline" 
              onClick={async () => {
                setLoading(true);
                try {
                  const res = await api.post('/api/ai-parser/process-email-batch?limit=50');
                  const d = res.data;
                  alert(`Processamento AI completato!\n\nDocumenti processati: ${d.processed || 0}\nFatture create: ${d.fatture_create || 0}\nF24 creati: ${d.f24_creati || 0}\nErrori: ${d.errors?.length || 0}`);
                  fetchStats();
                  fetchDocuments();
                } catch (err) {
                  console.error('Errore processo batch:', err);
                  alert('Errore processamento: ' + (err.response?.data?.detail || err.message));
                } finally {
                  setLoading(false);
                }
              }} 
              disabled={loading}
              data-testid="process-email-batch-btn"
            >
              <Play className="w-4 h-4 mr-2" />
              Processa con AI
            </Button>
          </div>

          {/* Download Progress */}
          {status?.in_progress && (
            <div className="bg-blue-50 p-4 rounded-lg mb-4">
              <div className="flex items-center gap-2 text-blue-700">
                <Loader2 className="w-5 h-5 animate-spin" />
                <span className="font-medium">Download in corso...</span>
              </div>
              {status.stats && (
                <div className="mt-2 text-sm text-blue-600">
                  Email processate: {status.stats.emails_processed} | 
                  PDF scaricati: {status.stats.pdfs_downloaded} |
                  Duplicati saltati: {status.stats.pdfs_duplicates}
                </div>
              )}
            </div>
          )}

          {/* Last Download Stats */}
          {!status?.in_progress && status?.stats && (
            <div className={`p-4 rounded-lg ${status.error ? 'bg-red-50' : 'bg-green-50'}`}>
              {status.error ? (
                <div className="flex items-center gap-2 text-red-700">
                  <XCircle className="w-5 h-5" />
                  <span>Errore: {status.error}</span>
                </div>
              ) : (
                <div className="flex items-center gap-2 text-green-700">
                  <CheckCircle className="w-5 h-5" />
                  <span>Ultimo download completato</span>
                </div>
              )}
              <div className="mt-2 text-sm">
                Email processate: {status.stats.emails_processed} | 
                PDF scaricati: {status.stats.pdfs_downloaded} |
                Duplicati: {status.stats.pdfs_duplicates}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Statistics */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {Object.entries(CATEGORIES).map(([key, { label, color }]) => (
          <Card key={key} className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => setSelectedCategory(key === selectedCategory ? '' : key)}>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{label}</span>
                <Badge className={color}>{stats[key]?.totale || 0}</Badge>
              </div>
              {stats[key] && (
                <div className="mt-2 text-xs text-gray-500">
                  Associati: {stats[key].associati} | Da associare: {stats[key].non_associati}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Documents List */}
      <Card>
        <CardHeader>
          <div className="flex justify-between items-center">
            <CardTitle className="flex items-center gap-2">
              <FileText className="w-5 h-5" />
              Documenti da Associare
              <Badge variant="outline">{filteredDocs.length}</Badge>
            </CardTitle>
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="w-4 h-4 absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
                <Input
                  placeholder="Cerca..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-10 w-64"
                />
              </div>
              <Select value={selectedCategory || "all"} onValueChange={(val) => setSelectedCategory(val === "all" ? "" : val)}>
                <SelectTrigger className="w-48">
                  <SelectValue placeholder="Tutte le categorie" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Tutte le categorie</SelectItem>
                  {Object.entries(CATEGORIES).map(([key, { label }]) => (
                    <SelectItem key={key} value={key}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
            </div>
          ) : filteredDocs.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              Nessun documento da associare trovato
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-2 text-left">File</th>
                    <th className="px-4 py-2 text-left">Categoria</th>
                    <th className="px-4 py-2 text-left">Email</th>
                    <th className="px-4 py-2 text-left">Data</th>
                    <th className="px-4 py-2 text-left">Periodo</th>
                    <th className="px-4 py-2 text-center">Azioni</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {filteredDocs.map((doc) => (
                    <tr key={doc.id} className="hover:bg-gray-50">
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-2">
                          <FileText className="w-4 h-4 text-gray-400" />
                          <span className="font-medium truncate max-w-xs" title={doc.filename}>
                            {doc.filename}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-2">
                        <Badge className={CATEGORIES[doc.category]?.color || 'bg-gray-500'}>
                          {CATEGORIES[doc.category]?.label || doc.category}
                        </Badge>
                      </td>
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-1">
                          <Mail className="w-3 h-3 text-gray-400" />
                          <span className="truncate max-w-xs text-xs" title={doc.email_subject}>
                            {doc.email_subject || '-'}
                          </span>
                        </div>
                        <div className="text-xs text-gray-400">{doc.email_from}</div>
                      </td>
                      <td className="px-4 py-2 text-xs">
                        {doc.email_date ? new Date(doc.email_date).toLocaleDateString('it-IT') : '-'}
                      </td>
                      <td className="px-4 py-2 text-xs">
                        {doc.mese && doc.anno ? `${doc.mese}/${doc.anno}` : '-'}
                      </td>
                      <td className="px-4 py-2 text-center">
                        <Button size="sm" variant="ghost" onClick={() => viewPdf(doc)}>
                          <Eye className="w-4 h-4" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
    </PageLayout>
  );
}
