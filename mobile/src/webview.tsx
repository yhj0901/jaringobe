import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  BackHandler,
  Linking,
  Platform,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { WebView } from 'react-native-webview';
import type { WebViewMessageEvent, WebViewNavigation } from 'react-native-webview';
import Constants from 'expo-constants';
import * as Localization from 'expo-localization';
import { isInternalUrl, WEB_URL } from './config';
import {
  BRIDGE_VERSION,
  parseWebMessage,
  serializeAppMessage,
  type AppToWebMessage,
  type BridgePlatform,
} from './bridge';
import { parseDeepLink, pushPathToUrl, resolveDeepLinkUrl } from './deeplink';
import {
  addPushResponseListener,
  getPermissionStatus,
  getPushTokenPayload,
  requestPushPermission,
} from './push';
import { openLoginTab } from './login';

/**
 * 웹뷰 래퍼 (docs/설계/mobile-app.md 4장)
 * - 오리진 allowlist: WEB_URL 만 내부 내비게이션, 그 외 시스템 브라우저 위임
 * - UA 접미사: ` JaringobeApp/{appVersion} ({ios|android})`
 * - Android 뒤로가기 = 웹뷰 히스토리 back, 루트면 표준 최소화
 * - 오프라인/로드 실패: 네이티브 재시도 화면 (웹 도달 불가 시 유일한 네이티브 UI)
 */

interface AppWebViewProps {
  /** 첫 로드 완료 — 스플래시 해제 시점 (App.tsx) */
  onFirstLoadEnd?: () => void;
}

/** 오프라인 화면 문구 — 웹 도달 불가 상태라 네이티브에 최소 리소스로 보관 (ko/en) */
const OFFLINE_STRINGS = {
  ko: { title: '연결할 수 없어요', description: '네트워크 상태를 확인한 뒤 다시 시도해 주세요.', retry: '다시 시도' },
  en: { title: 'Cannot connect', description: 'Please check your network and try again.', retry: 'Retry' },
} as const;

function offlineStrings() {
  const language = Localization.getLocales()[0]?.languageCode ?? 'en';
  return language === 'ko' ? OFFLINE_STRINGS.ko : OFFLINE_STRINGS.en;
}

const PLATFORM: BridgePlatform = Platform.OS === 'ios' ? 'ios' : 'android';

