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
}

/**
 * 홈 셸 — 게스트/회원 공용, HomeViewModel 주입형 (FR-101, architecture.md A-2).
 * 데이터 소스를 모른다: 게스트 샘플이든 회원 실데이터든 같은 형태로 받는다.
 */
export function HomeShell({ viewModel, onAutoOrderStart, onRecipeClick }: HomeShellProps) {
  const t = useTranslations('guestHome');
  const isGuest = viewModel.mode !== 'member';

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-5 px-4 py-6">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-extrabold text-brand-700">{t('brand')}</h1>
        {isGuest ? <TrialModeBadge /> : null}
      </header>
      <BudgetMoodCard budgetMood={viewModel.budgetMood} />
      <MealPlanSection weekPlan={viewModel.weekPlan} onRecipeClick={onRecipeClick} />
      <FridgePreviewCard items={viewModel.fridgePreview} />
      <AutoOrderCard autoOrder={viewModel.autoOrder} onStart={onAutoOrderStart} />
    </main>
  );
}
