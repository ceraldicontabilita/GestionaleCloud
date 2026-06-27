import { CSSProperties, SelectHTMLAttributes, ReactNode } from 'react';

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  children?: ReactNode;
  style?: CSSProperties;
}

/** Menù a tendina nativo coerente con Input. */
export function Select(props: SelectProps): JSX.Element;
export default Select;
