import { useTranslations } from 'next-intl';
import { TrialModeBadge } from '@/features/home/TrialModeBadge';
import { BudgetMoodCard } from '@/features/home/BudgetMoodCard';
import { MealPlanSection } from '@/features/home/MealPlanSection';
import { FridgePreviewCard } from '@/features/home/FridgePreviewCard';
import { AutoOrderCard } from '@/features/home/AutoOrderCard';
import type { HomeViewModel } from '@/features/home/types';

interface HomeShellProps {
  viewModel: HomeViewModel;
  onAutoOrderStart?: () => void;
  onRecipeClick?: () => void;
  /** 하단 탭바의 잠긴 탭(식단/냉장고/장바구니) 클릭 — 게스트는 가입 게이트 (FR-109) */
  onLockedNavClick?: () => void;
}

type LockedTab = 'meal' | 'fridge' | 'cart';

/** 하단 탭바 아이콘 — 디자인 마크업의 인라인 SVG 재사용 */
function NavIcon({ tab, active }: { tab: 'home' | LockedTab; active: boolean }) {
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
  }
}

const LOCKED_TABS: LockedTab[] = ['meal', 'fridge', 'cart'];

/**
 * 홈 셸 — 게스트/회원 공용, HomeViewModel 주입형 (FR-101, architecture.md A-2).
 * 데이터 소스를 모른다: 게스트 샘플이든 회원 실데이터든 같은 형태로 받는다.
 * 시각 구성은 Claude Design 프로토타입 home 화면 재현: 인사 헤더 → 예산 락 히어로 →
 * 절약 스트립 → 오늘 식단 카드 → 냉장고 위젯 → 자동주문 카드 → 하단 탭바.
 */
export function HomeShell({
  viewModel,
  onAutoOrderStart,
  onRecipeClick,
  onLockedNavClick,
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
              {isGuest ? <TrialModeBadge /> : null}
            </div>
            <h1 className="text-xl font-extrabold tracking-tight text-navy-900">
              {t('header.title')} <span className="text-brand-600">{t('header.accent')}</span>
            </h1>
          </div>
          <span
            aria-hidden
            className="flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-[13px] bg-navy-800 text-[13px] font-extrabold tracking-tight text-white"
          >
            GB
          </span>
        </header>

        <div className="flex flex-col gap-3.5">
          <BudgetMoodCard budgetMood={viewModel.budgetMood} sample={isGuest} />
          <MealPlanSection weekPlan={viewModel.weekPlan} onRecipeClick={onRecipeClick} />
          <FridgePreviewCard items={viewModel.fridgePreview} />
          <AutoOrderCard autoOrder={viewModel.autoOrder} onStart={onAutoOrderStart} />
        </div>
      </main>

      {/* 하단 탭바 — 디자인의 home/meal/fridge/cart. 게스트는 잠긴 탭 클릭 시 가입 게이트 */}
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
            onClick={onLockedNavClick}
            className="flex flex-1 flex-col items-center gap-1"
          >
            <NavIcon tab={tab} active={false} />
            <span className="text-[11px] font-bold tracking-tight text-ink-300">
              {t(`nav.${tab}`)}
            </span>
          </button>
        ))}
      </nav>
    </div>
  );
}
