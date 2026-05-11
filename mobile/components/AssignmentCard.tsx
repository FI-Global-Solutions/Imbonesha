import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { formatDistanceToNow } from 'date-fns';
import { colors, radius, spacing } from '../lib/theme';
import SeverityBadge from './SeverityBadge';
import type { FlagListItem } from '../lib/api/types';

interface Props {
  flag: FlagListItem;
  onPress: () => void;
}

function permitLabel(status: string | null): string {
  if (status === 'active') return 'Active permit';
  if (status === 'expired') return 'Expired permit';
  if (status === 'no_permit') return 'No permit';
  if (status === 'no_parcel') return 'Unregistered parcel';
  return 'Unknown permit status';
}

export default function AssignmentCard({ flag, onPress }: Props) {
  const severityColor = colors.severity[flag.severity] ?? colors.muted;
  const relativeTime = formatDistanceToNow(new Date(flag.created_at), { addSuffix: true });

  return (
    <TouchableOpacity style={styles.card} onPress={onPress} activeOpacity={0.7}>
      <View style={[styles.colorBar, { backgroundColor: severityColor }]} />
      <View style={styles.body}>
        <View style={styles.topRow}>
          <SeverityBadge severity={flag.severity} size="sm" />
          <Text style={styles.time}>{relativeTime}</Text>
        </View>
        <Text style={styles.upi}>{flag.parcel_upi ?? 'Unregistered parcel'}</Text>
        <Text style={styles.location}>
          {[flag.district].filter(Boolean).join(', ')}
        </Text>
        <Text style={styles.permit}>{permitLabel(flag.permit_status)}</Text>
        <View style={styles.footer}>
          <Text style={styles.inspect}>Inspect →</Text>
        </View>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    backgroundColor: colors.background,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.sm,
    overflow: 'hidden',
  },
  colorBar: { width: 4 },
  body: { flex: 1, padding: spacing.md },
  topRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  time: { fontSize: 12, color: colors.muted },
  upi: { fontSize: 15, fontWeight: '700', fontFamily: 'monospace', color: colors.foreground, marginBottom: 2 },
  location: { fontSize: 13, color: colors.muted, marginBottom: 2 },
  permit: { fontSize: 13, color: colors.muted },
  footer: { alignItems: 'flex-end', marginTop: 8 },
  inspect: { fontSize: 14, fontWeight: '600', color: colors.primary },
});
