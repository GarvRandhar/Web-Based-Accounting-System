import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            "@": path.resolve(__dirname, "./src"),
        },
    },
    build: {
        outDir: "../app/static/react",
        emptyOutDir: true,
        rollupOptions: {
            input: path.resolve(__dirname, "src/main.tsx"),
            output: {
                entryFileNames: "sidebar.js",
                assetFileNames: "sidebar.[ext]",
            },
        },
    },
});
