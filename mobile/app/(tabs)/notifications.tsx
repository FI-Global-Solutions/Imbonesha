import React, { useState } from 'react';
import {
  ActivityIndicator, Animated, FlatList, RefreshControl,
  SafeAreaView, StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';
import { formatDistanceToNow, isToday, isYesterday, format } from 'date-fns';
import * as Haptics from 'expo-haptics';
import {
  useMarkAllRead, useMarkNotificationRead, useNotifications,
} from '../../lib/api/hooks';
import { useTheme, radius, spacing } from '../../lib/theme';
import type { MobileNotification } from '../../lib/api/types';

// ─── helpers ────────────────────────────────────────────────────────────────

function smartTime(iso: string): string {
  try {
    const d = new Date(iso);
    if (isToday(d)) return formatDistanceToNow(d, { addSuffix: true });
    if (isYesterday(d)) return `Yesterday ${format(d, 'HH:mm')}`;
    return format(d, 'd MMM, HH:mm');
  } catch {
    return '';
  }
}

function groupByDate(items: MobileNotification[]): { title: string; data: MobileNotification[] }[] {
  const groups: Record<string, MobileNotification[]> = {};
  for (const item of items) {
    const d = new Date(item.created_at);
    let key: string;
    if (isToday(d)) key = 'Today';
    else if (isYesterday(d)) key = 'Yesterday';
    else key = format(d, 'd MMMM yyyy');
    if (!groups[key]) groups[key] = [];
    groups[key].push(item);
  }
  return Object.entries(groups).map(([title, data]) => ({ title, data }));
}

// icon + accent color per notification type
const TYPE_META: Record<string, { icon: string; color: string }> = {
  flag_assigned: { icon: '📋', color: '#16a34a' },
  inspection_complete: { icon: '✅', color: '#2563eb' },
};
function typeMeta(type: string) {
  return TYPE_META[type] ?? { icon: '🔔', color: '#64748b' };
}

// severity badge in the body line
const SEVERITY_LABEL: Record<string, { label: string; color: string }> = {
  critical: { label: 'Critical', color: '#dc2626' },
  high:     { label: 'High',     color: '#ea580c' },
  medium:   { label: 'Medium',   color: '#f59e0b' },
  low:      { label: 'Low',      color: '#16a34a' },
};

function parseSeverity(body: string): { label: string; color: string } | null {
  for (const [key, val] of Object.entries(SEVERITY_LABEL)) {
    if (body.toLowerCase().includes(key)) return val;
  }
  return null;
}

// ─── sub-components ──────────────────────────────────────────────────────────

function SectionHeader({ title, c }: { title: string; c: ReturnType<typeof useTheme> }) {
  return (
    <View style={[sectionHeaderStyles.wrap, { backgroundColor: c.background }]}>
      <Text style={[sectionHeaderStyles.text, { color: c.muted }]}>{title}</Text>
    </View>
  );
}
const sectionHeaderStyles = StyleSheet.create({
  wrap: { paddingHorizontal: spacing.md, paddingTop: 20, paddingBottom: 6 },
  text: { fontSize: 12, fontWeight: '700', letterSpacing: 0.6, textTransform: 'uppercase' },
});

function NotificationCard({
  item,
  onPress,
  isFirst,
  isLast,
}: {
  item: MobileNotification;
  onPress: (item: MobileNotification) => void;
  isFirst: boolean;
  isLast: boolean;
}) {
  const c = useTheme();
  const meta = typeMeta(item.notification_type);
  const severity = parseSeverity(item.body);
  const unread = !item.is_read;

  const scale = React.useRef(new Animated.Value(1)).current;

  function handlePressIn() {
    Animated.spring(scale, { toValue: 0.975, useNativeDriver: true, speed: 50, bounciness: 0 }).start();
  }
  function handlePressOut() {
    Animated.spring(scale, { toValue: 1, useNativeDriver: true, speed: 30, bounciness: 4 }).start();
  }

  return (
    <Animated.View style={[
      { transform: [{ scale }] },
      cardStyles.wrapper,
      isFirst && cardStyles.wrapperFirst,
      isLast && cardStyles.wrapperLast,
      { backgroundColor: unread ? meta.color + '08' : c.background },
    ]}>
      <TouchableOpacity
        activeOpacity={1}
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        onPress={() => onPress(item)}
        style={cardStyles.inner}
      >
        {/* Unread accent bar */}
        {unread && (
          <View style={[cardStyles.accentBar, { backgroundColor: meta.color }]} />
        )}

        {/* Icon bubble */}
        <View style={[cardStyles.iconWrap, { backgroundColor: meta.color + '18' }]}>
          <Text style={cardStyles.icon}>{meta.icon}</Text>
        </View>

        {/* Content */}
        <View style={cardStyles.content}>
          <View style={cardStyles.titleRow}>
            <Text
              style={[
                cardStyles.title,
                { color: c.foreground },
                unread && cardStyles.titleUnread,
              ]}
              numberOfLines={1}
            >
              {item.title}
            </Text>
            <Text style={[cardStyles.time, { color: c.muted }]}>
              {smartTime(item.created_at)}
            </Text>
          </View>

          <Text style={[cardStyles.body, { color: c.muted }]} numberOfLines={2}>
            {item.body}
          </Text>

          {/* Pills row */}
          <View style={cardStyles.pillRow}>
            {severity && (
              <View style={[cardStyles.pill, { backgroundColor: severity.color + '15', borderColor: severity.color + '30' }]}>
                <View style={[cardStyles.pillDot, { backgroundColor: severity.color }]} />
                <Text style={[cardStyles.pillText, { color: severity.color }]}>{severity.label}</Text>
              </View>
            )}
            {unread && (
              <View style={[cardStyles.pill, { backgroundColor: meta.color + '15', borderColor: meta.color + '30' }]}>
                <Text style={[cardStyles.pillText, { color: meta.color }]}>New</Text>
              </View>
            )}
          </View>
        </View>

        {/* Unread dot */}
        {unread && (
          <View style={[cardStyles.unreadDot, { backgroundColor: meta.color }]} />
        )}
      </TouchableOpacity>

      {/* Divider — only between cards, not after last */}
      {!isLast && (
        <View style={[cardStyles.divider, { backgroundColor: c.divider, marginLeft: 72 }]} />
      )}
    </Animated.View>
  );
}

const cardStyles = StyleSheet.create({
  wrapper: {
    marginHorizontal: spacing.md,
    borderRadius: 0,
    overflow: 'hidden',
  },
  wrapperFirst: { borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl },
  wrapperLast: { borderBottomLeftRadius: radius.xl, borderBottomRightRadius: radius.xl },
  inner: { flexDirection: 'row', alignItems: 'flex-start', padding: spacing.md, paddingLeft: 10 },
  accentBar: { position: 'absolute', left: 0, top: 0, bottom: 0, width: 3, borderRadius: 2 },
  iconWrap: {
    width: 44, height: 44, borderRadius: 22,
    justifyContent: 'center', alignItems: 'center',
    marginRight: 12, marginTop: 1, flexShrink: 0,
  },
  icon: { fontSize: 20 },
  content: { flex: 1, gap: 3 },
  titleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  title: { fontSize: 14, fontWeight: '500', flex: 1 },
  titleUnread: { fontWeight: '700' },
  time: { fontSize: 11, flexShrink: 0 },
  body: { fontSize: 13, lineHeight: 18 },
  pillRow: { flexDirection: 'row', gap: 6, marginTop: 4, flexWrap: 'wrap' },
  pill: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: 20, borderWidth: 1,
  },
  pillDot: { width: 6, height: 6, borderRadius: 3 },
  pillText: { fontSize: 11, fontWeight: '700' },
  unreadDot: {
    width: 9, height: 9, borderRadius: 5,
    alignSelf: 'center', marginLeft: 8, flexShrink: 0,
  },
  divider: { height: 1 },
});

