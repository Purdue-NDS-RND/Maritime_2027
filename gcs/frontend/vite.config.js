import {defineConfig} from 'vite';

// A separate frontend preview uses the existing backend and fresh page sessions.
// Bind locally and leave vehicle transports with the running GCS backend.
export default defineConfig({
    server: {
        host: '127.0.0.1',
        port: 8082,
        strictPort: true,
        proxy: {
            '/api': {
                target: 'http://127.0.0.1:8080',
                headers: {Origin: 'http://localhost:8080'},
            },
        },
    },
});
