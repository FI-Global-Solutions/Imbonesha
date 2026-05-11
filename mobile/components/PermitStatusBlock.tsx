import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { colors } from '../lib/theme';
import type { Parcel } from '../lib/api/types';

interface Props {
  parcel: Parcel | null;
  permitStatus: string | null;
}

export default function PermitStatusBlock({ parcel, permitStatus }: Props) {
  const permit = parcel?.active_permit;

  let label = 'Unknown';
  let color = colors.muted;

  if (permitStatus === 'active' && permit) {
    label = `Active: ${permit.permit_no}`;
    color = colors.severity.low;
  } else if (permitStatus === 'expired') {
    label = 'Expired permit';
    color = colors.severity.medium;
  } else if (permitStatus === 'no_permit') {
    label = 'No permit';
    color = colors.severity.critical;
  } else if (permitStatus === 'no_parcel') {
    label = 'Parcel not registered';
    color = colors.muted;
  }

  return (
    <View style={[styles.container, { borderLeftColor: color }]}>
      <Text style={[styles.label, { color }]}>{label}</Text>
      {permit && (
        <Text style={styles.sub}>
          {permit.intended_use} · {permit.max_floors_allowed} floor{permit.max_floors_allowed !== 1 ? 's' : ''} allowed
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderLeftWidth: 3,
    paddingLeft: 10,
    paddingVertical: 4,
  },
  label: { fontSize: 14, fontWeight: '600' },
  sub: { fontSize: 12, color: colors.muted, marginTop: 2 },
});
