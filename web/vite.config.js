import { sveltekit } from '@sveltejs/kit/vite';

export default {
  plugins: [sveltekit()],
  server: {
    // Bound to all interfaces so you can reach it from a phone at the machine.
    host: true,
    port: 5173
  }
};
