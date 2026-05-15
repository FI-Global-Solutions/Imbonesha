import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Animated,
  Dimensions,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import * as SecureStore from 'expo-secure-store';
import { useCompletedInspections, useMyAssignments, useProfile, useUnreadCount } from '../../lib/api/hooks';
import { useAuthStore } from '../../lib/auth';
import { registerForPushNotifications, unregisterPushNotifications } from '../../lib/notifications';
import { darkColors, lightColors, radius, spacing } from '../../lib/theme';
import { useThemeStore } from '../../lib/themeStore';

const DRAWER_WIDTH = Dimensions.get('window').width * 0.82;

function useTheme() {
  const isDark = useThemeStore((s) => s.isDark);
  return isDark ? darkColors : lightColors;
}

function InitialsAvatar({ name, size = 80, isDark }: { name: string; size?: number; isDark: boolean }) {
  const parts = name.trim().split(' ');
  const initials = parts.length >= 2
    ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
    : name.slice(0, 2).toUpperCase();
  const c = isDark ? darkColors : lightColors;
  return (
    <View style={{
      width: size, height: size, borderRadius: size / 2,
      backgroundColor: c.primary + '22',
      borderWidth: 2, borderColor: c.primary,
      justifyContent: 'center', alignItems: 'center',
    }}>
      <Text style={{ fontSize: size * 0.34, fontWeight: '800', color: c.primary }}>{initials}</Text>
    </View>
  );
}

function StatCard({ value, label, color }: { value: number; label: string; color: string }) {
  const c = useTheme();
  return (
    <View style={[styles.statCard, { backgroundColor: c.surface, borderColor: c.border }]}>
      <Text style={[styles.statValue, { color }]}>{value}</Text>
      <Text style={[styles.statLabel, { color: c.muted }]}>{label}</Text>
    </View>
  );
}

interface DrawerRowProps {
  icon: string;
  label: string;
  right?: React.ReactNode;
  onPress?: () => void;
  destructive?: boolean;
}
function DrawerRow({ icon, label, right, onPress, destructive }: DrawerRowProps) {
  const c = useTheme();
  return (
    <TouchableOpacity
      style={[styles.drawerRow, { borderBottomColor: c.divider }]}
      onPress={onPress}
      activeOpacity={onPress ? 0.65 : 1}
      disabled={!onPress && !right}
    >
      <Text style={styles.drawerIcon}>{icon}</Text>
      <Text style={[styles.drawerLabel, { color: destructive ? '#dc2626' : c.foreground }]}>{label}</Text>
      {right && <View style={styles.drawerRight}>{right}</View>}
      {onPress && !right && <Text style={[styles.drawerChevron, { color: c.muted }]}>›</Text>}
    </TouchableOpacity>
  );
}

function SectionHeader({ title }: { title: string }) {
  const c = useTheme();
  return <Text style={[styles.sectionHeader, { color: c.muted }]}>{title.toUpperCase()}</Text>;
}

