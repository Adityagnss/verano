import { fileURLToPath } from "node:url"

import { defineConfig } from "vitest/config"

// `*.test.ts` run in plain node (fast, as before); `*.test.tsx` run in jsdom with Testing Library.
const alias = { "@": fileURLToPath(new URL("./src", import.meta.url)) }

export default defineConfig({
  resolve: { alias },
  esbuild: { jsx: "automatic" },
  test: {
    projects: [
      {
        resolve: { alias },
        test: { name: "node", include: ["src/**/*.test.ts"] },
      },
      {
        resolve: { alias },
        esbuild: { jsx: "automatic" },
        test: {
          name: "dom",
          environment: "jsdom",
          include: ["src/**/*.test.tsx"],
          setupFiles: ["./src/test/setup.ts"],
        },
      },
    ],
  },
})
