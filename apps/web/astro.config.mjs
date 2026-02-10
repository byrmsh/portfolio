import { defineConfig } from 'astro/config';
import svelte from '@astrojs/svelte';
import node from '@astrojs/node';
import tailwindcss from '@tailwindcss/vite';

// https://astro.build/config
export default defineConfig({
  output: 'server',
  adapter: node({ mode: 'standalone' }),
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
