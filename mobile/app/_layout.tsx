import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Stack, useRouter, useSegments } from 'expo-router';
import { useEffect } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { useAuthStore } from '../lib/auth';
import { lightColors } from '../lib/theme';
import { useThemeStore } from '../lib/themeStore';

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

  useEffect(() => {
    loadTokens();
    loadTheme();
  }, []);

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

  return <>{children}</>;
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
