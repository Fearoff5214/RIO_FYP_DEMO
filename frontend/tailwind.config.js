/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        novaliseo: {
          blue: '#1E3A8A',
          light: '#3B82F6',
          dark: '#0F172A',
        },
      },
    },
  },
  plugins: [],
}
