import type { Config } from "tailwindcss";

const config: Config = {
    content: ["./src/**/*.{ts,tsx}"],
    darkMode: "class",
    // Scope Tailwind to elements with the 'tw-root' class so it doesn't clash with Flask CSS
    important: ".tw-root",
    theme: {
        extend: {},
    },
    plugins: [],
};

export default config;
