import type { MetadataRoute } from 'next';

/**
 * PWA 웹 앱 manifest — 홈 화면 설치(standalone) 지원.
 * 안드로이드는 정사각 192/512 + maskable 아이콘을 요구한다.
 * next-intl 로캘 프리픽스 구조라 start_url 은 기본 로캘(/ko).
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'JARINGOBE 자린고비',
    short_name: '자린고비',
    description: '예산 안에서 식단을 자동으로 짜고, 버리는 식재료를 0으로 만드는 알뜰 식생활 플랫폼',
    start_url: '/ko',
    scope: '/',
    display: 'standalone',
    orientation: 'portrait',
    background_color: '#E9ECF1',
    theme_color: '#0B1B3A',
    lang: 'ko',
    icons: [
      { src: '/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
      { src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
      { src: '/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
    ],
  };
}
