import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  // Habilita output standalone para Docker (gera server.js autocontido)
  output: "standalone",
};

export default nextConfig;