// ─── empty state ─────────────────────────────────────────────────────────────

function EmptyState({ c }: { c: ReturnType<typeof useTheme> }) {
  return (
    <View style={emptyStyles.container}>
      <View style={[emptyStyles.iconWrap, { backgroundColor: c.surface, borderColor: c.border }]}>
        <Text style={emptyStyles.icon}>🔔</Text>
      </View>
      <Text style={[emptyStyles.title, { color: c.foreground }]}>All caught up</Text>
      <Text style={[emptyStyles.body, { color: c.muted }]}>
        Flag assignments and updates{'\n'}will appear here
      </Text>
    </View>
  );
}
const emptyStyles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingBottom: 80, gap: 12 },
  iconWrap: {
    width: 80, height: 80, borderRadius: 40,
    justifyContent: 'center', alignItems: 'center',
    borderWidth: 1, marginBottom: 4,
  },
  icon: { fontSize: 36 },
  title: { fontSize: 18, fontWeight: '700' },
  body: { fontSize: 14, textAlign: 'center', lineHeight: 20 },
});

// ─── flat list item types ─────────────────────────────────────────────────────

type ListItem =
  | { type: 'header'; title: string }
  | { type: 'card'; item: MobileNotification; isFirst: boolean; isLast: boolean };

// ─── main screen ─────────────────────────────────────────────────────────────

