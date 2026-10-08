/**
 * Context per gestire upload in background.
 * Mantiene lo stato degli upload anche quando si cambia pagina.
 */
import React, { createContext, useContext, useState, useCallback } from 'react';
import api from '../api';

const UploadContext = createContext();

export function UploadProvider({ children }) {
  const [uploads, setUploads] = useState([]);
  const [notifications, setNotifications] = useState([]);

  // Aggiunge un nuovo upload alla coda
  const addUpload = useCallback((uploadConfig) => {
    const uploadId = `upload_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const newUpload = {
      id: uploadId,
      fileName: uploadConfig.fileName,
      fileType: uploadConfig.fileType,
      status: 'pending', // pending, uploading, processing, completed, error
      progress: 0,
      startTime: new Date(),
      endpoint: uploadConfig.endpoint,
      formData: uploadConfig.formData,
      onSuccess: uploadConfig.onSuccess,
      onError: uploadConfig.onError,
      result: null,
      error: null
    };

    setUploads(prev => [...prev, newUpload]);
    
    // Avvia l'upload
    processUpload(newUpload);
    
    return uploadId;
  }, []);

  // Processa un singolo upload
  const processUpload = async (upload) => {
    updateUpload(upload.id, { status: 'uploading', progress: 10 });

    try {
      const response = await api.post(upload.endpoint, upload.formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 300000, // 5 minuti per file grandi
        onUploadProgress: (progressEvent) => {
          const progress = Math.round((progressEvent.loaded * 80) / progressEvent.total) + 10;
          updateUpload(upload.id, { progress: Math.min(progress, 90) });
        }
      });

      updateUpload(upload.id, { 
        status: 'completed', 
        progress: 100, 
        result: response.data,
        endTime: new Date()
      });

      // Notifica completamento
      addNotification({
        type: 'success',
        title: 'Upload Completato',
        message: `${upload.fileName} caricato con successo`,
        uploadId: upload.id
      });

      // Callback success
      if (upload.onSuccess) {
        upload.onSuccess(response.data);
      }

    } catch (error) {
      const errorMessage = error.response?.data?.detail || error.message || 'Errore sconosciuto';
      
      // Log dettagliato per debug
      console.error('[Upload Error]', upload.fileName, error);
      
      updateUpload(upload.id, { 
        status: 'error', 
        error: errorMessage,
        endTime: new Date()
      });

      // Notifica errore
      addNotification({
        type: 'error',
        title: 'Errore Upload',
        message: `${upload.fileName}: ${errorMessage}`,
        uploadId: upload.id
      });

      // Callback error
      if (upload.onError) {
        upload.onError(error);
      }
    }
  };

  // Aggiorna un upload esistente
  const updateUpload = useCallback((uploadId, updates) => {
    setUploads(prev => prev.map(u => 
      u.id === uploadId ? { ...u, ...updates } : u
    ));
  }, []);

  // Rimuove un upload dalla lista
  const removeUpload = useCallback((uploadId) => {
    setUploads(prev => prev.filter(u => u.id !== uploadId));
  }, []);

  // Rimuove tutti gli upload completati
  const clearCompleted = useCallback(() => {
    setUploads(prev => prev.filter(u => u.status === 'uploading' || u.status === 'pending'));
  }, []);

  // Aggiunge una notifica
  const addNotification = useCallback((notification) => {
    const notifId = `notif_${Date.now()}`;
    setNotifications(prev => [...prev, { ...notification, id: notifId, timestamp: new Date() }]);
    
    // Auto-rimuovi dopo 5 secondi
    setTimeout(() => {
      setNotifications(prev => prev.filter(n => n.id !== notifId));
    }, 5000);
  }, []);

  // Rimuove una notifica
  const removeNotification = useCallback((notifId) => {
    setNotifications(prev => prev.filter(n => n.id !== notifId));
  }, []);

  // Conteggi
  const activeUploads = uploads.filter(u => u.status === 'uploading' || u.status === 'pending');
  const completedUploads = uploads.filter(u => u.status === 'completed');
  const errorUploads = uploads.filter(u => u.status === 'error');

  const value = {
    uploads,
    notifications,
    addUpload,
    updateUpload,
    removeUpload,
    clearCompleted,
    addNotification,
    removeNotification,
    activeUploads,
    completedUploads,
    errorUploads,
    hasActiveUploads: activeUploads.length > 0
  };

  return (
    <UploadContext.Provider value={value}>
      {children}
    </UploadContext.Provider>
  );
}

export function useUpload() {
  const context = useContext(UploadContext);
  if (!context) {
    throw new Error('useUpload must be used within an UploadProvider');
  }
  return context;
}

export default UploadContext;
