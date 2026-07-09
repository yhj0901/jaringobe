import { setRequestLocale } from 'next-intl/server';
import { OnboardingWizard } from '@/features/household/OnboardingWizard';

interface OnboardingPageProps {
  params: { locale: string };
  searchParams: { imported?: string };
}

/**
 * 온보딩 (`/onboarding`) — 3스텝 위저드 실화면 (ui-design 8장, FR-311~315).
 * ?imported=1 (게스트 예산안 이전 성공, FR-108) 이면 확인 화면 후 STEP1 진입.
 */
export default function OnboardingPage({ params: { locale }, searchParams }: OnboardingPageProps) {
  setRequestLocale(locale);
  return <OnboardingWizard imported={searchParams.imported === '1'} />;
}
