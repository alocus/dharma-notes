import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";

// GitHub Pages project site: https://alocus.github.io/dharma-notes/
export default defineConfig({
  site: "https://alocus.github.io",
  base: "/dharma-notes",
  trailingSlash: "always",
  build: { format: "directory" },
  integrations: [sitemap()],
});
