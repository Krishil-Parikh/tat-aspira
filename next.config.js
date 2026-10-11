/** @type {import('next').NextConfig} */
const nextConfig = {
  // Required for Docker multi-stage build — emits a self-contained server.js
  output: 'standalone',

  // Next.js 15: serverComponentsExternalPackages moved from experimental to top-level
  serverExternalPackages: ['@radix-ui/react-icons'],

  images: {
    domains: ['localhost'],
  },
  env: {
    CUSTOM_KEY: process.env.CUSTOM_KEY,
  },
  async rewrites() {
    // API routing strategy:
    // 1. INTERNAL_API_URL: Docker/server-side rewrites (e.g., http://backend:8000)
    // 2. NEXT_PUBLIC_BACKEND_URL: Set in Vercel/Railway env vars (e.g., https://backend-prod.railway.app)
    // 3. NEXT_PUBLIC_API_URL: Legacy fallback
    // 4. http://localhost:8000: Local development default
    
    const apiBase =
      process.env.INTERNAL_API_URL ||          // Docker compose server rewrites
      process.env.NEXT_PUBLIC_BACKEND_URL ||   // Railway backend (Vercel env)
      process.env.NEXT_PUBLIC_API_URL ||       // Legacy env var
      'http://localhost:8000';                 // Local dev default

    return [
      {
        source: '/api/:path*',
        destination: `${apiBase}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