export default function ProfileScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const { clearTokens } = useAuthStore();
  const { data: user, isLoading } = useProfile();
  const { data: active } = useMyAssignments();
  const { data: completed } = useCompletedInspections();
  const { data: unreadData } = useUnreadCount();
  const unreadCount = unreadData?.count ?? 0;
  const { isDark, loaded, load, toggleTheme } = useThemeStore();
  const c = isDark ? darkColors : lightColors;

  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawerAnim = useRef(new Animated.Value(-DRAWER_WIDTH)).current;
  const overlayAnim = useRef(new Animated.Value(0)).current;

  const [pushEnabled, setPushEnabled] = useState(false);
  const [togglingPush, setTogglingPush] = useState(false);

  useEffect(() => { if (!loaded) load(); }, [loaded]);

  // Load persisted push preference
  useEffect(() => {
    SecureStore.getItemAsync('push_enabled').then((val) => {
      setPushEnabled(val === 'true');
    }).catch(() => {});
  }, []);

  async function handlePushToggle(value: boolean) {
    setTogglingPush(true);
    // Optimistically update UI immediately
    setPushEnabled(value);
    try {
      if (value) {
        await SecureStore.setItemAsync('push_enabled', 'true');
        // Best-effort token registration — silently skipped in Expo Go
        await registerForPushNotifications();
      } else {
        await SecureStore.setItemAsync('push_enabled', 'false');
        await unregisterPushNotifications();
      }
      Haptics.selectionAsync();
    } catch {
      // Silent failure — UI stays at the new value
    } finally {
      setTogglingPush(false);
    }
  }

  const openDrawer = useCallback(() => {
    setDrawerOpen(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    Animated.parallel([
      Animated.spring(drawerAnim, { toValue: 0, useNativeDriver: true, damping: 22, stiffness: 180 }),
      Animated.timing(overlayAnim, { toValue: 1, duration: 220, useNativeDriver: true }),
    ]).start();
  }, []);

  const closeDrawer = useCallback(() => {
    Animated.parallel([
      Animated.spring(drawerAnim, { toValue: -DRAWER_WIDTH, useNativeDriver: true, damping: 22, stiffness: 180 }),
      Animated.timing(overlayAnim, { toValue: 0, duration: 180, useNativeDriver: true }),
    ]).start(() => setDrawerOpen(false));
  }, []);

  function handleSignOut() {
    closeDrawer();
    setTimeout(() => {
      Alert.alert('Sign Out', 'Are you sure you want to sign out?', [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Sign Out', style: 'destructive',
          onPress: async () => {
            await clearTokens();
            qc.clear();
            router.replace('/login');
          },
        },
      ]);
    }, 300);
  }

  const fullName = user ? [user.first_name, user.last_name].filter(Boolean).join(' ') || user.email : '';
  const roleLabel = user?.role?.replace(/_/g, ' ') ?? '—';

  if (isLoading || !user) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]}>
        <View style={styles.skeletonWrap}>
          <View style={[styles.skeletonCircle, { backgroundColor: c.border }]} />
          <View style={[styles.skeletonLine, { width: 160, backgroundColor: c.border }]} />
          <View style={[styles.skeletonLine, { width: 200, height: 12, backgroundColor: c.border }]} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]}>
      {/* Header bar */}
      <View style={[styles.header, { borderBottomColor: c.border }]}>
        <Text style={[styles.headerTitle, { color: c.foreground }]}>My Profile</Text>
        <TouchableOpacity onPress={openDrawer} style={styles.menuBtn} activeOpacity={0.7}>
          <View style={[styles.menuLine, { backgroundColor: c.foreground }]} />
          <View style={[styles.menuLine, { backgroundColor: c.foreground, width: 18 }]} />
          <View style={[styles.menuLine, { backgroundColor: c.foreground, width: 14 }]} />
        </TouchableOpacity>
      </View>

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={[styles.scroll, { backgroundColor: c.background }]}
        showsVerticalScrollIndicator={false}
      >
        {/* Hero section */}
        <View style={[styles.hero, { backgroundColor: c.surface, borderColor: c.border }]}>
          <InitialsAvatar name={fullName} size={80} isDark={isDark} />
          <View style={styles.heroText}>
            <Text style={[styles.heroName, { color: c.foreground }]}>{fullName}</Text>
            <Text style={[styles.heroEmail, { color: c.muted }]}>{user.email}</Text>
            <View style={[styles.rolePill, { backgroundColor: c.primary + '18', borderColor: c.primary + '40' }]}>
              <Text style={[styles.roleText, { color: c.primary }]}>{roleLabel}</Text>
            </View>
          </View>
        </View>

        {/* Stats */}
        <View style={styles.statsRow}>
          <StatCard value={active?.count ?? 0} label="Assigned" color={c.severity.high} />
          <StatCard value={completed?.count ?? 0} label="Completed" color={c.primary} />
        </View>

        {/* Info card */}
        <View style={[styles.card, { backgroundColor: c.surface, borderColor: c.border }]}>
          <SectionHeader title="Account" />
          {[
            { label: 'District', value: user.district || '—' },
            { label: 'Role', value: roleLabel },
          ].map((row, i) => (
            <View key={row.label}>
              <View style={styles.infoRow}>
                <Text style={[styles.infoLabel, { color: c.muted }]}>{row.label}</Text>
                <Text style={[styles.infoValue, { color: c.foreground }]}>{row.value}</Text>
              </View>
              {i === 0 && <View style={[styles.divider, { backgroundColor: c.divider }]} />}
            </View>
          ))}
        </View>

        {/* Quick settings inside scroll */}
        <View style={[styles.card, { backgroundColor: c.surface, borderColor: c.border }]}>
          <SectionHeader title="Preferences" />
          <View style={styles.infoRow}>
            <Text style={[styles.infoLabel, { color: c.muted }]}>Dark mode</Text>
            <Switch
              value={isDark}
              onValueChange={() => { toggleTheme(); Haptics.selectionAsync(); }}
              trackColor={{ false: c.border, true: c.primary }}
              thumbColor="#fff"
            />
          </View>
          <View style={[styles.divider, { backgroundColor: c.divider }]} />
          <View style={styles.infoRow}>
            <View style={{ flex: 1 }}>
              <Text style={[styles.infoLabel, { color: c.muted }]}>Push notifications</Text>
              {togglingPush && (
                <ActivityIndicator size="small" color={c.primary} style={{ marginTop: 4, alignSelf: 'flex-start' }} />
              )}
            </View>
            <Switch
              value={pushEnabled}
              onValueChange={handlePushToggle}
              trackColor={{ false: c.border, true: c.primary }}
              thumbColor="#fff"
              disabled={togglingPush}
            />
          </View>
          {unreadCount > 0 && (
            <>
              <View style={[styles.divider, { backgroundColor: c.divider }]} />
              <TouchableOpacity
                style={styles.infoRow}
                onPress={() => router.push('/(tabs)/notifications')}
                activeOpacity={0.7}
              >
                <Text style={[styles.infoLabel, { color: c.primary, fontWeight: '600' }]}>
                  {unreadCount} unread notification{unreadCount !== 1 ? 's' : ''}
                </Text>
                <Text style={[styles.drawerChevron, { color: c.primary }]}>›</Text>
              </TouchableOpacity>
            </>
          )}
        </View>

        {/* Sign out */}
        <TouchableOpacity
          style={[styles.signOutBtn, { borderColor: '#dc2626' }]}
          onPress={handleSignOut}
          activeOpacity={0.8}
        >
          <Text style={styles.signOutText}>Sign out</Text>
        </TouchableOpacity>

        <Text style={[styles.version, { color: c.mutedForeground }]}>Imbonesha Inspector v1.0.0</Text>
      </ScrollView>

      {/* Drawer overlay */}
      {drawerOpen && (
        <Animated.View
          style={[styles.overlay, { opacity: overlayAnim }]}
          pointerEvents="auto"
        >
          <Pressable style={StyleSheet.absoluteFill} onPress={closeDrawer} />
        </Animated.View>
      )}

      {/* Drawer panel */}
      <Animated.View style={[styles.drawer, { backgroundColor: c.drawerBg, transform: [{ translateX: drawerAnim }] }]}>
        {/* Drawer header */}
        <View style={[styles.drawerHead, { backgroundColor: c.primary }]}>
          <InitialsAvatar name={fullName} size={56} isDark={false} />
          <Text style={styles.drawerHeadName} numberOfLines={1}>{fullName}</Text>
          <Text style={styles.drawerHeadEmail} numberOfLines={1}>{user.email}</Text>
        </View>

        <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false}>
          <SectionHeader title="Account" />
          <DrawerRow icon="👤" label={roleLabel} />
          <DrawerRow icon="📍" label={user.district || 'No district'} />

          <SectionHeader title="Activity" />
          <DrawerRow icon="📋" label={`${active?.count ?? 0} active assignments`} />
          <DrawerRow icon="✅" label={`${completed?.count ?? 0} inspections done`} />

          <SectionHeader title="Settings" />
          <DrawerRow
            icon="🌙"
            label="Dark mode"
            right={
              <Switch
                value={isDark}
                onValueChange={() => { toggleTheme(); Haptics.selectionAsync(); }}
                trackColor={{ false: lightColors.border, true: c.primary }}
                thumbColor="#fff"
              />
            }
          />
          <DrawerRow
            icon="🔔"
            label="Push notifications"
            right={
              togglingPush
                ? <ActivityIndicator size="small" color={c.primary} />
                : (
                  <Switch
                    value={pushEnabled}
                    onValueChange={handlePushToggle}
                    trackColor={{ false: lightColors.border, true: c.primary }}
                    thumbColor="#fff"
                    disabled={togglingPush}
                  />
                )
            }
          />

          <SectionHeader title="App" />
          <DrawerRow icon="ℹ️" label="Version 1.0.0" />

          <DrawerRow icon="🚪" label="Sign out" onPress={handleSignOut} destructive />
        </ScrollView>

        <TouchableOpacity style={styles.drawerClose} onPress={closeDrawer}>
          <Text style={[styles.drawerCloseText, { color: c.muted }]}>✕  Close</Text>
        </TouchableOpacity>
      </Animated.View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },

  // Header
  header: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: spacing.md, paddingVertical: 14,
    borderBottomWidth: 1,
  },
  headerTitle: { fontSize: 18, fontWeight: '800' },
  menuBtn: { padding: 8, gap: 4, justifyContent: 'center' },
  menuLine: { height: 2, width: 22, borderRadius: 2, marginVertical: 2 },

  // Scroll
  scroll: { padding: spacing.md, gap: spacing.md, paddingBottom: 48 },

  // Hero
  hero: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.md,
    padding: spacing.md, borderRadius: radius.xl, borderWidth: 1,
  },
  heroText: { flex: 1, gap: 3 },
  heroName: { fontSize: 18, fontWeight: '800' },
  heroEmail: { fontSize: 13 },
  rolePill: {
    alignSelf: 'flex-start', marginTop: 6,
    paddingHorizontal: 10, paddingVertical: 3,
    borderRadius: 20, borderWidth: 1,
  },
  roleText: { fontSize: 12, fontWeight: '700', textTransform: 'capitalize' },

  // Stats
  statsRow: { flexDirection: 'row', gap: spacing.sm },
  statCard: {
    flex: 1, borderRadius: radius.lg, borderWidth: 1,
    paddingVertical: 18, alignItems: 'center',
  },
  statValue: { fontSize: 30, fontWeight: '900' },
  statLabel: { fontSize: 12, fontWeight: '600', marginTop: 2 },

  // Info card
  card: { borderRadius: radius.lg, borderWidth: 1, overflow: 'hidden', paddingHorizontal: spacing.md },
  infoRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 14 },
  infoLabel: { fontSize: 14 },
  infoSubLabel: { fontSize: 11, marginTop: 1 },
  infoValue: { fontSize: 14, fontWeight: '600', textTransform: 'capitalize' },
  divider: { height: 1 },
  sectionHeader: { fontSize: 11, fontWeight: '700', letterSpacing: 0.8, paddingVertical: 10 },

  // Sign out
  signOutBtn: {
    height: 52, borderRadius: radius.md, borderWidth: 2,
    justifyContent: 'center', alignItems: 'center',
  },
  signOutText: { color: '#dc2626', fontSize: 15, fontWeight: '700' },
  version: { textAlign: 'center', fontSize: 12, marginTop: 4 },

  // Skeleton
  skeletonWrap: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 },
  skeletonCircle: { width: 80, height: 80, borderRadius: 40 },
  skeletonLine: { height: 16, borderRadius: 6 },

  // Overlay
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.45)',
    zIndex: 10,
  },

  // Drawer
  drawer: {
    position: 'absolute', top: 0, bottom: 0, left: 0,
    width: DRAWER_WIDTH,
    zIndex: 20,
    shadowColor: '#000',
    shadowOffset: { width: 4, height: 0 },
    shadowOpacity: 0.18,
    shadowRadius: 16,
    elevation: 20,
  },
  drawerHead: {
    padding: spacing.lg, paddingTop: 48, gap: 6,
    alignItems: 'flex-start',
  },
  drawerHeadName: { fontSize: 17, fontWeight: '800', color: '#fff', marginTop: 10 },
  drawerHeadEmail: { fontSize: 13, color: 'rgba(255,255,255,0.75)' },
  drawerRow: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: spacing.md, height: 52,
    borderBottomWidth: 1,
  },
  drawerIcon: { fontSize: 18, width: 32 },
  drawerLabel: { flex: 1, fontSize: 15, fontWeight: '500' },
  drawerRight: { marginLeft: 8 },
  drawerChevron: { fontSize: 20, fontWeight: '300' },
  drawerClose: {
    paddingVertical: 20, alignItems: 'center',
    borderTopWidth: 1, borderTopColor: 'rgba(0,0,0,0.08)',
  },
  drawerCloseText: { fontSize: 14, fontWeight: '600' },
});
