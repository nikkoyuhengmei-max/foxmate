import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#FFF5EB',
          100: '#FFE8D6',
          200: '#FFD4AD',
          300: '#FFB985',
          400: '#FF9E5C',
          500: '#FF6B35',
          600: '#E55A2B',
          700: '#CC4A22',
          800: '#B33A19',
          900: '#992A10',
        },
        secondary: {
          50: '#FFF9F5',
          100: '#FFEDD6',
          200: '#FFDBAD',
          300: '#FFC985',
          400: '#FFB75C',
          500: '#FFA533',
          600: '#E5942B',
          700: '#CC8322',
          800: '#B37219',
          900: '#996110',
        },
      },
      fontFamily: {
        sans: ['Nunito', 'sans-serif'],
        display: ['Poppins', 'sans-serif'],
      },
      animation: {
        'bounce-slow': 'bounce 3s infinite',
        'float': 'float 3s ease-in-out infinite',
        'wiggle': 'wiggle 1s ease-in-out infinite',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-20px)' },
        },
        wiggle: {
          '0%, 100%': { transform: 'rotate(-3deg)' },
          '50%': { transform: 'rotate(3deg)' },
        },
      },
    },
  },
  plugins: [],
}
export default config
