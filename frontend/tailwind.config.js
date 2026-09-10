/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        /* ---------------------------------------------------------------
         * "Golden Hour Voyage" — a travel palette.
         * Midnight navy (night flights, departure boards) grounds warm
         * map-paper cream. Ocean azure leads, lagoon turquoise supports,
         * sunset coral + brass gold carry the golden-hour warmth.
         * ------------------------------------------------------------- */
        cream: "#F6F2EB", // warm map paper
        paper: "#FFFFFF",
        sand: "#EFE7DA", // aged chart edge
        ink: {
          DEFAULT: "#0E1B2C", // midnight navy
          soft: "#46596F",
          faint: "#8698AC",
        },
        // primary — deep ocean azure
        brand: {
          50: "#EEF6FC",
          100: "#D8EAF7",
          200: "#AFD3EE",
          300: "#7EB7E0",
          400: "#4C97CE",
          500: "#2176AE",
          600: "#175E8E",
          700: "#12486D",
          800: "#0E3652",
          900: "#0B2839",
        },
        // secondary — lagoon turquoise
        teal: {
          100: "#D6F5F0",
          300: "#7FE3D6",
          500: "#2EC4B6",
          600: "#1FA396",
          700: "#167B72",
        },
        // supporting pops
        sunny: "#E8A33D", // brass compass / sunlit sand
        sky: "#6FA8DC", // clear horizon
        bubble: "#F4784F", // sunset coral — the warm counterpoint
        lime: "#3FBF8F", // jade
        grape: "#7A6A9B", // dusk plum
      },
      fontFamily: {
        display: ['"Bricolage Grotesque"', "system-ui", "sans-serif"],
        sans: ['"Inter"', "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
      borderRadius: {
        xl: "1rem",
        "2xl": "1.25rem",
        "3xl": "1.75rem",
        "4xl": "2.25rem",
        blob: "42% 58% 63% 37% / 41% 44% 56% 59%",
      },
      boxShadow: {
        /* names kept for compatibility — values are now soft & layered
           instead of hard sticker-book offsets */
        chunky:
          "0 1px 2px rgba(14,27,44,0.05), 0 4px 14px -3px rgba(14,27,44,0.10)",
        "chunky-sm":
          "0 1px 2px rgba(14,27,44,0.06), 0 2px 8px -2px rgba(14,27,44,0.10)",
        "chunky-lg":
          "0 2px 4px rgba(14,27,44,0.06), 0 16px 34px -10px rgba(14,27,44,0.18)",
        pop: "0 18px 44px -14px rgba(14,27,44,0.30)",
        soft: "0 1px 2px rgba(14,27,44,0.05), 0 8px 24px -10px rgba(14,27,44,0.14)",
        lift: "0 10px 28px -10px rgba(14,27,44,0.24), 0 30px 60px -20px rgba(14,27,44,0.22)",
        glow: "0 0 0 4px rgba(33,118,174,0.18)",
        inset: "inset 0 1px 0 0 rgba(255,255,255,0.6)",
      },
      backgroundImage: {
        "brand-gradient": "linear-gradient(135deg, #4C97CE 0%, #2176AE 55%, #12486D 100%)",
        // golden hour: night -> dusk -> sunset -> gold
        sunset:
          "linear-gradient(120deg, #12486D 0%, #2176AE 26%, #7A6A9B 52%, #F4784F 80%, #E8A33D 100%)",
        ocean: "linear-gradient(135deg, #7FE3D6 0%, #2EC4B6 45%, #167B72 100%)",
        dawn: "linear-gradient(160deg, #F4784F 0%, #E8A33D 55%, #7FE3D6 100%)",
        dusk: "linear-gradient(135deg, #0E1B2C 0%, #12486D 50%, #7A6A9B 100%)",
        mesh:
          "radial-gradient(at 4% 8%, rgba(33,118,174,0.20) 0px, transparent 46%), radial-gradient(at 94% 2%, rgba(244,120,79,0.16) 0px, transparent 44%), radial-gradient(at 84% 92%, rgba(46,196,182,0.18) 0px, transparent 48%), radial-gradient(at 12% 94%, rgba(232,163,61,0.14) 0px, transparent 46%)",
      },
      keyframes: {
        "float-slow": {
          "0%,100%": { transform: "translateY(0) rotate(0deg)" },
          "50%": { transform: "translateY(-20px) rotate(6deg)" },
        },
        "pop-in": {
          "0%": { opacity: "0", transform: "scale(0.96) translateY(10px)" },
          "100%": { opacity: "1", transform: "scale(1) translateY(0)" },
        },
        shimmer: { "100%": { transform: "translateX(100%)" } },
        "bounce-sm": {
          "0%,100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
        "blob-morph": {
          "0%,100%": {
            borderRadius: "42% 58% 63% 37% / 41% 44% 56% 59%",
            transform: "translate3d(0,0,0) rotate(0deg) scale(1)",
          },
          "33%": {
            borderRadius: "67% 33% 47% 53% / 37% 62% 38% 63%",
            transform: "translate3d(4%,-5%,0) rotate(35deg) scale(1.06)",
          },
          "66%": {
            borderRadius: "39% 61% 33% 67% / 63% 38% 62% 37%",
            transform: "translate3d(-4%,4%,0) rotate(-28deg) scale(0.96)",
          },
        },
        twinkle: {
          "0%,100%": { opacity: "0.15", transform: "scale(0.7)" },
          "50%": { opacity: "1", transform: "scale(1.2)" },
        },
        /* ---- new, travel-flavoured ---- */
        "gradient-pan": {
          "0%,100%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
        },
        drift: {
          "0%": { transform: "translateX(-8%)" },
          "100%": { transform: "translateX(108%)" },
        },
        "spin-slow": {
          "0%": { transform: "rotate(0deg)" },
          "100%": { transform: "rotate(360deg)" },
        },
        "dash-flow": { "100%": { strokeDashoffset: "-120" } },
        rise: {
          "0%": { opacity: "0", transform: "translateY(14px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(0.85)", opacity: "0.55" },
          "100%": { transform: "scale(1.9)", opacity: "0" },
        },
        sheen: {
          "0%": { transform: "translateX(-120%) skewX(-18deg)" },
          "60%,100%": { transform: "translateX(220%) skewX(-18deg)" },
        },
      },
      animation: {
        "float-slow": "float-slow 9s ease-in-out infinite",
        "pop-in": "pop-in 0.45s cubic-bezier(0.22,1,0.36,1) both",
        shimmer: "shimmer 1.6s infinite",
        "bounce-sm": "bounce-sm 1.8s ease-in-out infinite",
        "blob-morph": "blob-morph 22s ease-in-out infinite",
        twinkle: "twinkle 3.4s ease-in-out infinite",
        "gradient-pan": "gradient-pan 14s ease infinite",
        drift: "drift 42s linear infinite",
        "spin-slow": "spin-slow 26s linear infinite",
        "dash-flow": "dash-flow 2.4s linear infinite",
        rise: "rise 0.5s cubic-bezier(0.22,1,0.36,1) both",
        "pulse-ring": "pulse-ring 2.4s cubic-bezier(0.22,1,0.36,1) infinite",
        sheen: "sheen 4.5s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
