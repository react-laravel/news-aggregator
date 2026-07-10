import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "imgs.search.brave.com",
        port: "",
        pathname: "/**",
      },
    ],
    minimumCacheTTL: 24 * 60 * 60,
    maximumRedirects: 0,
    maximumResponseBody: 5 * 1024 * 1024,
    // Clash/TUN can map this public Brave host into 198.18.0.0/15. The strict
    // remotePatterns allowlist and disabled redirects keep the exception scoped.
    dangerouslyAllowLocalIP: true,
  },
};

export default nextConfig;
