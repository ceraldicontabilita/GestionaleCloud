import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { toast } from '../hooks/use-toast';
import { QRCodeSVG } from 'qrcode.react';
import { Download, Wifi, Menu as MenuIcon, Eye, Save } from 'lucide-react';
import axios from 'axios';
import AdminPageHeader from '../components/admin/AdminPageHeader';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const AdminQRCodePage = () => {
  const [config, setConfig] = useState(null);
  const [menuUrl, setMenuUrl] = useState('');
  const [wifiSsid, setWifiSsid] = useState('');
  const [wifiPassword, setWifiPassword] = useState('');
  const [wifiSecurity, setWifiSecurity] = useState('WPA');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    checkAuth();
    loadConfig();
  }, []);

  const checkAuth = async () => {
    const token = localStorage.getItem('admin_token');
    if (!token) {
      navigate('/admin/login');
      return;
    }

    try {
      await axios.get(`${BACKEND_URL}/api/qrcode/verify`, {
        headers: { Authorization: `Bearer ${token}` }
      });
    } catch (error) {
      localStorage.removeItem('admin_token');
      navigate('/admin/login');
    }
  };

  const loadConfig = async () => {
    try {
      const response = await axios.get(`${BACKEND_URL}/api/qrcode/config`);
      const data = response.data;
      setConfig(data);
      setMenuUrl(data.menu_url);
      setWifiSsid(data.wifi.ssid);
      setWifiPassword(data.wifi.password);
      setWifiSecurity(data.wifi.security);
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to load configuration',
        variant: 'destructive'
      });
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    const token = localStorage.getItem('admin_token');

    try {
      await axios.put(
        `${BACKEND_URL}/api/qrcode/config`,
        {
          menu_url: menuUrl,
          wifi: {
            ssid: wifiSsid,
            password: wifiPassword,
            security: wifiSecurity,
            hidden: false
          }
        },
        {
          headers: { Authorization: `Bearer ${token}` }
        }
      );

      toast({
        title: 'Success',
        description: 'Configuration updated successfully'
      });

      loadConfig();
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to save configuration',
        variant: 'destructive'
      });
    } finally {
      setSaving(false);
    }
  };

  const downloadQR = (type) => {
    const canvas = document.getElementById(`qr-${type}`);
    if (canvas) {
      const svg = canvas.querySelector('svg');
      const svgData = new XMLSerializer().serializeToString(svg);
      const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
      const svgUrl = URL.createObjectURL(svgBlob);
      const downloadLink = document.createElement('a');
      downloadLink.href = svgUrl;
      downloadLink.download = `ceraldi_${type}_qr.svg`;
      document.body.appendChild(downloadLink);
      downloadLink.click();
      document.body.removeChild(downloadLink);
    }
  };

  const getWiFiString = () => {
    return `WIFI:T:${wifiSecurity};S:${wifiSsid};P:${wifiPassword};H:false;;`;
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#4a5d4a] mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <AdminPageHeader title="QR Code Management" subtitle="Ceraldi Caffè Admin Panel" />

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Configuration Panel */}
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <MenuIcon className="w-5 h-5" />
                  Menu QR Code Settings
                </CardTitle>
                <CardDescription>
                  Configure the URL for your menu QR code
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="menuUrl">Menu URL</Label>
                  <Input
                    id="menuUrl"
                    type="url"
                    value={menuUrl}
                    onChange={(e) => setMenuUrl(e.target.value)}
                    placeholder="https://ceraldicaffe.qromo.it"
                  />
                  <p className="text-xs text-gray-500">
                    This URL will be encoded in the menu QR code
                  </p>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Wifi className="w-5 h-5" />
                  WiFi QR Code Settings
                </CardTitle>
                <CardDescription>
                  Configure WiFi credentials for automatic connection
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="ssid">Network Name (SSID)</Label>
                  <Input
                    id="ssid"
                    value={wifiSsid}
                    onChange={(e) => setWifiSsid(e.target.value)}
                    placeholder="Ceraldi_WiFi"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="password">Password</Label>
                  <Input
                    id="password"
                    type="text"
                    value={wifiPassword}
                    onChange={(e) => setWifiPassword(e.target.value)}
                    placeholder="••••••••"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="security">Security Type</Label>
                  <Select value={wifiSecurity} onValueChange={setWifiSecurity}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="WPA">WPA/WPA2</SelectItem>
                      <SelectItem value="WEP">WEP</SelectItem>
                      <SelectItem value="nopass">No Password</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </CardContent>
            </Card>

            <Button onClick={handleSave} disabled={saving} className="w-full" size="lg">
              <Save className="w-4 h-4 mr-2" />
              {saving ? 'Saving...' : 'Save Configuration'}
            </Button>
          </div>

          {/* QR Code Preview Panel */}
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Menu QR Code</CardTitle>
                <CardDescription>
                  Scan this to view the menu
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div id="qr-menu" className="flex justify-center p-6 bg-white rounded-lg border-2 border-gray-200">
                  <QRCodeSVG value={menuUrl} size={256} level="H" />
                </div>
                <div className="flex gap-2">
                  <Button onClick={() => downloadQR('menu')} variant="outline" className="flex-1">
                    <Download className="w-4 h-4 mr-2" />
                    Download
                  </Button>
                  <Button onClick={() => window.open(menuUrl, '_blank')} variant="outline" className="flex-1">
                    <Eye className="w-4 h-4 mr-2" />
                    Preview
                  </Button>
                </div>
                <div className="text-xs text-gray-500 text-center">
                  <p className="font-mono break-all">{menuUrl}</p>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>WiFi QR Code</CardTitle>
                <CardDescription>
                  Scan this to connect to WiFi automatically
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div id="qr-wifi" className="flex justify-center p-6 bg-white rounded-lg border-2 border-gray-200">
                  <QRCodeSVG value={getWiFiString()} size={256} level="H" />
                </div>
                <Button onClick={() => downloadQR('wifi')} variant="outline" className="w-full">
                  <Download className="w-4 h-4 mr-2" />
                  Download
                </Button>
                <div className="bg-gray-50 p-4 rounded-lg space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Network:</span>
                    <span className="font-semibold">{wifiSsid}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Security:</span>
                    <span className="font-semibold">{wifiSecurity}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Password:</span>
                    <span className="font-mono">{'•'.repeat(wifiPassword.length)}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Instructions */}
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>How to Use</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <h3 className="font-semibold mb-2 flex items-center gap-2">
                  <MenuIcon className="w-4 h-4 text-[#4a5d4a]" />
                  Menu QR Code
                </h3>
                <ol className="list-decimal list-inside space-y-1 text-sm text-gray-600">
                  <li>Download the QR code</li>
                  <li>Print and display it on your tables</li>
                  <li>Customers scan to view the menu</li>
                  <li>Update the URL anytime from this panel</li>
                </ol>
              </div>
              <div>
                <h3 className="font-semibold mb-2 flex items-center gap-2">
                  <Wifi className="w-4 h-4 text-[#4a5d4a]" />
                  WiFi QR Code
                </h3>
                <ol className="list-decimal list-inside space-y-1 text-sm text-gray-600">
                  <li>Download the WiFi QR code</li>
                  <li>Display it in your cafe</li>
                  <li>Customers scan to connect automatically</li>
                  <li>No need to manually enter password</li>
                </ol>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default AdminQRCodePage;