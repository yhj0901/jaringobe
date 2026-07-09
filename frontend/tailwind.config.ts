import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f0faf4',
          100: '#dbf2e4',
          500: '#16a35f',
          600: '#0e8a4f',
          700: '#0b6e40',
        },
      },
    },
  },
  plugins: [],
};

export default config;
