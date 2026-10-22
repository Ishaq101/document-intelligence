import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#173434",
        teal: { 50: "#f1f8f8", 100: "#dceeee", 400: "#91BBBB", 600: "#429393", 700: "#337575" },
        olive: "#9C9D6E",
        kirana: { navy: "#0b2b3a", teal: "#0b5f5a", gold: "#d7a53a", mist: "#f2f6f5" },
      },
    },
  },
  plugins: [],
};

export default config;
