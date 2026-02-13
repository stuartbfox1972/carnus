import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // 🟢 MANDATORY FIX for Amplify + Vite blank screen
  define: {
    global: 'window',
  },
  server: {
    host: true, // 🟢 Allows you to access from your desktop browser
    proxy: {
      '/tags': {
        target: 'https://9gzcy88gc0.execute-api.us-east-1.amazonaws.com/Prod',
        changeOrigin: true,
        secure: false,
      },
      '/image': {
        target: 'https://9gzcy88gc0.execute-api.us-east-1.amazonaws.com/Prod',
        changeOrigin: true,
        secure: false,
      },
      '/stats': {
        target: 'https://9gzcy88gc0.execute-api.us-east-1.amazonaws.com/Prod',
        changeOrigin: true,
        secure: false,
      },
    },
  },
});


Key                 UserPoolClientId
Description         -
Value               phk5na2ctttmm6tg94vtvb0d

Key                 CarnusApiUrl
Description         Base URL for the Carnus REST API
Value               https://9gzcy88gc0.execute-api.us-east-1.amazonaws.com/Prod/

Key                 UserPoolId
Description         -
Value               us-east-1_RwqEWHSYz
