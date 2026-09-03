/** Tailwind SOLO per il modulo Menu (frontend/src/menu/**): il resto del
 *  gestionale usa stili inline e index.css. Preflight spento per non toccare
 *  il resto dell'app; il reset minimo che serve ai componenti sta in
 *  src/menu/menu.css (scoped a .menu-root). I token shadcn sono rinominati
 *  --menu-* per non collidere con le variabili globali (--border, --primary
 *  del modulo HR). */
module.exports = {
  content: ['./src/menu/**/*.{js,jsx}'],
  corePlugins: { preflight: false },
  theme: {
    extend: {
      borderRadius: {
        lg: 'var(--menu-radius)',
        md: 'calc(var(--menu-radius) - 2px)',
        sm: 'calc(var(--menu-radius) - 4px)',
      },
      colors: {
        background: 'hsl(var(--menu-background))',
        foreground: 'hsl(var(--menu-foreground))',
        card: { DEFAULT: 'hsl(var(--menu-card))', foreground: 'hsl(var(--menu-card-foreground))' },
        popover: { DEFAULT: 'hsl(var(--menu-popover))', foreground: 'hsl(var(--menu-popover-foreground))' },
        primary: { DEFAULT: 'hsl(var(--menu-primary))', foreground: 'hsl(var(--menu-primary-foreground))' },
        secondary: { DEFAULT: 'hsl(var(--menu-secondary))', foreground: 'hsl(var(--menu-secondary-foreground))' },
        muted: { DEFAULT: 'hsl(var(--menu-muted))', foreground: 'hsl(var(--menu-muted-foreground))' },
        accent: { DEFAULT: 'hsl(var(--menu-accent))', foreground: 'hsl(var(--menu-accent-foreground))' },
        destructive: { DEFAULT: 'hsl(var(--menu-destructive))', foreground: 'hsl(var(--menu-destructive-foreground))' },
        border: 'hsl(var(--menu-border))',
        input: 'hsl(var(--menu-input))',
        ring: 'hsl(var(--menu-ring))',
        sage: { DEFAULT: '#5b7a6b', dark: '#3f5a4e', soft: '#e8efe9' },
        cream: '#faf7f0',
        sand: '#e6e0d4',
        gold: { DEFAULT: '#d4af37', dark: '#c9a332' },
      },
    },
  },
  plugins: [],
};
