const nextConfig = {
  images: {
    unoptimized: true,
  },
  async rewrites() {
    return [{ source: '/api/:path((?!auth/).*)', destination: `${process.env.RHIZO_API_URL ?? 'http://localhost:8000'}/api/:path` }]
  },
}

export default nextConfig
