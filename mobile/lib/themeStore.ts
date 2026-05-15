import * as SecureStore from 'expo-secure-store';
import { create } from 'zustand';

interface ThemeState {
  isDark: boolean;
  notificationsEnabled: boolean;
  loaded: boolean;
  toggleTheme: () => Promise<void>;
  toggleNotifications: () => Promise<void>;
  load: () => Promise<void>;
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  isDark: false,
  notificationsEnabled: false,
  loaded: false,

  load: async () => {
    try {
      const [dark, notif] = await Promise.all([
        SecureStore.getItemAsync('theme_dark'),
        SecureStore.getItemAsync('notif_enabled'),
      ]);
      set({ isDark: dark === 'true', notificationsEnabled: notif === 'true', loaded: true });
    } catch {
      set({ loaded: true });
    }
  },

  toggleTheme: async () => {
    const next = !get().isDark;
    try { await SecureStore.setItemAsync('theme_dark', String(next)); } catch { /* ignore */ }
    set({ isDark: next });
  },

  toggleNotifications: async () => {
    const next = !get().notificationsEnabled;
    try { await SecureStore.setItemAsync('notif_enabled', String(next)); } catch { /* ignore */ }
    set({ notificationsEnabled: next });
  },
}));
