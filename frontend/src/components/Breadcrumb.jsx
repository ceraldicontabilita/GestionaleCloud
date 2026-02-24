/**
 * Breadcrumb - Componente per navigazione con URL descrittivi
 */
import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChevronRight, Home } from 'lucide-react';
import { generateBreadcrumb } from '../utils/urlHelpers';

export default function Breadcrumb({ pageTitle = '', customItems = null }) {
  const location = useLocation();
  
  // Usa items custom se forniti, altrimenti genera automaticamente
  const items = customItems || generateBreadcrumb(location.pathname, pageTitle);
  
  if (items.length <= 1) return null;
  
  return (
    <nav 
      aria-label="Breadcrumb" 
      style={{
        padding: '12px 0',
        marginBottom: 16
      }}
    >
      <ol style={{
        display: 'flex',
        alignItems: 'center',
        listStyle: 'none',
        margin: 0,
        padding: 0,
        flexWrap: 'wrap',
        gap: 4
      }}>
        {items.map((item, index) => (
          <li 
            key={item.path}
            style={{
              display: 'flex',
              alignItems: 'center'
            }}
          >
            {index > 0 && (
              <ChevronRight 
                style={{ 
                  width: 14, 
                  height: 14, 
                  color: '#9ca3af',
                  marginRight: 4
                }} 
              />
            )}
            
            {item.isLast ? (
              <span 
                style={{
                  color: '#1f2937',
                  fontWeight: 600,
                  fontSize: 14
                }}
              >
                {index === 0 ? <Home style={{ width: 14, height: 14 }} /> : item.label}
              </span>
            ) : (
              <Link
                to={item.path}
                style={{
                  color: '#6080a0',
                  textDecoration: 'none',
                  fontSize: 14,
                  display: 'flex',
                  alignItems: 'center',
                  transition: 'color 0.2s'
                }}
                onMouseEnter={(e) => e.target.style.color = '#1535a8'}
                onMouseLeave={(e) => e.target.style.color = '#6080a0'}
              >
                {index === 0 ? <Home style={{ width: 14, height: 14 }} /> : item.label}
              </Link>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

// Versione compatta per header di pagina
export function BreadcrumbCompact({ items }) {
  if (!items || items.length <= 1) return null;
  
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      fontSize: 12,
      color: 'rgba(255,255,255,0.8)',
      marginTop: 4
    }}>
      {items.slice(1).map((item, index) => (
        <span key={item.path}>
          {index > 0 && <span style={{ margin: '0 6px' }}>/</span>}
          {item.label}
        </span>
      ))}
    </div>
  );
}
