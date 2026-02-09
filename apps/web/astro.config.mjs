import { defineConfig } from 'astro/config';
import svelte from '@astrojs/svelte';
import tailwindcss from '@tailwindcss/vite';

// https://astro.build/config
export default defineConfig({
  integrations: [svelte()],
  vite: {
    plugins: [tailwindcss()],
    server: {
      // Local dev: let the browser call /api/* on the Astro origin, then proxy to the API.
      proxy: {
        '/api': 'http://localhost:3000',
      },
    },
  },
});
