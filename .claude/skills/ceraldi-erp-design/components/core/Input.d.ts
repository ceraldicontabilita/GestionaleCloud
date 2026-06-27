import { CSSProperties, InputHTMLAttributes, ReactNode } from 'react';

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  /** Bordo rosso di errore. */
  error?: boolean;
  /** Icona Lucide a sinistra (es. Search). */
  iconLeft?: ReactNode;
  style?: CSSProperties;
}

/** Campo testo standard del Ceraldi ERP. */
export function Input(props: InputProps): JSX.Element;
export default Input;
