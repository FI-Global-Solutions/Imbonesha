import React from 'react';
import { StyleSheet, View } from 'react-native';
import { useTheme, radius, spacing } from '../lib/theme';

export default function SkeletonCard() {
  const c = useTheme();
  return (
    <View style={[styles.card, { backgroundColor: c.surface, borderColor: c.border }]}>
      <View style={[styles.bar, { backgroundColor: c.border }]} />
      <View style={styles.body}>
        <View style={styles.topRow}>
          <View style={[styles.badge, { backgroundColor: c.border }]} />
          <View style={[styles.time, { backgroundColor: c.border }]} />
        </View>
        <View style={[styles.upi, { backgroundColor: c.border }]} />
        <View style={[styles.location, { backgroundColor: c.border }]} />
        <View style={[styles.permit, { backgroundColor: c.border }]} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 12,
    overflow: 'hidden',
    height: 96,
  },
  bar: { width: 4 },
  body: { flex: 1, padding: 16, gap: 8 },
  topRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  badge: { height: 18, width: 72, borderRadius: 4 },
  time: { height: 12, width: 60, borderRadius: 4 },
  upi: { height: 17, width: '70%', borderRadius: 4 },
  location: { height: 13, width: '50%', borderRadius: 4 },
  permit: { height: 13, width: '60%', borderRadius: 4 },
});
