import { CSSProperties, ReactNode } from 'react';

export interface TabItem {
  key: string;
  label: string;
  icon?: ReactNode;
}

export interface TabsProps {
  items: TabItem[];
  /** key del tab attivo. */
  value: string;
  onChange?: (key: string) => void;
  style?: CSSProperties;
}

/** Barra di tab a pillola; il tab attivo è navy pieno. */
export function Tabs(props: TabsProps): JSX.Element;
export default Tabs;
