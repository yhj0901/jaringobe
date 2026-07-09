import path from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    css: false,
    coverage: {
      provider: 'v8',
      // 커버리지 대상: 도메인 로직/컴포넌트 (features + shared).
      // app/ 라우트·middleware·i18n 설정은 프레임워크 글루로 빌드에서 검증.
      include: ['src/features/**', 'src/shared/**'],
      exclude: ['src/features/**/sample-matrix/**'],
      thresholds: {
        lines: 90,
        statements: 90,
        functions: 90,
        branches: 90,
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@messages': path.resolve(__dirname, './messages'),
    },
  },
});
