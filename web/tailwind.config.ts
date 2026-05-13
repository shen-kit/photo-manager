import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#060816",
          900: "#0c1021",
          800: "#121936",
          700: "#1d2750",
        },
        cyan: {
          300: "#67e8f9",
          400: "#22d3ee",
          500: "#06b6d4",
        },
      },
      boxShadow: {
        panel: "0 16px 40px rgba(0, 0, 0, 0.28)",
      },
      backgroundImage: {
        "mesh-grid":
          "radial-gradient(circle at top, rgba(34,211,238,0.14), transparent 28%), linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px)",
      },
      backgroundSize: {
        "grid-size": "auto, 28px 28px, 28px 28px",
      },
    },
  },
  plugins: [],
};

export default config;
