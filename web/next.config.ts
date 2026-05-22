import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  eslint: {
    ignoreDuringBuilds: true,
  },
  distDir: ".next",
  images: {
    remotePatterns: [
      { protocol: "http", hostname: "localhost", port: "9007" },
      { protocol: "http", hostname: "minio", port: "9000" },
      // Supabase Storage (production imagery)
      { protocol: "https", hostname: "*.supabase.co" },
    ],
  },
};

export default nextConfig;
