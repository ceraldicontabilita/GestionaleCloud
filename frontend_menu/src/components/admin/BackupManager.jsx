import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { toast } from '../../hooks/use-toast';
import { Database, Download, Trash2, RefreshCw, Clock, HardDrive, Shield } from 'lucide-react';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_MENU_BACKEND_URL;

const BackupManager = () => {
  const [backups, setBackups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [restoring, setRestoring] = useState(null);

  useEffect(() => {
    loadBackups();
  }, []);

  const loadBackups = async () => {
    try {
      const token = localStorage.getItem('admin_token');
      const response = await axios.get(`${BACKEND_URL}/api/backup/list`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setBackups(response.data.backups || []);
    } catch (error) {
      toast({
        title: 'Errore',
        description: 'Impossibile caricare la lista dei backup',
        variant: 'destructive'
      });
    } finally {
      setLoading(false);
    }
  };

  const createBackup = async () => {
    setCreating(true);
    try {
      const token = localStorage.getItem('admin_token');
      const response = await axios.post(`${BACKEND_URL}/api/backup/create`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });

      toast({
        title: 'Backup Creato!',
        description: `File: ${response.data.backup.filename}`,
      });

      loadBackups();
    } catch (error) {
      toast({
        title: 'Errore',
        description: error.response?.data?.detail || 'Impossibile creare il backup',
        variant: 'destructive'
      });
    } finally {
      setCreating(false);
    }
  };

  const downloadBackup = async (filename) => {
    try {
      const token = localStorage.getItem('admin_token');
      const response = await axios.get(`${BACKEND_URL}/api/backup/download/${filename}`, {
        headers: { Authorization: `Bearer ${token}` },
        responseType: 'blob'
      });

      // Create download link
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);

      toast({
        title: 'Download Avviato',
        description: `Scaricamento di ${filename}`,
      });
    } catch (error) {
      toast({
        title: 'Errore',
        description: 'Impossibile scaricare il backup',
        variant: 'destructive'
      });
    }
  };

  const deleteBackup = async (filename) => {
    if (!window.confirm(`Eliminare il backup "${filename}"? Questa azione è irreversibile.`)) {
      return;
    }

    try {
      const token = localStorage.getItem('admin_token');
      await axios.delete(`${BACKEND_URL}/api/backup/delete/${filename}`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      toast({
        title: 'Backup Eliminato',
        description: `${filename} eliminato con successo`,
      });

      loadBackups();
    } catch (error) {
      toast({
        title: 'Errore',
        description: 'Impossibile eliminare il backup',
        variant: 'destructive'
      });
    }
  };

  const restoreBackup = async (filename) => {
    if (!window.confirm(`ATTENZIONE: Ripristinare il database dal backup "${filename}"?\n\nQuesta operazione sovrascriverà TUTTI i dati attuali!`)) {
      return;
    }

    setRestoring(filename);
    try {
      const token = localStorage.getItem('admin_token');
      await axios.post(`${BACKEND_URL}/api/backup/restore/${filename}`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });

      toast({
        title: 'Database Ripristinato',
        description: `Ripristinato con successo da ${filename}`,
      });
    } catch (error) {
      toast({
        title: 'Errore',
        description: error.response?.data?.detail || 'Impossibile ripristinare il backup',
        variant: 'destructive'
      });
    } finally {
      setRestoring(null);
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  };

  const formatDate = (isoString) => {
    if (!isoString) return 'N/A';
    return new Date(isoString).toLocaleString('it-IT', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  return (
    <div className="space-y-6">
      {/* Create Backup Section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Database className="w-5 h-5" />
            Crea Nuovo Backup
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
            <h4 className="font-semibold text-blue-900 mb-2 flex items-center gap-2">
              <Shield className="w-4 h-4" />
              Informazioni sul Backup
            </h4>
            <ul className="text-sm text-blue-800 space-y-1">
              <li>Il backup includerà tutti i dati del database MongoDB</li>
              <li>I file vengono compressi in formato .tar.gz</li>
              <li>Conserva i backup in un luogo sicuro</li>
            </ul>
          </div>

          <Button 
            onClick={createBackup} 
            disabled={creating}
            className="w-full"
            size="lg"
          >
            {creating ? (
              <>
                <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                Creazione in corso...
              </>
            ) : (
              <>
                <Database className="w-4 h-4 mr-2" />
                Crea Backup Database
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      {/* Backups List */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span className="flex items-center gap-2">
              <HardDrive className="w-5 h-5" />
              Backup Disponibili ({backups.length})
            </span>
            <Button variant="outline" size="sm" onClick={loadBackups}>
              <RefreshCw className="w-4 h-4 mr-2" />
              Aggiorna
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="text-center py-8 text-gray-500">
              <RefreshCw className="w-8 h-8 mx-auto animate-spin mb-2" />
              Caricamento...
            </div>
          ) : backups.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <Database className="w-12 h-12 mx-auto mb-2 text-gray-300" />
              <p>Nessun backup disponibile</p>
              <p className="text-sm mt-1">Crea il primo backup del tuo database</p>
            </div>
          ) : (
            <div className="space-y-3">
              {backups.map((backup) => (
                <div
                  key={backup.filename}
                  className="flex items-center justify-between p-4 border rounded-lg hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
                      <Database className="w-5 h-5 text-green-600" />
                    </div>
                    <div>
                      <p className="font-medium text-gray-900">{backup.filename}</p>
                      <div className="flex items-center gap-4 text-sm text-gray-500">
                        <span className="flex items-center gap-1">
                          <HardDrive className="w-3 h-3" />
                          {formatFileSize(backup.size)}
                        </span>
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {formatDate(backup.created_at)}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => downloadBackup(backup.filename)}
                      title="Scarica backup"
                    >
                      <Download className="w-4 h-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => restoreBackup(backup.filename)}
                      disabled={restoring === backup.filename}
                      title="Ripristina database"
                      className="text-orange-600 hover:text-orange-700 hover:bg-orange-50"
                    >
                      {restoring === backup.filename ? (
                        <RefreshCw className="w-4 h-4 animate-spin" />
                      ) : (
                        <RefreshCw className="w-4 h-4" />
                      )}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => deleteBackup(backup.filename)}
                      title="Elimina backup"
                      className="text-red-600 hover:text-red-700 hover:bg-red-50"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Warning Notice */}
      <Card className="border-orange-200 bg-orange-50">
        <CardContent className="pt-6">
          <div className="flex items-start gap-3">
            <Shield className="w-5 h-5 text-orange-600 mt-0.5" />
            <div>
              <h4 className="font-semibold text-orange-900">Nota sulla Sicurezza</h4>
              <p className="text-sm text-orange-800 mt-1">
                I backup contengono dati sensibili. Scarica e conserva i file in un luogo sicuro.
                Il ripristino sovrascriverà tutti i dati esistenti nel database.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default BackupManager;
