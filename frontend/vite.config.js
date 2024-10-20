import { defineConfig } from "vite";
import jsconfigPaths from "vite-jsconfig-paths";
import { resolve } from "path";

export default defineConfig({
  plugins: [jsconfigPaths()],
  esbuild: {
    jsx: "transform",
    jsxInject: `import { h } from '@/lib/jsx/jsx-runtime'`,
    jsxFactory: "h",
    minify: false,
    legalComments: "none",
  },
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, "src/main.jsx"),
        // 필요한 다른 파일을 추가할 수 있습니다.
      },
      output: {
        dir: "dist",
        entryFileNames: "[name].js",
      },
      manualChunks(id) {
        if (id.includes("node_modules")) {
          return "vendor";
        }
      },
    },
    outDir: "dist",
    minify: false,
    chunkSizeWarningLimit: 1000,
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
      "@img": resolve(__dirname, "img"),
    },
  },
});
