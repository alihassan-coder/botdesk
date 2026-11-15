import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  // The Docker image (apps/web/Dockerfile) sets BOTDESK_STANDALONE=true to get a self-contained
  // server in .next/standalone. Off otherwise, so `next start` (e2e) keeps working as before.
  output: process.env.BOTDESK_STANDALONE === "true" ? "standalone" : undefined,
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
