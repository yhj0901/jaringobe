import type { ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { Badge } from '@/shared/ui/Badge';
import { TrialModeBadge } from '@/features/home/TrialModeBadge';
import { BudgetMoodCard } from '@/features/home/BudgetMoodCard';
import { MealPlanSection } from '@/features/home/MealPlanSection';
import { FridgePreviewCard } from '@/features/home/FridgePreviewCard';
import { AutoOrderCard } from '@/features/home/AutoOrderCard';
import { LockedFeatureCard } from '@/features/mealplan/LockedFeatureCard';
import type { HomeViewModel, MealItem } from '@/features/home/types';

export type LockedTab = 'meal' | 'fridge' | 'cart';

interface HomeShellProps {
  viewModel: HomeViewModel;
  /** [member 옵셔널 확장] 회원 샘플 홈 — 체험 배지 숨김, "예시" 라벨은 유지 (ui-design 8장) */
  hideTrialBadge?: boolean;
  onAutoOrderStart?: () => void;
  /** 끼니 행 클릭 → 레시피 시트 (FR-504) — 클릭된 끼니를 전달 */
  onRecipeClick?: (meal: MealItem) => void;
  /** 하단 탭바의 잠긴 탭(식단/냉장고/장바구니) 클릭 — 게스트는 가입 게이트 (FR-109), 회원은 탭별 분기 (FR-208) */
  onLockedNavClick?: (tab: LockedTab) => void;
  /** [member 옵셔널 확장] 헤더 아래 배너 슬롯 — 예산 초과/에러 배너 (FR-206) */
  topSlot?: ReactNode;
  /** [member 옵셔널 확장] 주간 스트립 일자 이동 (FR-205) */
  onSelectDate?: (date: string) => void;
  /** [member 옵셔널 확장] 전체 재생성 버튼 (FR-209) */
  onRegenerateClick?: () => void;
  /** [member 옵셔널 확장] 끼니 완료 토글 (FR-501) — 제공 시 완료 버튼 노출 */
  onToggleMealComplete?: (meal: MealItem) => void;
  /** [member 옵셔널 확장] 완료 토글 진행 중 끼니 id (FR-503) */
  pendingMealIds?: ReadonlySet<string>;
  /** 하단 "마이" 탭 클릭 — 회원: /settings 이동, 게스트: 가입 게이트 (ui-design 9장, FR-401) */
  onMyTabClick?: () => void;
  /** [member 옵셔널 확장] country != KR 시 "글로벌" 배지 노출 (FR-605, ui-design 12장) */
  globalBadge?: boolean;
}

/** 하단 탭바 아이콘 — 디자인 마크업의 인라인 SVG 재사용 */
function NavIcon({ tab, active }: { tab: 'home' | 'my' | LockedTab; active: boolean }) {
  const stroke = active ? '#2F6BFF' : '#9AA6BD';
  switch (tab) {
    case 'home':
      return (
        <svg aria-hidden width="24" height="24" viewBox="0 0 24 24" fill="none">
          <path
            d="M4 11.5 12 5l8 6.5V20a1 1 0 0 1-1 1h-4v-6h-6v6H5a1 1 0 0 1-1-1z"
            stroke={stroke}
            strokeWidth="1.9"
            strokeLinejoin="round"
          />
        </svg>
      );
    case 'meal':
      return (
        <svg aria-hidden width="24" height="24" viewBox="0 0 24 24" fill="none">
          <path
            d="M3.5 11.5h17a8 8 0 0 1-8 7.5h-1a8 8 0 0 1-8-7.5z"
            stroke={stroke}
            strokeWidth="1.9"
            strokeLinejoin="round"
          />
          <path
            d="M8 8c0-1.6 1-2.5 1-4M12 8c0-1.6 1-2.5 1-4M16 8c0-1.6 1-2.5 1-4"
            stroke={stroke}
            strokeWidth="1.7"
            strokeLinecap="round"
          />
        </svg>
      );
    case 'fridge':
      return (
        <svg aria-hidden width="24" height="24" viewBox="0 0 24 24" fill="none">
          <rect x="6" y="3" width="12" height="18" rx="2.5" stroke={stroke} strokeWidth="1.9" />
          <path d="M6 10h12" stroke={stroke} strokeWidth="1.9" />
          <path
            d="M9 6.5v1.5M9 12.5V14"
            stroke={stroke}
            strokeWidth="1.9"
            strokeLinecap="round"
          />
        </svg>
      );
    case 'cart':
      return (
        <svg aria-hidden width="24" height="24" viewBox="0 0 24 24" fill="none">
          <circle cx="9" cy="20" r="1.5" stroke={stroke} strokeWidth="1.6" />
          <circle cx="18" cy="20" r="1.5" stroke={stroke} strokeWidth="1.6" />
          <path
            d="M2.5 4h2L7 15.2a1.5 1.5 0 0 0 1.5 1.2h8.5a1.5 1.5 0 0 0 1.5-1.2L20.5 7H6"
            stroke={stroke}
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
    case 'my':
      return (
        <svg aria-hidden width="24" height="24" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="8" r="3.5" stroke={stroke} strokeWidth="1.9" />
          <path
            d="M5 20a7 7 0 0 1 14 0"
            stroke={stroke}
            strokeWidth="1.9"
            strokeLinecap="round"
          />
        </svg>
      );
  }
}

// '식단'(meal)은 프리미엄 구독 편입 예정 기능 — 탭은 노출하되 클릭 시 구독 안내
const LOCKED_TABS: LockedTab[] = ['meal', 'fridge', 'cart'];

/**
 * 홈 셸 — 게스트/회원 공용, HomeViewModel 주입형 (FR-101, architecture.md A-2).
 * 데이터 소스를 모른다: 게스트 샘플이든 회원 실데이터든 같은 형태로 받는다.
 * 시각 구성은 Claude Design 프로토타입 home 화면 재현: 인사 헤더 → 예산 락 히어로 →
 * 절약 스트립 → 오늘 식단 카드 → 냉장고 위젯 → 자동주문 카드 → 하단 탭바.
 */
export function HomeShell({
  viewModel,
  hideTrialBadge = false,
  onAutoOrderStart,
  onRecipeClick,
  onLockedNavClick,
  topSlot,
  onSelectDate,
  onRegenerateClick,
  onMyTabClick,
  onToggleMealComplete,
  pendingMealIds,
  globalBadge = false,
}: HomeShellProps) {
  const t = useTranslations('guestHome');
  const isGuest = viewModel.mode !== 'member';

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-[480px] flex-col bg-surface-app sm:min-h-0 sm:my-6 sm:overflow-hidden sm:rounded-[32px] sm:shadow-card">
      <main className="flex-1 px-[18px] pb-6 pt-8">
        <header className="mb-4 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[13px] font-semibold text-ink-400">
                {t('header.greeting')}
              </span>
              {isGuest && !hideTrialBadge ? <TrialModeBadge /> : null}
              {globalBadge ? <Badge tone="neutral">{t('globalBadge')}</Badge> : null}
            </div>
            <h1 className="text-xl font-extrabold tracking-tight text-navy-900">
              {t('header.title')} <span className="text-brand-600">{t('header.accent')}</span>
            </h1>
          </div>
          {/* 브랜드 마크 — 설정 진입은 하단 "마이" 탭으로 이동 (상단 중복 제거) */}
          <span
            aria-hidden
            className="flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-[13px] overflow-hidden"
          >
            <img
              src="/icon.png"
              alt="Jaringobe"
              className="h-full w-full object-cover"
            />
          </span>
        </header>

        {topSlot}

        <div className="flex flex-col gap-3.5">
          <BudgetMoodCard budgetMood={viewModel.budgetMood} sample={isGuest} />
          <MealPlanSection
            weekPlan={viewModel.weekPlan}
            onRecipeClick={onRecipeClick}
            selectedDate={viewModel.selectedDate}
            onSelectDate={onSelectDate}
            onRegenerate={onRegenerateClick}
            onToggleMealComplete={onToggleMealComplete}
            pendingMealIds={pendingMealIds}
          />
          {isGuest ? (
            <>
              <FridgePreviewCard items={viewModel.fridgePreview} />
              <AutoOrderCard autoOrder={viewModel.autoOrder} onStart={onAutoOrderStart} />
            </>
          ) : (
            <>
              {/* 냉장고는 /fridge 수동 관리 페이지로 연결(활성), 자동주문은 "준비 중" (FR-208) */}
              <LockedFeatureCard feature="fridge" href="/fridge" />
              <LockedFeatureCard feature="order" />
            </>
          )}
        </div>
      </main>

      {/* 하단 탭바 — 홈/식단/냉장고/장바구니/마이. 잠긴 탭·마이 클릭 시 회원 분기/게스트 게이트 */}
      <nav
        aria-label={t('nav.label')}
        className="sticky bottom-0 z-40 flex border-t border-surface-line bg-white/95 px-1.5 pb-4 pt-2 backdrop-blur-md"
      >
        <button
          type="button"
          aria-current="page"
          className="flex flex-1 flex-col items-center gap-1"
        >
          <NavIcon tab="home" active />
          <span className="text-[11px] font-bold tracking-tight text-brand-600">
            {t('nav.home')}
          </span>
        </button>
        {LOCKED_TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => onLockedNavClick?.(tab)}
            className="flex flex-1 flex-col items-center gap-1"
          >
            <NavIcon tab={tab} active={false} />
            <span className="text-[11px] font-bold tracking-tight text-ink-300">
              {t(`nav.${tab}`)}
            </span>
          </button>
        ))}
        <button
          type="button"
          aria-label={t('nav.my')}
          onClick={() => onMyTabClick?.()}
          className="flex flex-1 flex-col items-center gap-1"
        >
          <NavIcon tab="my" active={false} />
          <span className="text-[11px] font-bold tracking-tight text-ink-300">
            {t('nav.my')}
          </span>
        </button>
      </nav>
    </div>
  );
}
