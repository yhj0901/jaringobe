import { KNOWN_ERROR_CODES } from '@/shared/config/constants';
import type { ApiErrorDetail } from '@/shared/api/types';

/**
 * fetch 래퍼 — 모든 API 호출은 이 클라이언트를 경유한다 (컴포넌트 내 fetch 직접 호출 금지).
 * 동일 오리진 rewrites 프록시(/api/v1/*) + httpOnly 쿠키 인증 전제 (architecture.md A-1).
 */

export type ApiResult<T> =
  | { ok: true; status: number; data: T }
  | { ok: false; status: number; code: string; i18nKey: string };

/** 네트워크 실패 등 응답 자체가 없는 경우의 코드 */
export const NETWORK_ERROR_CODE = 'NETWORK_ERROR';

/**
 * API 에러 detail.code → i18n 키 매핑 (ui-design 6장 규약).
 * 알려진 코드는 `auth.error.{code}`, 미정의 코드는 `common.error.fallback`.
 */
export function errorCodeToI18nKey(code: string | undefined): string {
  if (code && (KNOWN_ERROR_CODES as readonly string[]).includes(code)) {
    return `auth.error.${code}`;
  }
  return 'common.error.fallback';
}

function parseErrorCode(body: unknown): string | undefined {
  if (typeof body !== 'object' || body === null) return undefined;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail !== 'object' || detail === null) return undefined;
  const code = (detail as Partial<ApiErrorDetail>).code;
  return typeof code === 'string' ? code : undefined;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  let res: Response;
  try {
    res = await fetch(path, {
      credentials: 'same-origin',
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    return {
      ok: false,
      status: 0,
      code: NETWORK_ERROR_CODE,
      i18nKey: errorCodeToI18nKey(undefined),
    };
  }

  if (res.ok) {
    // 204 등 본문 없는 응답 대응
    if (res.status === 204) {
      return { ok: true, status: res.status, data: undefined as T };
    }
    const data = (await res.json()) as T;
    return { ok: true, status: res.status, data };
  }

  let code: string | undefined;
  try {
    code = parseErrorCode(await res.json());
  } catch {
    code = undefined;
  }
  return {
    ok: false,
    status: res.status,
    code: code ?? 'UNKNOWN',
    i18nKey: errorCodeToI18nKey(code),
  };
}
