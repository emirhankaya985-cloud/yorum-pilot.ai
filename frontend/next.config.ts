import type { NextConfig } from 'next';
const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    const origin = process.env.BACKEND_INTERNAL_URL ?? 'http://localhost:8000';
    return [{source: '/api/:path*', destination: `${origin}/api/:path*`},
            {source: '/healthz', destination: `${origin}/healthz`}];
  },
  async headers(){
    return [{source:'/:path*',headers:[
      {key:'X-Content-Type-Options',value:'nosniff'},
      {key:'Referrer-Policy',value:'strict-origin-when-cross-origin'},
      {key:'X-Frame-Options',value:'DENY'}
    ]}];
  }
};
export default nextConfig;
