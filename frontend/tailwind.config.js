/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Space Grotesk"', 'Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        bg: '#07080b',
        surface: '#0f1117',
        raised: '#161922',
        line: '#252a36',
        ink: '#f1f3f8',
        dim: '#98a1b3',
        faint: '#636c7f',
        volt: '#c6ff3d',
        ice: '#4fd8ff',
        ember: '#ff8a3d',
        rose: '#ff4d6a',
        grape: '#a78bfa',
        mint: '#34e0a1',
        amber: '#ffc43d',
      },
    },
  },
  plugins: [],
}
