import type { ReactElement, ReactNode } from 'react';
import { render, type RenderResult } from '@testing-library/react';
import { NextIntlClientProvider, type AbstractIntlMessages } from 'next-intl';
import koMessages from '@messages/ko.json';
import enMessages from '@messages/en.json';
import type { AppLocale } from '@/i18n/routing';

const MESSAGES: Record<AppLocale, AbstractIntlMessages> = {
  ko: koMessages,
  en: enMessages,
};

export function IntlWrapper({
  locale = 'ko',
  children,
}: {
  locale?: AppLocale;
  children: ReactNode;
}) {
  return (
    <NextIntlClientProvider locale={locale} messages={MESSAGES[locale]} timeZone="UTC">
      {children}
    </NextIntlClientProvider>
  );
}

export function renderWithIntl(ui: ReactElement, locale: AppLocale = 'ko'): RenderResult {
  return render(<IntlWrapper locale={locale}>{ui}</IntlWrapper>);
}
