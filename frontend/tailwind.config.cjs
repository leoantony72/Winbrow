/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  corePlugins: { preflight: false },
  theme: {
    extend: {
      colors: {
        border: 'hsl(var(--ui-border) / <alpha-value>)',
        input: 'hsl(var(--ui-border) / <alpha-value>)',
        ring: 'hsl(var(--ui-primary) / <alpha-value>)',
        background: 'hsl(var(--ui-background) / <alpha-value>)',
        foreground: 'hsl(var(--ui-foreground) / <alpha-value>)',
        primary: { DEFAULT: 'hsl(var(--ui-primary) / <alpha-value>)', foreground: '#fff' },
        secondary: { DEFAULT: '#eef2ef', foreground: '#283d34' },
        accent: { DEFAULT: '#e7eee8', foreground: '#283d34' },
        destructive: { DEFAULT: '#b91c1c', foreground: '#fff' },
      },
    },
  },
  plugins: [],
};
