import React, { useState } from 'react';
import {
  FlatList, RefreshControl,
  StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { useCompletedInspections, useMyAssignments, useProfile } from '../../lib/api/hooks';
import AssignmentCard from '../../components/AssignmentCard';
import SeverityBadge from '../../components/SeverityBadge';
import SkeletonCard from '../../components/SkeletonCard';
import { useTheme, radius, spacing } from '../../lib/theme';
import type { FlagListItem } from '../../lib/api/types';
import { formatDistanceToNow } from 'date-fns';

const SEVERITY_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };

function sortBySeverity(flags: FlagListItem[]): FlagListItem[] {
  return [...flags].sort((a, b) => {
    const diff = (SEVERITY_ORDER[a.severity] ?? 4) - (SEVERITY_ORDER[b.severity] ?? 4);
    return diff !== 0 ? diff : new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
  });
}

function greeting(name: string | undefined): string {
  const hour = new Date().getHours();
  const time = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
  return name ? `${time}, ${name.split(' ')[0]}` : time;
}

export default function AssignmentsScreen() {
  const router = useRouter();
  const c = useTheme();
  const { data: user } = useProfile();
  const {
    data: active, isLoading, isError, refetch: refetchActive,
  } = useMyAssignments();
  const { data: completed, refetch: refetchCompleted } = useCompletedInspections();
  const [showCompleted, setShowCompleted] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  useFocusEffect(
    React.useCallback(() => {
      refetchActive();
      refetchCompleted();
    }, []),
  );

  async function handleRefresh() {
    setRefreshing(true);
    await Promise.all([refetchActive(), refetchCompleted()]);
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setRefreshing(false);
  }

  const activeFlags = sortBySeverity(active?.results ?? []);
  const completedFlags = completed?.results ?? [];
  const fullName = user ? [user.first_name, user.last_name].filter(Boolean).join(' ') : undefined;

  if (isLoading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]}>
        <View style={styles.list}>
          <View style={styles.header}>
            <View style={[styles.skeletonGreeting, { backgroundColor: c.border }]} />
            <View style={[styles.skeletonSub, { backgroundColor: c.border }]} />
          </View>
          {[1, 2, 3].map((i) => <SkeletonCard key={i} />)}
        </View>
      </SafeAreaView>
    );
  }

  if (isError) {
    return (
      <SafeAreaView style={[styles.center, { backgroundColor: c.background }]}>
        <Text style={styles.errorIcon}>⚠️</Text>
        <Text style={[styles.errorMsg, { color: c.foreground }]}>Something went wrong.</Text>
        <TouchableOpacity style={[styles.retryBtn, { borderColor: c.primary }]} onPress={() => refetchActive()}>
          <Text style={[styles.retryText, { color: c.primary }]}>Try again</Text>
        </TouchableOpacity>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]}>
      <FlatList
        data={activeFlags}
        keyExtractor={(f) => String(f.id)}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor={c.primary} />
        }
        ListHeaderComponent={
          <View style={styles.header}>
            <View style={styles.headerRow}>
              <Text style={[styles.greeting, { color: c.foreground }]}>{greeting(fullName)}</Text>
              <View style={[styles.onlineDot, { backgroundColor: c.primary }]} />
            </View>
            <Text style={[styles.subheading, { color: c.muted }]}>
              {activeFlags.length === 0
                ? 'No pending assignments'
                : `${activeFlags.length} assignment${activeFlags.length === 1 ? '' : 's'} pending`}
            </Text>
          </View>
        }
        renderItem={({ item }) => (
          <AssignmentCard
            flag={item}
            onPress={() => router.push({ pathname: '/inspection', params: { flagId: String(item.id) } })}
          />
        )}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyIcon}>📋</Text>
            <Text style={[styles.emptyTitle, { color: c.foreground }]}>You're all caught up.</Text>
            <Text style={[styles.emptySubtitle, { color: c.muted }]}>Pull down to refresh.</Text>
          </View>
        }
        ListFooterComponent={
          completedFlags.length > 0 ? (
            <View style={styles.completedSection}>
              <TouchableOpacity
                style={[styles.completedToggle, { borderTopColor: c.border }]}
                onPress={() => setShowCompleted((v) => !v)}
                activeOpacity={0.7}
              >
                <Text style={[styles.completedToggleText, { color: c.muted }]}>
                  {showCompleted ? '▼' : '▶'}  Completed ({completedFlags.length})
                </Text>
              </TouchableOpacity>
              {showCompleted && completedFlags.map((flag) => (
                <TouchableOpacity
                  key={flag.id}
                  style={[styles.completedCard, { backgroundColor: c.surface, borderColor: c.border }]}
                  onPress={() => router.push({ pathname: '/inspection', params: { flagId: String(flag.id) } })}
                  activeOpacity={0.75}
                >
                  <View style={styles.completedRow}>
                    <SeverityBadge severity={flag.severity} size="sm" />
                    <Text style={[styles.completedUpi, { color: c.muted }]}>{flag.parcel_upi ?? 'Unregistered'}</Text>
                    <Text style={[styles.completedVerdict, { color: c.muted }]}>{flag.status.replace('_', ' ')}</Text>
                  </View>
                  <Text style={[styles.completedTime, { color: c.muted }]}>
                    Submitted {formatDistanceToNow(new Date(flag.updated_at), { addSuffix: true })}
                  </Text>
                </TouchableOpacity>
              ))}
              <View style={{ height: spacing.xl }} />
            </View>
          ) : null
        }
        contentContainerStyle={styles.list}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: spacing.xl },
  list: { paddingHorizontal: spacing.md, paddingBottom: spacing.xl },
  header: { paddingVertical: spacing.lg },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  greeting: { fontSize: 22, fontWeight: '800' },
  onlineDot: { width: 8, height: 8, borderRadius: 4 },
  subheading: { fontSize: 14, marginTop: 4 },
  skeletonGreeting: { height: 22, width: 200, borderRadius: 6, marginBottom: 8 },
  skeletonSub: { height: 14, width: 140, borderRadius: 4 },
  empty: { alignItems: 'center', paddingVertical: 48 },
  emptyIcon: { fontSize: 40, marginBottom: 12 },
  emptyTitle: { fontSize: 16, fontWeight: '700' },
  emptySubtitle: { fontSize: 13, marginTop: 4 },
  errorIcon: { fontSize: 32, marginBottom: 12 },
  errorMsg: { fontSize: 16, marginBottom: 16 },
  retryBtn: {
    borderWidth: 1, borderRadius: radius.md,
    paddingHorizontal: 24, paddingVertical: 10,
  },
  retryText: { fontWeight: '600' },
  completedSection: { marginTop: spacing.md },
  completedToggle: { paddingVertical: spacing.md, borderTopWidth: 1 },
  completedToggleText: { fontSize: 14, fontWeight: '600' },
  completedCard: {
    borderRadius: radius.md, padding: spacing.md,
    marginBottom: spacing.sm, borderWidth: 1, gap: 6,
  },
  completedRow: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  completedUpi: { fontSize: 13, fontWeight: '700', fontFamily: 'monospace', flex: 1 },
  completedVerdict: { fontSize: 12, textTransform: 'capitalize' },
  completedTime: { fontSize: 12 },
});
