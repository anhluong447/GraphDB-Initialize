import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/status': 'http://localhost:8080',
      '/graph': 'http://localhost:8080',
      '/communities': 'http://localhost:8080',
      '/community': 'http://localhost:8080',
      '/node': 'http://localhost:8080',
      '/functions': 'http://localhost:8080',
      '/commits': 'http://localhost:8080',
      '/sync': 'http://localhost:8080',
      '/query': 'http://localhost:8080',
      '/tasks': 'http://localhost:8080',
      '/owner': 'http://localhost:8080',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/setupTests.js',
    globals: true,
  },
})
