import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as Notifications from 'expo-notifications';
import { Stack, useRouter, useSegments } from 'expo-router';
import { useEffect, useRef } from 'react';
import { ActivityIndicator, LogBox, StatusBar, View } from 'react-native';
import { useAuthStore } from '../lib/auth';
import { registerForPushNotifications } from '../lib/notifications';
import { lightColors } from '../lib/theme';
import { useThemeStore } from '../lib/themeStore';

LogBox.ignoreLogs([
  'expo-notifications: Android Push notifications',
  '`expo-notifications` functionality is not fully supported in Expo Go',
]);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 2 },
  },
});

function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const segments = useSegments();
  const { isLoaded, accessToken, loadTokens } = useAuthStore();
  const loadTheme = useThemeStore((s) => s.load);
  const isDark = useThemeStore((s) => s.isDark);
  const registeredRef = useRef(false);

  useEffect(() => {
    loadTokens();
    loadTheme();
  }, []);

  // Register push token once after login
  useEffect(() => {
    if (isLoaded && accessToken && !registeredRef.current) {
      registeredRef.current = true;
      registerForPushNotifications();
    }
    if (!accessToken) {
      registeredRef.current = false;
    }
  }, [isLoaded, accessToken]);

  // Handle notification taps — deep link to inspection screen
  useEffect(() => {
    const subscription = Notifications.addNotificationResponseReceivedListener((response) => {
      try {
        const flagId = response.notification.request.content.data?.flagId;
        if (flagId) {
          router.push({ pathname: '/inspection', params: { flagId: String(flagId) } });
        }
      } catch {
        // Silent failure
      }
    });
    return () => subscription.remove();
  }, [router]);

  useEffect(() => {
    if (!isLoaded) return;
    const inAuth = segments[0] === 'login';
    if (!accessToken && !inAuth) {
      router.replace('/login');
    } else if (accessToken && inAuth) {
      router.replace('/(tabs)/assignments');
    }
  }, [isLoaded, accessToken, segments]);

  if (!isLoaded) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#fff' }}>
        <ActivityIndicator size="large" color={lightColors.primary} />
      </View>
    );
  }

  return (
    <>
      <StatusBar barStyle={isDark ? 'light-content' : 'dark-content'} />
      {children}
    </>
  );
}

export default function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthGate>
        <Stack screenOptions={{ headerShown: false }}>
          <Stack.Screen name="login" />
          <Stack.Screen name="(tabs)" />
          <Stack.Screen
            name="inspection"
            options={{ presentation: 'card', gestureEnabled: true, animation: 'slide_from_right' }}
          />
          <Stack.Screen name="index" redirect />
        </Stack>
      </AuthGate>
    </QueryClientProvider>
  );
}
