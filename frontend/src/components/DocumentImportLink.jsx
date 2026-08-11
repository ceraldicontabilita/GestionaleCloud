import React from 'react';
import { Link, useInRouterContext } from 'react-router-dom';

/**
 * Punto unico di acquisizione: le pagine specialistiche mostrano il contesto,
 * ma il file viene sempre scelto e classificato da Documenti.
 */
export default function DocumentImportLink({ children, workflow, style, ...props }) {
  const query = workflow ? `?workflow=${encodeURIComponent(workflow)}` : '';
  const to = `/documenti/import${query}`;
  const inRouter = useInRouterContext();
  if (!inRouter) {
    return (
      <a href={to} style={{ textDecoration: 'none', ...style }} {...props}>
        {children}
      </a>
    );
  }
  return (
    <Link to={to} style={{ textDecoration: 'none', ...style }} {...props}>
      {children}
    </Link>
  );
}
