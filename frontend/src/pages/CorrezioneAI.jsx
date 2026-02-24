import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { 
  FileText, AlertCircle, CheckCircle, Edit, Save, X, 
  RefreshCw, Search
} from 'lucide-react';
import api from '../api';
import { STYLES, COLORS, button, badge, formatEuro, formatDateIT } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';

export default function CorrezioneAI() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({});
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [editMode, setEditMode] = useState(false);
  const [editedData, setEditedData] = useState({});
  const [filter, setFilter] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filter !== 'all') params.append('tipo', filter);
      params.append('limit', '100');
      
      const response = await api.get(`/api/ai-parser/da-rivedere?${params}`);
      setDocuments(response.data.documents || []);
    } catch (error) {
      console.error('Errore caricamento documenti:', error);
    }
    setLoading(false);
  }, [filter]);

  const loadStats = useCallback(async () => {
    try {
      const response = await api.get('/api/ai-parser/statistiche');
      setStats(response.data);
    } catch (error) {
      console.error('Errore caricamento statistiche:', error);
    }
  }, []);

  useEffect(() => {
    loadDocuments();
    loadStats();
  }, [loadDocuments, loadStats]);

  const handleSelectDocument = (doc) => {
    setSelectedDoc(doc);
    setEditedData(doc.ai_parsed_data || {});
    setEditMode(false);
  };

  const handleSaveCorrection = async () => {
    if (!selectedDoc) return;
    
    try {
      await api.put(`/api/ai-parser/da-rivedere/${selectedDoc.id}/classifica`, null, {
        params: {
          centro_costo_id: editedData.centro_costo_id || 'CDC_ALTRO',
          centro_costo_nome: editedData.centro_costo_nome || 'Altri Costi',
          notes: 'Corretto manualmente'
        }
      });
      
      alert('Documento aggiornato con successo!');
      loadDocuments();
      setSelectedDoc(null);
      setEditMode(false);
    } catch (error) {
      console.error('Errore salvataggio:', error);
      alert('Errore durante il salvataggio');
    }
  };

  const filteredDocs = documents.filter(doc => {
    if (!searchTerm) return true;
    const search = searchTerm.toLowerCase();
    return (
      (doc.filename || '').toLowerCase().includes(search) ||
      (doc.fornitore_nome || '').toLowerCase().includes(search) ||
      (doc.dipendente_nome || '').toLowerCase().includes(search)
    );
  });

  const getStatusBadge = (doc) => {
    if (doc.ai_parsing_error) {
      return <Badge variant="destructive">Errore Parsing</Badge>;
    }
    if (doc.needs_review) {
      return <Badge variant="warning" className="bg-orange-100 text-orange-800">Da Rivedere</Badge>;
    }
    if (!doc.classificazione_automatica) {
      return <Badge variant="secondary">Non Classificato</Badge>;
    }
    return <Badge variant="success" className="bg-green-100 text-green-800">OK</Badge>;
  };

  const getDocTypeIcon = (tipo) => {
    switch (tipo) {
      case 'fattura': return '📄';
      case 'f24': return '📋';
      case 'busta_paga': return '📄';
      default: return '📁';
    }
  };

  return (
    <PageLayout title="Correzione Dati AI" subtitle="Revisione e correzione documenti processati dalla AI">
    <div className="bg-gray-50 min-h-screen">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-800">Correzione Dati AI</h1>
        <p className="text-gray-600">Revisione e correzione documenti processati dalla AI</p>
      </div>

      {/* Statistiche */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <Card>
          <CardContent className="p-4">
            <div className="text-2xl font-bold text-blue-600">{stats.total_parsed || 0}</div>
            <div className="text-sm text-gray-600">Totale Parsati</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-2xl font-bold text-orange-600">{stats.needs_review || 0}</div>
            <div className="text-sm text-gray-600">Da Rivedere</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-2xl font-bold text-green-600">{stats.auto_classified || 0}</div>
            <div className="text-sm text-gray-600">Auto-Classificati</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-2xl font-bold text-red-600">{stats.parsing_errors || 0}</div>
            <div className="text-sm text-gray-600">Errori Parsing</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-2xl font-bold text-purple-600">{stats.classification_rate || 0}%</div>
            <div className="text-sm text-gray-600">Tasso Successo</div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Lista Documenti */}
        <Card>
          <CardHeader className="pb-2">
            <div className="flex justify-between items-center">
              <CardTitle className="text-lg">Documenti da Rivedere</CardTitle>
              <Button variant="outline" size="sm" onClick={loadDocuments}>
                <RefreshCw className="w-4 h-4 mr-1" />
                Aggiorna
              </Button>
            </div>
            
            {/* Filtri */}
            <div className="flex gap-2 mt-3">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
                <Input
                  placeholder="Cerca..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-9"
                />
              </div>
              <select
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="px-3 py-2 border rounded-md text-sm"
              >
                <option value="all">Tutti</option>
                <option value="fattura">Fatture</option>
                <option value="f24">F24</option>
                <option value="busta_paga">Cedolini</option>
              </select>
            </div>
          </CardHeader>
          
          <CardContent className="max-h-[600px] overflow-y-auto">
            {loading ? (
              <div className="text-center py-8 text-gray-500">Caricamento...</div>
            ) : filteredDocs.length === 0 ? (
              <div className="text-center py-8">
                <CheckCircle className="w-12 h-12 text-green-500 mx-auto mb-2" />
                <p className="text-gray-600">Nessun documento da rivedere!</p>
              </div>
            ) : (
              <div className="space-y-2">
                {filteredDocs.map((doc) => (
                  <div
                    key={doc.id}
                    onClick={() => handleSelectDocument(doc)}
                    className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                      selectedDoc?.id === doc.id 
                        ? 'border-blue-500 bg-blue-50' 
                        : 'border-gray-200 hover:bg-gray-50'
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-xl">{getDocTypeIcon(doc.ai_parsed_type)}</span>
                        <div>
                          <div className="font-medium text-sm truncate max-w-[200px]">
                            {doc.filename || 'Senza nome'}
                          </div>
                          <div className="text-xs text-gray-500">
                            {doc.fornitore_nome || doc.dipendente_nome || doc.ai_parsed_type || 'N/D'}
                          </div>
                        </div>
                      </div>
                      {getStatusBadge(doc)}
                    </div>
                    {doc.ai_parsing_error && (
                      <div className="mt-2 text-xs text-red-600 flex items-center gap-1">
                        <AlertCircle className="w-3 h-3" />
                        {doc.ai_parsing_error.substring(0, 50)}...
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Dettaglio Documento */}
        <Card>
          <CardHeader className="pb-2">
            <div className="flex justify-between items-center">
              <CardTitle className="text-lg">
                {selectedDoc ? 'Dettaglio Documento' : 'Seleziona un documento'}
              </CardTitle>
              {selectedDoc && (
                <div className="flex gap-2">
                  {editMode ? (
                    <>
                      <Button size="sm" onClick={handleSaveCorrection}>
                        <Save className="w-4 h-4 mr-1" />
                        Salva
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => setEditMode(false)}>
                        <X className="w-4 h-4 mr-1" />
                        Annulla
                      </Button>
                    </>
                  ) : (
                    <Button variant="outline" size="sm" onClick={() => setEditMode(true)}>
                      <Edit className="w-4 h-4 mr-1" />
                      Modifica
                    </Button>
                  )}
                </div>
              )}
            </div>
          </CardHeader>
          
          <CardContent>
            {!selectedDoc ? (
              <div className="text-center py-12 text-gray-500">
                <FileText className="w-16 h-16 mx-auto mb-4 opacity-30" />
                <p>Seleziona un documento dalla lista per visualizzare i dettagli</p>
              </div>
            ) : (
              <Tabs defaultValue="dati">
                <TabsList className="mb-4">
                  <TabsTrigger value="dati">Dati Estratti</TabsTrigger>
                  <TabsTrigger value="raw">JSON Raw</TabsTrigger>
                </TabsList>
                
                <TabsContent value="dati">
                  <div className="space-y-4">
                    {/* Info Base */}
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="text-xs text-gray-500">Tipo Documento</label>
                        <div className="font-medium">{selectedDoc.ai_parsed_type || 'N/D'}</div>
                      </div>
                      <div>
                        <label className="text-xs text-gray-500">File</label>
                        <div className="font-medium truncate">{selectedDoc.filename || 'N/D'}</div>
                      </div>
                    </div>

                    {/* Dati Specifici per Tipo */}
                    {selectedDoc.ai_parsed_type === 'fattura' && (
                      <>
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="text-xs text-gray-500">Fornitore</label>
                            {editMode ? (
                              <Input
                                value={editedData.fornitore?.denominazione || ''}
                                onChange={(e) => setEditedData({
                                  ...editedData,
                                  fornitore: { ...editedData.fornitore, denominazione: e.target.value }
                                })}
                              />
                            ) : (
                              <div className="font-medium">{selectedDoc.fornitore_nome || 'N/D'}</div>
                            )}
                          </div>
                          <div>
                            <label className="text-xs text-gray-500">P.IVA</label>
                            <div className="font-medium">{selectedDoc.fornitore_piva || 'N/D'}</div>
                          </div>
                        </div>
                        <div className="grid grid-cols-3 gap-4">
                          <div>
                            <label className="text-xs text-gray-500">Numero</label>
                            <div className="font-medium">{selectedDoc.numero_documento || 'N/D'}</div>
                          </div>
                          <div>
                            <label className="text-xs text-gray-500">Data</label>
                            <div className="font-medium">{selectedDoc.data_documento || 'N/D'}</div>
                          </div>
                          <div>
                            <label className="text-xs text-gray-500">Importo</label>
                            <div className="font-medium text-green-600">
                              € {(selectedDoc.importo_totale || 0).toLocaleString('it-IT', { minimumFractionDigits: 2 })}
                            </div>
                          </div>
                        </div>
                      </>
                    )}

                    {selectedDoc.ai_parsed_type === 'f24' && (
                      <>
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="text-xs text-gray-500">Codice Fiscale</label>
                            <div className="font-medium">{selectedDoc.codice_fiscale || 'N/D'}</div>
                          </div>
                          <div>
                            <label className="text-xs text-gray-500">Data Pagamento</label>
                            <div className="font-medium">{selectedDoc.data_pagamento || 'N/D'}</div>
                          </div>
                        </div>
                        <div>
                          <label className="text-xs text-gray-500">Totale Versato</label>
                          <div className="font-medium text-blue-600">
                            € {(selectedDoc.totale_versato || 0).toLocaleString('it-IT', { minimumFractionDigits: 2 })}
                          </div>
                        </div>
                      </>
                    )}

                    {selectedDoc.ai_parsed_type === 'busta_paga' && (
                      <>
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="text-xs text-gray-500">Dipendente</label>
                            <div className="font-medium">{selectedDoc.dipendente_nome || 'N/D'}</div>
                          </div>
                          <div>
                            <label className="text-xs text-gray-500">Periodo</label>
                            <div className="font-medium">
                              {selectedDoc.periodo_mese || 'N/D'}/{selectedDoc.periodo_anno || 'N/D'}
                            </div>
                          </div>
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="text-xs text-gray-500">Netto Pagato</label>
                            <div className="font-medium text-green-600">
                              € {(selectedDoc.netto_pagato || 0).toLocaleString('it-IT', { minimumFractionDigits: 2 })}
                            </div>
                          </div>
                          <div>
                            <label className="text-xs text-gray-500">Lordo Totale</label>
                            <div className="font-medium">
                              € {(selectedDoc.lordo_totale || 0).toLocaleString('it-IT', { minimumFractionDigits: 2 })}
                            </div>
                          </div>
                        </div>
                      </>
                    )}

                    {/* Centro di Costo */}
                    <div className="pt-4 border-t">
                      <label className="text-xs text-gray-500">Centro di Costo</label>
                      {editMode ? (
                        <select
                          value={editedData.centro_costo_id || ''}
                          onChange={(e) => {
                            const options = {
                              'CDC_MATERIE_PRIME': 'Materie Prime',
                              'CDC_BEVANDE': 'Bevande',
                              'CDC_PERSONALE': 'Costo del Personale',
                              'CDC_AFFITTO': 'Affitto e Locazioni',
                              'CDC_UTENZE': 'Utenze',
                              'CDC_MANUTENZIONE': 'Manutenzione',
                              'CDC_CONSULENZE': 'Consulenze',
                              'CDC_TASSE': 'Imposte e Tasse',
                              'CDC_ALTRO': 'Altri Costi'
                            };
                            setEditedData({
                              ...editedData,
                              centro_costo_id: e.target.value,
                              centro_costo_nome: options[e.target.value] || e.target.value
                            });
                          }}
                          className="w-full px-3 py-2 border rounded-md"
                        >
                          <option value="">Seleziona...</option>
                          <option value="CDC_MATERIE_PRIME">Materie Prime</option>
                          <option value="CDC_BEVANDE">Bevande</option>
                          <option value="CDC_PERSONALE">Costo del Personale</option>
                          <option value="CDC_AFFITTO">Affitto e Locazioni</option>
                          <option value="CDC_UTENZE">Utenze</option>
                          <option value="CDC_MANUTENZIONE">Manutenzione</option>
                          <option value="CDC_CONSULENZE">Consulenze</option>
                          <option value="CDC_TASSE">Imposte e Tasse</option>
                          <option value="CDC_ALTRO">Altri Costi</option>
                        </select>
                      ) : (
                        <div className="font-medium">
                          {selectedDoc.centro_costo_nome || 
                           <span className="text-orange-600">Non assegnato</span>}
                        </div>
                      )}
                    </div>

                    {/* Errore Parsing */}
                    {selectedDoc.ai_parsing_error && (
                      <div className="p-3 bg-red-50 rounded-lg border border-red-200">
                        <div className="flex items-center gap-2 text-red-700 font-medium mb-1">
                          <AlertCircle className="w-4 h-4" />
                          Errore Parsing
                        </div>
                        <div className="text-sm text-red-600">{selectedDoc.ai_parsing_error}</div>
                      </div>
                    )}
                  </div>
                </TabsContent>
                
                <TabsContent value="raw">
                  <pre className="bg-gray-100 p-4 rounded-lg text-xs overflow-auto max-h-[400px]">
                    {JSON.stringify(selectedDoc.ai_parsed_data || selectedDoc, null, 2)}
                  </pre>
                </TabsContent>
              </Tabs>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
    </PageLayout>
  );
}
