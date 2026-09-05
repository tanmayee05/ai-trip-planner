/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // page + surfaces
        cream: "#F4F1FF", // soft lavender-white (kept the name; it's the app bg)
        paper: "#FFFFFF",
        ink: {
          DEFAULT: "#241C46", // deep indigo-black
          soft: "#5A5182",
          faint: "#9C96BC",
        },
        // primary — electric violet / indigo
        brand: {
          50: "#F1EDFF",
          100: "#E3DAFF",
          200: "#C6B4FF",
          300: "#A88DFF",
          400: "#8B6BFF",
          500: "#6C4CF1",
          600: "#5A38E0",
          700: "#4728B8",
          800: "#341E88",
          900: "#241663",
        },
        // secondary — bright aqua / cyan (kept the name "teal")
        teal: {
          100: "#CDF6FB",
          300: "#77E4F0",
          500: "#1FCBDE",
          600: "#10AEC1",
          700: "#0C8A99",
        },
        // supporting pops
        grape: "#B57BFF",
        sunny: "#FFB93B",
        sky: "#5B8DEF",
        bubble: "#FF5C8A", // hot pink — the warm counterpoint
        lime: "#37D98E",
      },
      fontFamily: {
        display: ['"Bricolage Grotesque"', "system-ui", "sans-serif"],
        sans: ['"Inter"', "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
      borderRadius: {
        xl: "1rem",
        "2xl": "1.5rem",
        "3xl": "2rem",
        "4xl": "2.5rem",
        blob: "42% 58% 63% 37% / 41% 44% 56% 59%",
      },
      boxShadow: {
        chunky: "0 4px 0 0 rgba(36,28,70,0.9)",
        "chunky-sm": "0 3px 0 0 rgba(36,28,70,0.85)",
        "chunky-lg": "0 7px 0 0 rgba(36,28,70,0.9)",
        pop: "0 14px 34px -10px rgba(36,28,70,0.30)",
        soft: "0 2px 10px -2px rgba(36,28,70,0.10), 0 10px 28px -10px rgba(36,28,70,0.16)",
        lift: "0 10px 24px -8px rgba(36,28,70,0.22), 0 24px 52px -14px rgba(36,28,70,0.24)",
        glow: "0 0 0 4px rgba(108,76,241,0.22)",
      },
      backgroundImage: {
        "brand-gradient": "linear-gradient(135deg, #8B6BFF 0%, #6C4CF1 50%, #4728B8 100%)",
        // "sunset" name kept — now a full aurora sweep
        "sunset":
          "linear-gradient(120deg, #1FCBDE 0%, #6C4CF1 38%, #FF5C8A 72%, #FFB93B 100%)",
        "mint": "linear-gradient(135deg, #77E4F0, #1FCBDE 60%, #10AEC1)",
        "dawn": "linear-gradient(160deg, #FF5C8A, #8B6BFF 60%, #5B8DEF)",
        "mesh":
          "radial-gradient(at 6% 10%, rgba(108,76,241,0.28) 0px, transparent 44%), radial-gradient(at 92% 4%, rgba(255,92,138,0.24) 0px, transparent 42%), radial-gradient(at 82% 94%, rgba(31,203,222,0.26) 0px, transparent 46%), radial-gradient(at 14% 92%, rgba(255,185,59,0.20) 0px, transparent 44%)",
      },
      keyframes: {
        "float-slow": {
          "0%,100%": { transform: "translateY(0) rotate(0deg)" },
          "50%": { transform: "translateY(-20px) rotate(6deg)" },
        },
        "pop-in": {
          "0%": { opacity: "0", transform: "scale(0.9) translateY(10px)" },
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
          "50%": { opacity: "1", transform: "scale(1.25)" },
        },
      },
      animation: {
        "float-slow": "float-slow 9s ease-in-out infinite",
        "pop-in": "pop-in 0.4s cubic-bezier(0.22,1,0.36,1) both",
        shimmer: "shimmer 1.6s infinite",
        "bounce-sm": "bounce-sm 1.8s ease-in-out infinite",
        "blob-morph": "blob-morph 20s ease-in-out infinite",
        twinkle: "twinkle 3.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
