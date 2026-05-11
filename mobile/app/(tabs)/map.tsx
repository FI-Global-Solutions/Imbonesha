import React from 'react';
import { SafeAreaView, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useMyAssignments } from '../../lib/api/hooks';
import SeverityBadge from '../../components/SeverityBadge';
import { colors, radius, spacing } from '../../lib/theme';

export default function MapScreen() {
  const router = useRouter();
  const { data } = useMyAssignments();
  const flags = (data?.results ?? []).filter(
    (f) => f.centroid_lat != null && f.centroid_lng != null,
  );

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.heading}>Site Locations</Text>
        <Text style={styles.sub}>
          Interactive map requires an EAS build. GPS coordinates shown below.
        </Text>
        {flags.length === 0 && (
          <Text style={styles.empty}>No assignments with coordinates.</Text>
        )}
        {flags.map((flag) => (
          <TouchableOpacity
            key={flag.id}
            style={styles.card}
            onPress={() =>
              router.push({ pathname: '/inspection', params: { flagId: String(flag.id) } })
            }
            activeOpacity={0.8}
          >
            <View style={styles.row}>
              <SeverityBadge severity={flag.severity} />
              <Text style={styles.upi}>{flag.parcel_upi ?? 'Unregistered'}</Text>
            </View>
            <Text style={styles.coords}>
              {flag.centroid_lat?.toFixed(5)}, {flag.centroid_lng?.toFixed(5)}
            </Text>
            <Text style={styles.status}>{flag.status.replace('_', ' ')}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  scroll: { padding: spacing.md },
  heading: { fontSize: 20, fontWeight: '800', color: colors.foreground, marginBottom: 4 },
  sub: { fontSize: 13, color: colors.muted, marginBottom: spacing.lg },
  empty: { color: colors.muted, fontSize: 15, textAlign: 'center', marginTop: spacing.xl },
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.sm,
    gap: 4,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: 4 },
  upi: { fontSize: 14, fontWeight: '700', fontFamily: 'monospace', color: colors.foreground, flex: 1 },
  coords: { fontSize: 13, color: colors.muted, fontFamily: 'monospace' },
  status: { fontSize: 13, color: colors.muted, textTransform: 'capitalize' },
});
