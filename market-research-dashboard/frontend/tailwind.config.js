/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ml: {
          bg: {
            canvas: '#0B1120',
            surface: '#111827',
            card: '#0F172A',
            elevated: '#152033',
          },
          border: {
            DEFAULT: '#23314C',
            strong: '#314261',
          },
          text: {
            primary: '#E5EEF8',
            secondary: '#AAB8CF',
            muted: '#7D8BA7',
            inverse: '#09101F',
          },
          state: {
            green: '#22C55E',
            yellow: '#EAB308',
            orange: '#F97316',
            red: '#EF4444',
            blocked: '#64748B',
          },
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      borderRadius: {
        card: '20px',
        chip: '9999px',
      },
      boxShadow: {
        'ml-card': '0 8px 24px rgba(0,0,0,0.28)',
        'ml-card-hover': '0 14px 34px rgba(0,0,0,0.34)',
      },
    },
  },
  plugins: [],
};
