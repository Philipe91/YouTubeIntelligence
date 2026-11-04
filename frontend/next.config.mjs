/** @type {import('next').NextConfig} */
const nextConfig = {
  poweredByHeader: false,
  // Imagens do laboratório passam pela ação do servidor. A API recusa o que passar de 5 MB.
  experimental: { serverActions: { bodySizeLimit: "6mb" } },
};

export default nextConfig;
