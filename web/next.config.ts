import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  distDir: ".next",
  images: {
    remotePatterns: [
      { protocol: "http", hostname: "localhost", port: "9007" },
      { protocol: "http", hostname: "minio", port: "9000" },
    ],
  },
};

export default nextConfig;
