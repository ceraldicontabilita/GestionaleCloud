import React from 'react';
import { STYLES_NEW, COLORS_NEW } from '../lib/designSystem';

export const PageHeaderNew = ({ title, subtitle, actions, icon: Icon }) => {
  return (
    <div style={STYLES_NEW.pageHeader}>
      <div style={STYLES_NEW.contentContainer}>
        <h1 style={STYLES_NEW.pageHeaderTitle}>
          {Icon && <Icon size={36} />}
          {title}
        </h1>
        {subtitle && (
          <p style={STYLES_NEW.pageHeaderSubtitle}>{subtitle}</p>
        )}
        {actions && actions.length > 0 && (
          <div style={STYLES_NEW.pageHeaderActions}>
            {actions.map((action, idx) => (
              <button
                key={idx}
                onClick={action.onClick}
                disabled={action.disabled}
                style={{
                  ...STYLES_NEW.btnLarge,
                  ...(action.variant === 'white' ? STYLES_NEW.btnWhite : 
                     action.variant === 'success' ? STYLES_NEW.btnSuccess : 
                     STYLES_NEW.btnPrimary),
                  opacity: action.disabled ? 0.5 : 1,
                  cursor: action.disabled ? 'not-allowed' : 'pointer'
                }}
                onMouseEnter={(e) => {
                  if (!action.disabled) {
                    e.target.style.transform = 'translateY(-2px)';
                    e.target.style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)';
                  }
                }}
                onMouseLeave={(e) => {
                  e.target.style.transform = 'translateY(0)';
                  e.target.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)';
                }}
              >
                {action.icon && <action.icon size={20} />}
                {action.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default PageHeaderNew;
