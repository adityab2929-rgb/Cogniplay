/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,jsx}', './public/index.html'],
  theme: {
    extend: {
      colors: {
        sky: { soft: '#DCEEFF' },
        garden: { soft: '#DFF5E1' },
        lavender: { soft: '#EDE4FF' },
        risk: { low: '#22C55E', moderate: '#F59E0B', high: '#EF4444' },
      },
      fontFamily: {
        // Rounded, high-legibility face - important for a dyslexia-screening UI.
        kid: ['"Baloo 2"', '"Comic Sans MS"', 'system-ui', 'sans-serif'],
      },
      keyframes: {
        pop: { '0%': { transform: 'scale(1)' }, '100%': { transform: 'scale(0)', opacity: '0' } },
        wiggle: { '0%,100%': { transform: 'rotate(-3deg)' }, '50%': { transform: 'rotate(3deg)' } },
      },
      animation: { pop: 'pop 0.3s ease-out forwards', wiggle: 'wiggle 0.4s ease-in-out' },
    },
  },
  plugins: [],
};
