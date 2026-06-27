import { ReactNode, CSSProperties, HTMLAttributes } from 'react';

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  /** Colore semantico. Default 'neutral'. */
  variant?: 'success' | 'warning' | 'danger' | 'info' | 'primary' | 'accent' | 'neutral';
  children?: ReactNode;
  style?: CSSProperties;
}

/** Pill di stato uppercase per tabelle e schede. */
export function Badge(props: BadgeProps): JSX.Element;
export default Badge;