export function AppWebView({ onFirstLoadEnd }: AppWebViewProps) {
  const webViewRef = useRef<WebView>(null);
  const canGoBackRef = useRef(false);
  const firstLoadRef = useRef(true);
  const [sourceUri, setSourceUri] = useState(WEB_URL);
  const [failed, setFailed] = useState(false);

  const appVersion = Constants.expoConfig?.version ?? '1.0.0';

  const sendToWeb = useCallback((message: AppToWebMessage) => {
    webViewRef.current?.postMessage(serializeAppMessage(message));
  }, []);

  const navigateTo = useCallback((url: string) => {
    setFailed(false);
    setSourceUri(url);
  }, []);

  // 딥링크 수신 (jaringobe://auth) — 커스텀 탭 로그인 복귀 / 콜드 스타트 (mobile-app 6장)
  useEffect(() => {
    const handleUrl = (url: string) => {
      const link = parseDeepLink(url);
      if (link !== null) navigateTo(resolveDeepLinkUrl(WEB_URL, link));
    };
    const subscription = Linking.addEventListener('url', (event) => handleUrl(event.url));
    void Linking.getInitialURL().then((url) => {
      if (url !== null) handleUrl(url);
    });
    return () => subscription.remove();
  }, [navigateTo]);

  // 푸시 탭 → data.path 화이트리스트 검증 → 웹뷰 내비게이트 (mobile-app 5장)
  useEffect(
    () => addPushResponseListener((path) => navigateTo(pushPathToUrl(WEB_URL, path))),
    [navigateTo],
  );

  // Android 뒤로가기 = 웹뷰 히스토리 back, 루트면 앱 최소화 표준 동작 (FR-001)
  useEffect(() => {
    if (Platform.OS !== 'android') return undefined;
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => {
      if (canGoBackRef.current) {
        webViewRef.current?.goBack();
        return true;
      }
      return false;
    });
    return () => subscription.remove();
  }, []);

  /** 로드 완료 시 브리지 초기 상태 전달 — BRIDGE_READY → PERMISSION_STATUS → (granted 면) PUSH_TOKEN */
  const announceBridgeState = useCallback(async () => {
    sendToWeb({ v: BRIDGE_VERSION, type: 'BRIDGE_READY', payload: { appVersion, platform: PLATFORM } });
    const status = await getPermissionStatus();
    sendToWeb({ v: BRIDGE_VERSION, type: 'PERMISSION_STATUS', payload: { status } });
    if (status === 'granted') {
      // 이미 granted: 토큰 재전송 → 웹이 upsert (last_seen 갱신, mobile-app 5장)
      const payload = await getPushTokenPayload(appVersion);
      if (payload !== null) sendToWeb({ v: BRIDGE_VERSION, type: 'PUSH_TOKEN', payload });
    }
  }, [appVersion, sendToWeb]);

  /** 웹 → 앱 메시지 라우팅 (mobile-app 3장) — mainFrame 오리진 완전 일치 확인 후 처리 (CWE-345, BUG-003) */
  const handleMessage = useCallback(
    async (event: WebViewMessageEvent) => {
      if (!isInternalUrl(event.nativeEvent.url, WEB_URL)) return;
      const message = parseWebMessage(event.nativeEvent.data);
      if (message === null) return;

      switch (message.type) {
        case 'REQUEST_PUSH_PERMISSION': {
          const status = await requestPushPermission();
          sendToWeb({ v: BRIDGE_VERSION, type: 'PERMISSION_STATUS', payload: { status } });
          if (status === 'granted') {
            const payload = await getPushTokenPayload(appVersion);
            if (payload !== null) sendToWeb({ v: BRIDGE_VERSION, type: 'PUSH_TOKEN', payload });
          }
          break;
        }
        case 'OPEN_OS_SETTINGS':
          void Linking.openSettings();
          break;
        case 'LOGIN_PROVIDER': {
          const link = await openLoginTab(WEB_URL, message.payload.provider, message.payload.next);
          if (link !== null) navigateTo(resolveDeepLinkUrl(WEB_URL, link));
          break;
        }
        case 'SYNC_REQUEST':
          // 웹 구독 완료 후 재동기화 요청 — 상태 재발신 (멱등, BUG-006 / mobile-app 3장)
          await announceBridgeState();
          break;
      }
    },
    [announceBridgeState, appVersion, navigateTo, sendToWeb],
  );

  /** 오리진 allowlist — WEB_URL 오리진 완전 일치 외(마트·약관 등)는 시스템 브라우저 위임 (mobile-app 4장, CWE-345, BUG-003) */
  const handleShouldStartLoad = useCallback(
    (request: WebViewNavigation): boolean => {
      if (isInternalUrl(request.url, WEB_URL)) return true;
      const link = parseDeepLink(request.url);
      if (link !== null) {
        navigateTo(resolveDeepLinkUrl(WEB_URL, link));
        return false;
      }
      if (request.url.startsWith('http://') || request.url.startsWith('https://')) {
        void Linking.openURL(request.url);
      }
      return false; // 그 외 스킴 차단 (CWE-601)
    },
    [navigateTo],
  );

  const handleLoadEnd = useCallback(() => {
    if (firstLoadRef.current) {
      firstLoadRef.current = false;
      onFirstLoadEnd?.();
    }
    void announceBridgeState();
  }, [announceBridgeState, onFirstLoadEnd]);

  if (failed) {
    const strings = offlineStrings();
    return (
      <View style={styles.fallback}>
        <Text style={styles.fallbackTitle}>{strings.title}</Text>
        <Text style={styles.fallbackDescription}>{strings.description}</Text>
        <TouchableOpacity
          accessibilityRole="button"
          style={styles.retryButton}
          onPress={() => navigateTo(sourceUri)}
        >
          <Text style={styles.retryLabel}>{strings.retry}</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <WebView
      ref={webViewRef}
      style={styles.webview}
      source={{ uri: sourceUri }}
      // 기본 UA + ' JaringobeApp/{v} ({os})' 접미사 — 웹 isApp() 감지 (mobile-app 4장)
      applicationNameForUserAgent={`JaringobeApp/${appVersion} (${PLATFORM})`}
      // 네이티브 쿠키 저장소 공유 — httpOnly 쿠키는 JS 미노출 유지 (mobile-app 4장)
      sharedCookiesEnabled
      onMessage={(event) => {
        void handleMessage(event);
      }}
      onShouldStartLoadWithRequest={handleShouldStartLoad}
      onNavigationStateChange={(navigation) => {
        canGoBackRef.current = navigation.canGoBack;
      }}
      onLoadEnd={handleLoadEnd}
      onError={() => setFailed(true)}
    />
  );
}

const styles = StyleSheet.create({
  webview: { flex: 1 },
  fallback: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    paddingHorizontal: 32,
    backgroundColor: '#F5F7FB',
  },
  fallbackTitle: { fontSize: 18, fontWeight: '800', color: '#0B1B3A' },
  fallbackDescription: { fontSize: 14, color: '#5B6B8C', textAlign: 'center' },
  retryButton: {
    marginTop: 12,
    borderRadius: 14,
    backgroundColor: '#2F6BFF',
    paddingHorizontal: 28,
    paddingVertical: 13,
  },
  retryLabel: { fontSize: 14, fontWeight: '800', color: '#FFFFFF' },
});
