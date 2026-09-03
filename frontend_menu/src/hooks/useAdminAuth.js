import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

/**
 * Verifica il token admin salvato in localStorage e reindirizza al login se assente/scaduto.
 * Restituisce { token, checking, authorized, authHeader }.
 */
export function useAdminAuth() {
  const [checking, setChecking] = useState(true);
  const [authorized, setAuthorized] = useState(false);
  const [token, setToken] = useState(null);
  const navigate = useNavigate();

  const checkAuth = useCallback(async () => {
    const saved = localStorage.getItem('admin_token');
    if (!saved) {
      navigate('/admin/login');
      return;
    }
    try {
      await axios.get(`${BACKEND_URL}/api/qrcode/verify`, {
        headers: { Authorization: `Bearer ${saved}` }
      });
      setToken(saved);
      setAuthorized(true);
    } catch (error) {
      localStorage.removeItem('admin_token');
      navigate('/admin/login');
    } finally {
      setChecking(false);
    }
  }, [navigate]);

  useEffect(() => {
    checkAuth();
  }, []);

  const authHeader = token ? { Authorization: `Bearer ${token}` } : {};

  return { token, checking, authorized, authHeader };
}

export default useAdminAuth;
