import React, { useState } from 'react';
import {
  ActivityIndicator, FlatList, RefreshControl, SafeAreaView,
  StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useCompletedInspections, useMyAssignments } from '../../lib/api/hooks';
import AssignmentCard from '../../components/AssignmentCard';
import SeverityBadge from '../../components/SeverityBadge';
import { colors, spacing } from '../../lib/theme';
import type { FlagListItem } from '../../lib/api/types';
import { formatDistanceToNow } from 'date-fns';

const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3 };

function sortBySeverity(flags: FlagListItem[]): FlagListItem[] {
  return [...flags].sort((a, b) => {
    const diff = (SEVERITY_ORDER[a.severity] ?? 4) - (SEVERITY_ORDER[b.severity] ?? 4);
    if (diff !== 0) return diff;
    return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
  });
}

export default function AssignmentsScreen() {
  const router = useRouter();
  const { data: active, isLoading: loadingActive, refetch: refetchActive } = useMyAssignments();
  const { data: completed, isLoading: loadingCompleted, refetch: refetchCompleted } = useCompletedInspections();
  const [showCompleted, setShowCompleted] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  async function handleRefresh() {
    setRefreshing(true);
    await Promise.all([refetchActive(), refetchCompleted()]);
    setRefreshing(false);
  }

  const activeFlags = sortBySeverity(active?.results ?? []);
  const completedFlags = completed?.results ?? [];

  function goToFlag(id: number) {
    router.push({ pathname: '/inspection', params: { flagId: String(id) } });
  }

  if (loadingActive) {
    return (
      <SafeAreaView style={styles.center}>
        <ActivityIndicator color={colors.primary} size="large" />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <FlatList
        data={activeFlags}
        keyExtractor={(f) => String(f.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor={colors.primary} />}
        ListHeaderComponent={
          <Text style={styles.sectionLabel}>
            Active Assignments ({activeFlags.length})
          </Text>
        }
        renderItem={({ item }) => (
          <AssignmentCard flag={item} onPress={() => goToFlag(item.id)} />
        )}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyText}>No assignments yet. Pull down to refresh.</Text>
          </View>
        }
        ListFooterComponent={
          <View>
            <TouchableOpacity
              style={styles.completedToggle}
              onPress={() => setShowCompleted((v) => !v)}
            >
              <Text style={styles.completedToggleText}>
                {showCompleted ? '▼' : '▶'} Completed ({completedFlags.length})
              </Text>
            </TouchableOpacity>
            {showCompleted && completedFlags.map((flag) => (
              <TouchableOpacity
                key={flag.id}
                style={styles.completedCard}
                onPress={() => goToFlag(flag.id)}
              >
                <SeverityBadge severity={flag.severity} size="sm" />
                <Text style={styles.completedUpi}>{flag.parcel_upi ?? 'Unregistered'}</Text>
                <Text style={styles.completedVerdict}>{flag.status.replace('_', ' ')}</Text>
                <Text style={styles.completedTime}>
                  Submitted {formatDistanceToNow(new Date(flag.updated_at), { addSuffix: true })}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        }
        contentContainerStyle={styles.list}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  list: { padding: spacing.md },
  sectionLabel: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.muted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: spacing.sm,
  },
  empty: { alignItems: 'center', paddingVertical: spacing.xl },
  emptyText: { color: colors.muted, fontSize: 15 },
  completedToggle: { paddingVertical: spacing.md, borderTopWidth: 1, borderTopColor: colors.border },
  completedToggleText: { fontSize: 14, fontWeight: '600', color: colors.muted },
  completedCard: {
    backgroundColor: colors.card,
    borderRadius: 10,
    padding: spacing.md,
    marginBottom: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
    gap: 4,
  },
  completedUpi: { fontSize: 14, fontWeight: '700', fontFamily: 'monospace', color: colors.foreground },
  completedVerdict: { fontSize: 13, color: colors.muted, textTransform: 'capitalize' },
  completedTime: { fontSize: 12, color: colors.muted },
});
