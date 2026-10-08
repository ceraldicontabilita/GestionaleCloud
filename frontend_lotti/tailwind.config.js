/** @type {import('tailwindcss').Config} */

// Scala beige/sabbia: sostituisce le scale fredde (blu/indaco/viola) in tutta l'app.
const SAND = {
  50: '#faf7f0', 100: '#f3ead9', 200: '#e7d6b9', 300: '#d6bd92', 400: '#c2a06d',
  500: '#a8854f', 600: '#8a6f47', 700: '#6f583a', 800: '#56442d', 900: '#403220',
};

// Scala neutra calda: sostituisce le scale grigio-fredde di Tailwind (gray, slate).
// I valori 50/100/200/300/400/500/900 sono i token reali del design system Ceraldi
// (crema, bordo sottile, sabbia, thumb scrollbar, text-3, text-2, inchiostro);
// 600-800 e 950 interpolano fra text-2 e l'inchiostro.
const NEUTRAL = {
  50: '#faf7f0', 100: '#f0ebe0', 200: '#e6e0d4', 300: '#c7cfc2', 400: '#9aa593',
  500: '#6b7669', 600: '#5a6458', 700: '#495247', 800: '#384038', 900: '#2a3329',
  950: '#1c211b',
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
        success: { DEFAULT:'#3d8168', soft:'#e2efe8' },
        warning: { DEFAULT:'#c4894a', soft:'#f7ecdc' },
        danger:  { DEFAULT:'#d35f4e', soft:'#fbe6e2' },
        info:    { DEFAULT:'#8a6f47', soft:'#f3ead9' },
        surface: { DEFAULT:'#faf7f0', card:'#fffefb' },
        // Scale fredde rimappate sul beige (niente piu' blu/viola nei componenti).
        blue: SAND, indigo: SAND, sky: SAND, violet: SAND, purple: SAND,
        // Neutri: le scale gray/slate di Tailwind sono grigio-freddo, fuori palette.
        gray: NEUTRAL, slate: NEUTRAL, zinc: NEUTRAL, neutral: NEUTRAL,
        border:  { DEFAULT:'#e6e0d4', subtle:'#f0ebe0' },
        text:    { DEFAULT:'#2a3329', 2:'#6b7669', 3:'#9aa593' },
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
        card: '0 2px 10px rgba(63,90,78,.06)',
        list: '0 1px 6px rgba(63,90,78,.05)',
        md:   '0 4px 20px rgba(63,90,78,.10)',
        lg:   '0 8px 32px rgba(63,90,78,.14)',
        btn:  '0 4px 12px rgba(91,122,107,.22)',
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
