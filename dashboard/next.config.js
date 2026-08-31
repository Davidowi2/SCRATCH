/** @type {import('next').NextConfig} */
const nextConfig = {
  env: {
    API_URL: process.env.API_URL || 'http://localhost:5000',
    API_KEY: process.env.API_KEY || 'your-secret-api-key-change-this',
  },
}

module.exports = nextConfig
