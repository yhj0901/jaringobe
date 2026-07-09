import type { Config } from 'tailwindcss';

/**
 * 디자인 토큰 — Claude Design 프로토타입(jaringobe-app-design)과 공통 팔레트.
 * 네이비(#0B1B3A) 히어로 · 블루(#2F6BFF) 프라이머리 · 그린(#0FB07A) 자동주문 · 오렌지(#E0651A) 임박 경고.
 */
const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        /** 프라이머리 블루 (기존 brand 팔레트를 디자인 블루로 재매핑) */
        brand: {
          50: '#EAF0FF',
          100: '#DCE7FF',
          400: '#5B8CFF',
          500: '#4A7BFF',
          600: '#2F6BFF',
          700: '#2453D6',
        },
        /** 네이비 — 예산 락 히어로/로그인 배경 */
        navy: {
          700: '#1C2E58',
          800: '#15244A',
          900: '#0B1B3A',
        },
        /** 그린 — 절약/자동주문 */
        mint: {
          50: '#E6F8F1',
          300: '#36E0A6',
          500: '#0FB07A',
          600: '#0A8A60',
          700: '#0A6E4E',
        },
        /** 오렌지 — 유통기한 임박 경고 */
        flame: {
          50: '#FEF3E2',
          200: '#FCE7CF',
          500: '#E0651A',
          600: '#C2761F',
        },
        /** 텍스트 잉크 스케일 */
        ink: {
          300: '#9AA6BD',
          400: '#8A95AD',
          500: '#5B6B8C',
          600: '#3A4A66',
          800: '#16223B',
          900: '#0B1B3A',
        },
        /** 배경/면 */
        surface: {
          DEFAULT: '#E9ECF1',
          app: '#EEF1F6',
          line: '#E7EBF3',
        },
        kakao: '#FEE500',
      },
      fontFamily: {
        sans: [
          'Pretendard Variable',
          'Pretendard',
          '-apple-system',
          'BlinkMacSystemFont',
          'system-ui',
          'Segoe UI',
          'sans-serif',
        ],
      },
      boxShadow: {
        card: '0 1px 2px rgba(16,30,60,.04), 0 8px 22px rgba(16,30,60,.05)',
        hero: '0 16px 34px rgba(11,27,58,.30)',
        mint: '0 12px 26px rgba(10,110,78,.28)',
        cta: '0 10px 24px rgba(47,107,255,.32)',
        sheet: '0 -12px 40px rgba(11,27,58,.18)',
      },
    },
  },
  plugins: [],
};

export default config;
