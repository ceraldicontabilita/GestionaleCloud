import { ReactNode, CSSProperties, ButtonHTMLAttributes } from 'react';

/**
 * Bottone standard del Ceraldi ERP.
 * @startingPoint section="Core" subtitle="Bottoni: primary, secondary, ghost, stato" viewport="700x440"
 */
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Stile visivo. Default 'primary' (navy pieno). */
  variant?: 'primary' | 'secondary' | 'ghost' | 'outline' | 'success' | 'danger' | 'info' | 'warning';
  /** Dimensione. Default 'md'. */
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
  /** Icona Lucide a sinistra del testo. */
  iconLeft?: ReactNode;
  /** Icona Lucide a destra del testo. */
  iconRight?: ReactNode;
  children?: ReactNode;
  style?: CSSProperties;
}

export function Button(props: ButtonProps): JSX.Element;
export default Button;
