import React, { useCallback } from 'react';
import { SafeAreaView, StyleSheet } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as SplashScreen from 'expo-splash-screen';
import { AppWebView } from './src/webview';

/**
 * 앱 루트 (docs/설계/mobile-app.md 2장) — 네이티브 스플래시 → 웹뷰 1장.
 * 쉘은 얇게: 제품 UI 는 전부 웹 (앱은 세션·상태를 소유하지 않는다).
 */

// 웹뷰 첫 로드 완료까지 스플래시 유지
void SplashScreen.preventAutoHideAsync();

export default function App() {
  const handleFirstLoadEnd = useCallback(() => {
    void SplashScreen.hideAsync();
  }, []);

  return (
    <SafeAreaView style={styles.root}>
      <StatusBar style="dark" />
      <AppWebView onFirstLoadEnd={handleFirstLoadEnd} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F5F7FB' },
});
