import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Direct mapping for your Carnus endpoints
      '/tags': {
        target: 'https://wvnsdm2w30.execute-api.us-east-1.amazonaws.com/Prod',
        changeOrigin: true,
        secure: false,
      },
      '/image': {
        target: 'https://wvnsdm2w30.execute-api.us-east-1.amazonaws.com/Prod',
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
