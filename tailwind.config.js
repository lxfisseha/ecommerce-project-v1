/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/templates/**/*.html",
  ],
  theme: {
    extend: {
      fontFamily: {
        display: ['Anton SC', 'Inter', 'sans-serif'],
      },
      colors: {
        primary: {
          DEFAULT: '#333333',
          hover: '#1F1F1F',
        },
        accent: '#963484',
        danger: '#C44536',
        warning: '#B45309',
        success: {
          DEFAULT: '#4F8A65',
          dark: '#3A694B',
          light: '#EDF5F0'
        },
        info: {
          DEFAULT: '#407899',
          dark: '#2E5A73',
          light: '#4C8BC4'
        },
        text: {
          main: '#2B2624',
          muted: '#524B48',
          light: '#7A736F',
        },
        bg: {
          main: '#FAF9F8',
          alt: '#F5F3F1',
          muted: '#E8E5E3',
          hover: '#F0ECE9',
        },
        border: {
          main: '#D0CBC7',
          dark: '#B5B0AD'
        }
      }
    }
  },
  plugins: [],
}
