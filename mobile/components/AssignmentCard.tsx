import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { formatDistanceToNow } from 'date-fns';
import { useTheme, radius } from '../lib/theme';
import SeverityBadge from './SeverityBadge';
import type { FlagListItem } from '../lib/api/types';

interface Props {
  flag: FlagListItem;
  onPress: () => void;
}

function permitIcon(status: string | null, primaryColor: string, mutedColor: string, critColor: string, warnColor: string) {
  if (status === 'active') return { icon: '✓', label: 'Active permit', color: primaryColor };
  if (status === 'expired') return { icon: '⚠', label: 'Expired permit', color: warnColor };
  if (status === 'no_permit') return { icon: '✗', label: 'No construction permit', color: critColor };
  if (status === 'no_parcel') return { icon: '?', label: 'Unregistered parcel', color: mutedColor };
  return { icon: '—', label: 'Unknown', color: mutedColor };
}

export default function AssignmentCard({ flag, onPress }: Props) {
  const c = useTheme();
  const severityColor = c.severity[flag.severity] ?? c.muted;
  const relativeTime = formatDistanceToNow(
    new Date(flag.assigned_at ?? flag.created_at), { addSuffix: true }
  );
  const permit = permitIcon(flag.permit_status, c.primary, c.muted, c.severity.critical, c.severity.medium);

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.card,
        { backgroundColor: c.surface, borderColor: c.border },
        pressed && styles.cardPressed,
      ]}
    >
      <View style={[styles.colorBar, { backgroundColor: severityColor }]} />
      <View style={styles.body}>
        <View style={styles.topRow}>
          <SeverityBadge severity={flag.severity} size="sm" />
          <Text style={[styles.time, { color: c.muted }]}>{relativeTime}</Text>
        </View>
        <Text style={[styles.upi, { color: c.foreground }]} numberOfLines={1}>{flag.parcel_upi ?? 'Unregistered parcel'}</Text>
        <Text style={[styles.location, { color: c.muted }]} numberOfLines={1}>{flag.district || '—'}</Text>
        <View style={styles.permitRow}>
          <Text style={[styles.permitIcon, { color: permit.color }]}>{permit.icon}</Text>
          <Text style={[styles.permitLabel, { color: permit.color }]}>{permit.label}</Text>
        </View>
      </View>
      <Text style={[styles.arrow, { color: c.border }]}>→</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 12,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 2,
  },
  cardPressed: { transform: [{ scale: 0.98 }], opacity: 0.95 },
  colorBar: { width: 4, alignSelf: 'stretch' },
  body: { flex: 1, padding: 16, gap: 3 },
  topRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  time: { fontSize: 12 },
  upi: { fontSize: 17, fontWeight: '800', fontFamily: 'monospace' },
  location: { fontSize: 13 },
  permitRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 2 },
  permitIcon: { fontSize: 12, fontWeight: '700' },
  permitLabel: { fontSize: 13, fontWeight: '500' },
  arrow: { fontSize: 18, paddingRight: 16 },
});
