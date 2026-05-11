import React from 'react';
import {
  ActivityIndicator, Alert, SafeAreaView, StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useQueryClient } from '@tanstack/react-query';
import { logout } from '../../lib/auth';
import { useCompletedInspections, useMyAssignments, useProfile } from '../../lib/api/hooks';
import { colors, radius, spacing } from '../../lib/theme';

export default function ProfileScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const { data: user, isLoading } = useProfile();
  const { data: active } = useMyAssignments();
  const { data: completed } = useCompletedInspections();

  async function handleLogout() {
    Alert.alert('Log Out', 'Are you sure you want to log out?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Log Out',
        style: 'destructive',
        onPress: async () => {
          await logout();
          qc.clear();
          router.replace('/login');
        },
      },
    ]);
  }

  if (isLoading) {
    return (
      <SafeAreaView style={styles.center}>
        <ActivityIndicator color={colors.primary} />
      </SafeAreaView>
    );
  }

  const fullName = [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.email;

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.inner}>
        <Text style={styles.name}>{fullName}</Text>
        <Text style={styles.email}>{user?.email}</Text>
        <Text style={styles.district}>{user?.district || 'No district assigned'}</Text>

        <View style={styles.badge}>
          <Text style={styles.badgeText}>{user?.role?.toUpperCase().replace('_', ' ')}</Text>
        </View>

        <View style={styles.stats}>
          <View style={styles.statItem}>
            <Text style={styles.statValue}>{active?.count ?? 0}</Text>
            <Text style={styles.statLabel}>Pending</Text>
          </View>
          <View style={styles.divider} />
          <View style={styles.statItem}>
            <Text style={styles.statValue}>{completed?.count ?? 0}</Text>
            <Text style={styles.statLabel}>Completed</Text>
          </View>
        </View>

        <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout} activeOpacity={0.8}>
          <Text style={styles.logoutText}>Log Out</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  inner: { flex: 1, padding: spacing.xl, gap: spacing.md },
  name: { fontSize: 22, fontWeight: '800', color: colors.foreground },
  email: { fontSize: 15, color: colors.muted },
  district: { fontSize: 15, color: colors.muted },
  badge: {
    alignSelf: 'flex-start',
    backgroundColor: colors.primary + '20',
    borderColor: colors.primary,
    borderWidth: 1,
    borderRadius: radius.sm,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  badgeText: { fontSize: 12, color: colors.primary, fontWeight: '700', letterSpacing: 0.5 },
  stats: {
    flexDirection: 'row',
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    marginTop: spacing.md,
  },
  statItem: { flex: 1, alignItems: 'center' },
  statValue: { fontSize: 32, fontWeight: '800', color: colors.foreground },
  statLabel: { fontSize: 13, color: colors.muted, marginTop: 4 },
  divider: { width: 1, backgroundColor: colors.border },
  logoutBtn: {
    marginTop: 'auto',
    height: 52,
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: colors.severity.critical,
    justifyContent: 'center',
    alignItems: 'center',
  },
  logoutText: { color: colors.severity.critical, fontSize: 16, fontWeight: '700' },
});
