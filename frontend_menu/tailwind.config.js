/** @type {import('tailwindcss').Config} */

// Scala beige/sabbia e scala neutra calda: sostituiscono le scale fredde di Tailwind
// (blu/indaco/ciano/viola e i grigi gray/slate), come in frontend_lotti.
const SAND = {
  50: '#faf7f0', 100: '#f3ead9', 200: '#e7d6b9', 300: '#d6bd92', 400: '#c2a06d',
  500: '#a8854f', 600: '#8a6f47', 700: '#6f583a', 800: '#56442d', 900: '#403220',
};
const NEUTRAL = {
  50: '#faf7f0', 100: '#f0ebe0', 200: '#e6e0d4', 300: '#c7cfc2', 400: '#9aa593',
  500: '#6b7669', 600: '#5a6458', 700: '#495247', 800: '#384038', 900: '#2a3329',
  950: '#1c211b',
};

module.exports = {
    darkMode: ["class"],
    content: [
    "./src/**/*.{js,jsx,ts,tsx}",
    "./public/index.html"
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Plus Jakarta Sans', '-apple-system', 'system-ui', 'sans-serif'],
      },
      // Anello di focus di default: salvia, non il blu di Tailwind (design Ceraldi)
      ringColor: { DEFAULT: '#5b7a6b' },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)'
      },
      colors: {
        // Scale fredde rimappate su sabbia e neutro caldo (design Ceraldi).
        blue: SAND, indigo: SAND, sky: SAND, violet: SAND, purple: SAND,
        gray: NEUTRAL, slate: NEUTRAL, zinc: NEUTRAL, neutral: NEUTRAL,
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))'
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))'
        },
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))'
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))'
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))'
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))'
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))'
        },
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        chart: {
          '1': 'hsl(var(--chart-1))',
          '2': 'hsl(var(--chart-2))',
          '3': 'hsl(var(--chart-3))',
          '4': 'hsl(var(--chart-4))',
          '5': 'hsl(var(--chart-5))'
        }
      },
      keyframes: {
        'accordion-down': {
          from: {
            height: '0'
          },
          to: {
            height: 'var(--radix-accordion-content-height)'
          }
        },
        'accordion-up': {
          from: {
            height: 'var(--radix-accordion-content-height)'
          },
          to: {
            height: '0'
          }
        }
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out'
      }
    }
  },
  plugins: [require("tailwindcss-animate")],
};