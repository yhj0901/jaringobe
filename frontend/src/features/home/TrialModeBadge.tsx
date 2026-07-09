import { useTranslations } from 'next-intl';
import { Badge } from '@/shared/ui/Badge';

/** 게스트일 때 상시 노출되는 "체험 모드" 배지 (FR-101) */
export function TrialModeBadge() {
  const t = useTranslations('guestHome');
  return <Badge tone="brand">{t('trialBadge.label')}</Badge>;
}
