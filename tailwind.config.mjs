import tailwindcssAnimate from "tailwindcss-animate";

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
  ],
  prefix: "",
  theme: {
    container: {
      center: true,
      padding: '2rem',
      screens: { '2xl': '1400px' },
    },
    extend: {
      colors: {
        /* Shadcn/Radix semantic tokens (RGB triplets → HSL bridge kept for compat) */
        border:      'rgb(var(--border) / <alpha-value>)',
        input:       'rgb(var(--input) / <alpha-value>)',
        ring:        'rgb(var(--ring) / <alpha-value>)',
        background:  'rgb(var(--background) / <alpha-value>)',
        foreground:  'rgb(var(--foreground) / <alpha-value>)',
        primary: {
          DEFAULT:    'rgb(var(--primary) / <alpha-value>)',
          foreground: 'rgb(var(--primary-foreground) / <alpha-value>)',
        },
        secondary: {
          DEFAULT:    'rgb(var(--secondary) / <alpha-value>)',
          foreground: 'rgb(var(--secondary-foreground) / <alpha-value>)',
        },
        destructive: {
          DEFAULT:    'rgb(var(--destructive) / <alpha-value>)',
          foreground: 'rgb(var(--destructive-foreground) / <alpha-value>)',
        },
        muted: {
          DEFAULT:    'rgb(var(--muted) / <alpha-value>)',
          foreground: 'rgb(var(--muted-foreground) / <alpha-value>)',
        },
        accent: {
          DEFAULT:    'rgb(var(--accent) / <alpha-value>)',
          foreground: 'rgb(var(--accent-foreground) / <alpha-value>)',
        },
        popover: {
          DEFAULT:    'rgb(var(--popover) / <alpha-value>)',
          foreground: 'rgb(var(--popover-foreground) / <alpha-value>)',
        },
        card: {
          DEFAULT:    'rgb(var(--card) / <alpha-value>)',
          foreground: 'rgb(var(--card-foreground) / <alpha-value>)',
        },
        chart: {
          '1': 'rgb(var(--chart-1) / <alpha-value>)',
          '2': 'rgb(var(--chart-2) / <alpha-value>)',
          '3': 'rgb(var(--chart-3) / <alpha-value>)',
          '4': 'rgb(var(--chart-4) / <alpha-value>)',
          '5': 'rgb(var(--chart-5) / <alpha-value>)',
        },

        /* Prototype ink scale */
        ink: {
          900: '#0A1628',
          800: '#0F2540',
          700: '#1F3A5F',
          500: '#4A5B74',
          400: '#6B7D97',
          300: '#95A4BD',
          200: '#C6D0E0',
          100: '#E6ECF5',
          50:  '#F3F6FB',
        },

        /* Prototype teal scale */
        teal: {
          700: '#0A5668',
          600: '#0E7490',
          500: '#0891B2',
          100: '#CFFAFE',
          50:  '#ECFEFF',
        },

        /* Prototype AI/indigo scale */
        ai: {
          700: '#4338CA',
          600: '#6366F1',
          500: '#818CF8',
          100: '#E0E7FF',
          50:  '#EEF2FF',
        },

        canvas: '#F6F8FB',

        /* Brand blue scale for new components */
        brand: {
          DEFAULT: 'var(--brand)',
          dark:    'var(--brand-dark)',
          deeper:  'var(--brand-deeper)',
        },
        surface: 'var(--surface)',
        label:   'var(--label)',

        /* Semantic colours kept for backwards compat references in existing code */
        gsblue:       '#0066cc',   /* updated → brand blue */
        gsgray:       '#0A1628',   /* remapped → ink-900 */
        customGray:   '#C6D0E0',   /* → ink-200 */
        thoughtYellow:'#FFFBEB',
        manuscriptBlue:'#0E7490',
        gsageGray:    '#6B7D97',   /* → ink-400 */
        gsageBlue:    '#6366F1',   /* → ai-600 */
        profileBlue:  '#E0E7FF',   /* → ai-100 */
      },

      fontFamily: {
        sans:    ['-apple-system', 'BlinkMacSystemFont', 'SF Pro Text', 'SF Pro Display', 'system-ui', 'Helvetica Neue', 'sans-serif'],
        mono:    ['JetBrains Mono', 'ui-monospace', 'Menlo', 'monospace'],
        /* Real Manrope (loaded in layout.tsx via next/font as --font-manrope),
           with system fallback if the webfont hasn't loaded yet. */
        manrope: ['var(--font-manrope)', '-apple-system', 'BlinkMacSystemFont', 'system-ui', 'sans-serif'],
        /* Signature script font (La Belle Aurore, self-hosted via next/font as
           --font-signature). Falls back to the platform `cursive` only if the
           webfont hasn't loaded yet. Drives the `font-signature` utility. */
        signature: ['var(--font-signature)', 'cursive'],
      },

      borderRadius: {
        'xl':  'var(--radius-xl)',
        lg:    'var(--radius-lg)',
        DEFAULT: 'var(--radius)',
        md:    'var(--radius)',
        sm:    'var(--radius-sm)',
      },

      boxShadow: {
        sm: 'var(--shadow-sm)',
        DEFAULT: 'var(--shadow)',
        lg: 'var(--shadow-lg)',
      },

      keyframes: {
        'accordion-down': { from: { height: '0' }, to: { height: 'var(--radix-accordion-content-height)' } },
        'accordion-up':   { from: { height: 'var(--radix-accordion-content-height)' }, to: { height: '0' } },
        shimmer:          { '0%': { backgroundPosition: '-200% 0' }, '100%': { backgroundPosition: '200% 0' } },
        shimmerSlide:     { '0%': { transform: 'translateX(-100%)' }, '100%': { transform: 'translateX(200%)' } },
        textShine:        { '0%': { backgroundPosition: '400% 50%' }, '100%': { backgroundPosition: '0% 50%' } },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up':   'accordion-up 0.2s ease-out',
        shimmer:          'shimmer 1.6s infinite linear',
        shimmerSlide:     'shimmerSlide 2s infinite',
        textShine:        'textShine 7s linear infinite',
      },

      cursor: {
        ban: 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'20\' height=\'20\' viewBox=\'0 0 24 24\' fill=\'none\' stroke=\'%23ffffff\' stroke-width=\'2\' stroke-linecap=\'round\' stroke-linejoin=\'round\'%3E%3Ccircle cx=\'12\' cy=\'12\' r=\'10\'/%3E%3Cpath d=\'m4.9 4.9 14.2 14.2\'/%3E%3C/svg%3E"), not-allowed',
      },
    },
  },
  plugins: [tailwindcssAnimate],
};
