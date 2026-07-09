import createNextIntlPlugin from 'next-intl/plugin';

const withNextIntl = createNextIntlPlugin('./src/i18n/request.ts');

/**
 * 백엔드 프록시 대상 — 동일 오리진화로 httpOnly 쿠키 인증 유지 (architecture.md A-1)
 * 기본값은 로컬 FastAPI. 배포 시 BACKEND_URL 환경변수로 교체.
 */
const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000';

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/api/v1/:path*',
        destination: `${BACKEND_URL}/api/v1/:path*`,
      },
    ];
  },
};

export default withNextIntl(nextConfig);
