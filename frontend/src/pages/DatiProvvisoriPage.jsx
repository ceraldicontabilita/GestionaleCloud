import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export default function DatiProvvisoriPage() {
  const navigate = useNavigate();

  useEffect(() => {
    navigate('/prima-nota#sezione=provvisori', { replace: true });
  }, [navigate]);

  return <div />;
}
