const backend = process.env.CAMPUSFLOW_API_ORIGIN

if (!backend || !/^https:\/\/[a-z0-9.-]+(?::\d+)?$/i.test(backend)) {
  throw new Error('Set CAMPUSFLOW_API_ORIGIN to the HTTPS origin of the Render service.')
}

export const config = {
  framework: 'vite',
  installCommand: 'corepack pnpm install --frozen-lockfile',
  buildCommand: 'corepack pnpm run build',
  outputDirectory: 'dist',
  rewrites: [
    { source: '/api/:path*', destination: `${backend}/api/:path*` },
    { source: '/((?!assets/|api/).*)', destination: '/index.html' },
  ],
}
