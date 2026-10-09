import { defineConfig } from 'astro/config';
import node from '@astrojs/node';

// Pages stay pre-rendered (static, fast). Only routes that set
// `export const prerender = false` (the currency API and the admin) run on the server.
export default defineConfig({
  devToolbar: { enabled: false },
  adapter: node({ mode: 'standalone' }),
});
