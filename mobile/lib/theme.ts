export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
};

export const radius = {
  sm: 6,
  md: 10,
  lg: 12,
  xl: 20,
};

const shared = {
  severity: {
    low: '#16a34a',
    medium: '#f59e0b',
    high: '#ea580c',
    critical: '#dc2626',
  },
  status: {
    pending: '#64748b',
    assigned: '#2563eb',
    in_review: '#7c3aed',
    confirmed: '#16a34a',
    dismissed: '#94a3b8',
    monitoring: '#f59e0b',
    inaccessible: '#64748b',
    data_error: '#64748b',
    closed: '#16a34a',
  },
  gps: {
    good: '#16a34a',
    warning: '#f59e0b',
    poor: '#dc2626',
  },
};

export const lightColors = {
  primary: '#16a34a',
  primaryDark: '#14532d',
  background: '#ffffff',
  surface: '#f8fafc',
  card: '#f8fafc',
  border: '#e2e8f0',
  foreground: '#1e293b',
  muted: '#64748b',
  mutedForeground: '#94a3b8',
  drawerBg: '#f8fafc',
  drawerHeader: '#1e293b',
  divider: '#f1f5f9',
  ...shared,
};

export const darkColors = {
  primary: '#22c55e',
  primaryDark: '#16a34a',
  background: '#0f172a',
  surface: '#1e293b',
  card: '#1e293b',
  border: '#334155',
  foreground: '#f1f5f9',
  muted: '#94a3b8',
  mutedForeground: '#64748b',
  drawerBg: '#1e293b',
  drawerHeader: '#0f172a',
  divider: '#1e293b',
  ...shared,
};

// Default export — lightColors as static fallback.
export const colors = lightColors;

// useTheme() — call inside any component to get reactive theme-aware tokens.
// Lazy import avoids circular dependency between theme.ts and themeStore.ts.
export function useTheme() {
  const { useThemeStore } = require('./themeStore') as typeof import('./themeStore');
  const isDark = useThemeStore((s: { isDark: boolean }) => s.isDark);
  return isDark ? darkColors : lightColors;
}