export default function NotificationsScreen() {
  const c = useTheme();
  const router = useRouter();
  const [refreshing, setRefreshing] = useState(false);

  const { data, isLoading, refetch } = useNotifications();
  const markRead = useMarkNotificationRead();
  const markAll = useMarkAllRead();

  useFocusEffect(
    React.useCallback(() => {
      refetch();
    }, []),
  );

  const notifications = data?.results ?? [];
  const hasUnread = notifications.some((n) => !n.is_read);
  const unreadCount = notifications.filter((n) => !n.is_read).length;

  async function handleRefresh() {
    setRefreshing(true);
    await refetch();
    setRefreshing(false);
  }

  async function handlePress(item: MobileNotification) {
    await Haptics.selectionAsync();
    if (!item.is_read) markRead.mutate(item.id);
    if (item.related_flag_id) {
      router.push({ pathname: '/inspection', params: { flagId: String(item.related_flag_id) } });
    }
  }

  async function handleMarkAll() {
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    markAll.mutate();
  }

  // Build flat list items from grouped data
  const groups = groupByDate(notifications);
  const listItems: ListItem[] = [];
  for (const group of groups) {
    listItems.push({ type: 'header', title: group.title });
    group.data.forEach((item, idx) => {
      listItems.push({
        type: 'card',
        item,
        isFirst: idx === 0,
        isLast: idx === group.data.length - 1,
      });
    });
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]}>
      {/* Header */}
      <View style={[styles.header, { borderBottomColor: c.border }]}>
        <View>
          <Text style={[styles.headerTitle, { color: c.foreground }]}>Notifications</Text>
          {unreadCount > 0 && (
            <Text style={[styles.headerSub, { color: c.muted }]}>
              {unreadCount} unread
            </Text>
          )}
        </View>
        {hasUnread && (
          <TouchableOpacity
            onPress={handleMarkAll}
            disabled={markAll.isPending}
            style={[styles.markAllBtn, { backgroundColor: c.primary + '12', borderColor: c.primary + '30' }]}
            activeOpacity={0.7}
          >
            <Text style={[styles.markAllText, { color: c.primary }]}>
              {markAll.isPending ? 'Clearing…' : '✓  Mark all read'}
            </Text>
          </TouchableOpacity>
        )}
      </View>

      {isLoading && !refreshing ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator color={c.primary} size="large" />
          <Text style={[styles.loadingText, { color: c.muted }]}>Loading notifications…</Text>
        </View>
      ) : (
        <FlatList
          data={listItems}
          keyExtractor={(item, idx) =>
            item.type === 'header' ? `header-${item.title}` : `card-${item.item.id}-${idx}`
          }
          contentContainerStyle={listItems.length === 0 ? styles.flatListEmpty : styles.flatList}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={handleRefresh}
              tintColor={c.primary}
            />
          }
          ListEmptyComponent={<EmptyState c={c} />}
          renderItem={({ item }) => {
            if (item.type === 'header') {
              return <SectionHeader title={item.title} c={c} />;
            }
            return (
              <NotificationCard
                item={item.item}
                onPress={handlePress}
                isFirst={item.isFirst}
                isLast={item.isLast}
              />
            );
          }}
          ListFooterComponent={listItems.length > 0 ? <View style={{ height: spacing.xl }} /> : null}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    paddingTop: spacing.md,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
  },
  headerTitle: { fontSize: 22, fontWeight: '800' },
  headerSub: { fontSize: 12, marginTop: 1 },
  markAllBtn: {
    paddingHorizontal: 14, paddingVertical: 8,
    borderRadius: 20, borderWidth: 1,
  },
  markAllText: { fontSize: 13, fontWeight: '600' },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 12 },
  loadingText: { fontSize: 14 },
  flatList: { paddingBottom: spacing.xl },
  flatListEmpty: { flex: 1 },
});
