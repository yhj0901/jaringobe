import * as Notifications from 'expo-notifications';
import * as Localization from 'expo-localization';
import Constants from 'expo-constants';
import { Platform } from 'react-native';
import { sanitizeInternalPath } from './deeplink';
import type { PermissionStatus, PushTokenPayload } from './bridge';

/**
 * 푸시 클라이언트 (docs/설계/mobile-app.md 5장)
 * 권한 요청·Expo 토큰 발급·포그라운드 프레젠테이션·탭 라우팅.
 * 권한 요청은 웹 주도(soft ask 수락 → REQUEST_PUSH_PERMISSION)로만 트리거된다 (FR-002).
 */

// 포그라운드 수신 — 인앱 배너 기본 프레젠테이션 (mobile-app 5장)
Notifications.setNotificationHandler({
  handleNotification: () =>
    Promise.resolve({
      shouldShowAlert: true,
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: false,
      shouldSetBadge: false,
    }),
});

/** expo 권한 상태 → 브리지 PERMISSION_STATUS 매핑 */
function toBridgeStatus(status: Notifications.PermissionStatus): PermissionStatus {
  if (status === 'granted') return 'granted';
  if (status === 'undetermined') return 'undetermined';
  return 'denied';
}

/** 현재 OS 푸시 권한 상태 조회 */
export async function getPermissionStatus(): Promise<PermissionStatus> {
  const { status } = await Notifications.getPermissionsAsync();
  return toBridgeStatus(status);
}

/** OS 권한 다이얼로그 — REQUEST_PUSH_PERMISSION 처리 (거부 시 재요청 없음, FR-002) */
export async function requestPushPermission(): Promise<PermissionStatus> {
  const current = await Notifications.getPermissionsAsync();
  if (current.status === 'granted') return 'granted';
  if (!current.canAskAgain && current.status !== 'undetermined') return 'denied';
  const { status } = await Notifications.requestPermissionsAsync();
  return toBridgeStatus(status);
}

/**
 * Expo 푸시 토큰 발급 → PUSH_TOKEN payload 구성 (locale/timezone/appVersion 동봉).
 * 발급 실패(시뮬레이터 등) 시 null — 웹 등록 생략.
 */
export async function getPushTokenPayload(appVersion: string): Promise<PushTokenPayload | null> {
  try {
    const projectId: string | undefined =
      Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
    const { data: token } = await Notifications.getExpoPushTokenAsync(
      projectId !== undefined ? { projectId } : undefined,
    );
    return {
      token,
      platform: Platform.OS === 'ios' ? 'ios' : 'android',
      locale: Localization.getLocales()[0]?.languageTag ?? 'en',
      timezone: Localization.getCalendars()[0]?.timeZone ?? 'UTC',
      appVersion,
    };
  } catch {
    return null;
  }
}

/**
 * 푸시 탭(백그라운드/종료 포함) → data.path 화이트리스트 검증 후 콜백 (mobile-app 5장).
 * 해제 함수 반환.
 */
export function addPushResponseListener(onPath: (path: string) => void): () => void {
  const subscription = Notifications.addNotificationResponseReceivedListener((response) => {
    const data = response.notification.request.content.data as Record<string, unknown> | undefined;
    onPath(sanitizeInternalPath(data?.path)); // 실패 시 홈 '/' (CWE-601)
  });
  // 종료 상태에서 푸시 탭으로 콜드 스타트한 경우
  void Notifications.getLastNotificationResponseAsync().then((response) => {
    const data = response?.notification.request.content.data as Record<string, unknown> | undefined;
    if (data?.path !== undefined) onPath(sanitizeInternalPath(data.path));
  });
  return () => subscription.remove();
}
