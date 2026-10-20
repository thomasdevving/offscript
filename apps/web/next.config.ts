import type { NextConfig } from "next";

// Static export: the web app is plain HTML/JS served by Azure Static Web Apps (or any static host).
// It talks to the API (Azure Container Apps) over HTTPS + WebSocket; no secrets ship to the browser.
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
