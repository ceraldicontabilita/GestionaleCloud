import React, { useState, useEffect, useCallback } from 'react';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Input } from '../ui/input';
import { toast } from '../../hooks/use-toast';
import { Upload, Trash2, Image as ImageIcon, Check } from 'lucide-react';
import axios from 'axios';
import { menuCategories } from '../../mockData';

const BACKEND_URL = process.env.REACT_APP_MENU_BACKEND_URL;

const ImageUploadManager = () => {
  const [images, setImages] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selectedFile, setSelectedFile] = useState(null);

  useEffect(() => {
    loadImages();
  }, []);

  const loadImages = async () => {
    try {
      const token = localStorage.getItem('admin_token');
      const response = await axios.get(`${BACKEND_URL}/api/admin/images`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setImages(response.data.images);
    } catch (error) {
      toast({
        title: 'Errore',
        description: 'Impossibile caricare le immagini',
        variant: 'destructive'
      });
    } finally {
      setLoading(false);
    }
  };

  const handleFileSelect = (event) => {
    const file = event.target.files[0];
    if (file) {
      if (!file.type.startsWith('image/')) {
        toast({
          title: 'Errore',
          description: 'Per favore seleziona un file immagine',
          variant: 'destructive'
        });
        return;
      }
      setSelectedFile(file);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) return;

    setUploading(true);
    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const token = localStorage.getItem('admin_token');
      const response = await axios.post(
        `${BACKEND_URL}/api/admin/upload-image`,
        formData,
        {
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'multipart/form-data'
          }
        }
      );

      toast({
        title: 'Successo!',
        description: `Immagine "${response.data.filename}" caricata con successo`
      });

      setSelectedFile(null);
      document.getElementById('file-input').value = '';
      loadImages();
      
      // Try to auto-associate with products
      autoAssociateImage(response.data.filename);
      
    } catch (error) {
      toast({
        title: 'Errore',
        description: 'Impossibile caricare l\'immagine',
        variant: 'destructive'
      });
    } finally {
      setUploading(false);
    }
  };

  const autoAssociateImage = (filename) => {
    // Try to match filename with product names
    const lowerFilename = filename.toLowerCase().replace(/[_-]/g, ' ');
    
    let matched = false;
    menuCategories.forEach(category => {
      category.subcategories?.forEach(subcategory => {
        subcategory.items?.forEach(item => {
          const itemName = item.nameIT.toLowerCase();
          if (lowerFilename.includes(itemName) || itemName.includes(lowerFilename.split('.')[0])) {
            toast({
              title: 'Associazione automatica',
              description: `Immagine associabile a: ${item.nameIT}`,
              duration: 5000
            });
            matched = true;
          }
        });
      });
    });

    if (!matched) {
      toast({
        title: 'Info',
        description: 'Nessuna corrispondenza automatica trovata. Associa manualmente.',
        duration: 3000
      });
    }
  };

  const handleDelete = async (filename) => {
    if (!window.confirm(`Eliminare l'immagine "${filename}"?`)) return;

    try {
      const token = localStorage.getItem('admin_token');
      await axios.delete(`${BACKEND_URL}/api/admin/images/${filename}`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      toast({
        title: 'Eliminata',
        description: `Immagine "${filename}" eliminata`
      });
      
      loadImages();
    } catch (error) {
      toast({
        title: 'Errore',
        description: 'Impossibile eliminare l\'immagine',
        variant: 'destructive'
      });
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  return (
    <div className="space-y-6">
      {/* Upload Section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Upload className="w-5 h-5" />
            Carica Nuova Immagine
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
              <ImageIcon className="w-12 h-12 mx-auto text-gray-400 mb-4" />
              <input
                id="file-input"
                type="file"
                accept="image/*"
                onChange={handleFileSelect}
                className="hidden"
              />
              <label
                htmlFor="file-input"
                className="cursor-pointer text-blue-600 hover:text-blue-800 font-medium"
              >
                Seleziona un'immagine
              </label>
              <p className="text-sm text-gray-500 mt-2">
                PNG, JPG, JPEG fino a 10MB
              </p>
              {selectedFile && (
                <div className="mt-4 p-3 bg-gray-50 rounded-lg">
                  <p className="font-medium text-gray-900">{selectedFile.name}</p>
                  <p className="text-sm text-gray-500">
                    {formatFileSize(selectedFile.size)}
                  </p>
                </div>
              )}
            </div>

            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
              <h4 className="font-semibold text-blue-900 mb-2">💡 Convenzioni di Nomenclatura</h4>
              <ul className="text-sm text-blue-800 space-y-1">
                <li>• Usa il nome del prodotto in italiano: <code className="bg-blue-100 px-1 rounded">sfogliatella-riccia.jpg</code></li>
                <li>• Per caffè speciali: <code className="bg-blue-100 px-1 rounded">caffe-ceraldi.jpg</code></li>
                <li>• Separa le parole con trattini o underscore</li>
                <li>• Il sistema proverà ad associare automaticamente l'immagine</li>
              </ul>
            </div>

            <Button 
              onClick={handleUpload} 
              disabled={!selectedFile || uploading}
              className="w-full"
              size="lg"
            >
              {uploading ? 'Caricamento...' : 'Carica Immagine'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Images Gallery */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Immagini Caricate ({images.length})</span>
            <Button variant="outline" size="sm" onClick={loadImages}>
              Aggiorna
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="text-center py-8 text-gray-500">Caricamento...</div>
          ) : images.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <ImageIcon className="w-12 h-12 mx-auto mb-2 text-gray-300" />
              <p>Nessuna immagine caricata</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              {images.map((image) => (
                <div key={image.filename} className="border rounded-lg overflow-hidden group relative">
                  <div className="aspect-square bg-gray-100 flex items-center justify-center">
                    <img
                      src={image.url}
                      alt={image.filename}
                      className="w-full h-full object-cover"
                    />
                  </div>
                  <div className="p-2 bg-white">
                    <p className="text-xs font-medium truncate" title={image.filename}>
                      {image.filename}
                    </p>
                    <p className="text-xs text-gray-500">{formatFileSize(image.size)}</p>
                  </div>
                  <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => handleDelete(image.filename)}
                      className="h-8 w-8 p-0"
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
    </div>
  );
};

export default ImageUploadManager;