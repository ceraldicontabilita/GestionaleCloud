/** @type {import('tailwindcss').Config} */

// Scala beige/sabbia: sostituisce le scale fredde (blu/indaco/viola) in tutta l'app.
const SAND = {
  50: '#faf7f0', 100: '#f3ead9', 200: '#e7d6b9', 300: '#d6bd92', 400: '#c2a06d',
  500: '#a8854f', 600: '#8a6f47', 700: '#6f583a', 800: '#56442d', 900: '#403220',
};

module.exports = {
  darkMode: ["class"],
  content: ["./src/**/*.{js,jsx,ts,tsx}", "./public/index.html"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Plus Jakarta Sans', '-apple-system', 'system-ui', 'sans-serif'],
      },
      colors: {
        primary: { DEFAULT:'#8a6f47', soft:'#f3ead9', grad:'#a8895e' },
        sidebar: '#4a3f33',
        success: { DEFAULT:'#00B884', soft:'#D4F5EA' },
        warning: { DEFAULT:'#FF9800', soft:'#FFE9CC' },
        danger:  { DEFAULT:'#F44336', soft:'#FFDAD7' },
        info:    { DEFAULT:'#8a6f47', soft:'#f3ead9' },
        surface: { DEFAULT:'#faf7f0', card:'#fffefb' },
        // Scale fredde rimappate sul beige (niente piu' blu/viola nei componenti).
        blue: SAND, indigo: SAND, sky: SAND, violet: SAND, purple: SAND,
        border:  { DEFAULT:'#E2E8F0', subtle:'#EDF2F7' },
        text:    { DEFAULT:'#0F172A', 2:'#64748B', 3:'#94A3B8' },
        /* shadcn compat */
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: { DEFAULT:'hsl(var(--card))', foreground:'hsl(var(--card-foreground))' },
        popover: { DEFAULT:'hsl(var(--popover))', foreground:'hsl(var(--popover-foreground))' },
        muted:   { DEFAULT:'hsl(var(--muted))', foreground:'hsl(var(--muted-foreground))' },
        accent:  { DEFAULT:'hsl(var(--accent))', foreground:'hsl(var(--accent-foreground))' },
        destructive: { DEFAULT:'hsl(var(--destructive))', foreground:'hsl(var(--destructive-foreground))' },
        input: 'hsl(var(--input))',
        ring:  'hsl(var(--ring))',
      },
      borderRadius: {
        DEFAULT: '12px', sm:'8px', lg:'16px', xl:'20px', '2xl':'24px',
      },
      boxShadow: {
        card: '0 2px 10px rgba(74,63,51,.06)',
        list: '0 1px 6px rgba(74,63,51,.05)',
        md:   '0 4px 20px rgba(74,63,51,.12)',
        lg:   '0 8px 32px rgba(74,63,51,.15)',
        btn:  '0 4px 12px rgba(74,63,51,.25)',
      },
      keyframes: {
        'accordion-down': { from:{height:'0'}, to:{height:'var(--radix-accordion-content-height)'} },
        'accordion-up':   { from:{height:'var(--radix-accordion-content-height)'}, to:{height:'0'} },
        'fade-in': { from:{opacity:0,transform:'translateY(8px)'}, to:{opacity:1,transform:'translateY(0)'} },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up':   'accordion-up 0.2s ease-out',
        'fade-in':        'fade-in 0.2s ease-out',
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
