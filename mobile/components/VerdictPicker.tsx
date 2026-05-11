import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { colors, radius, spacing } from '../lib/theme';
import type { InspectionVerdict } from '../lib/api/types';

const VERDICTS: { value: InspectionVerdict; label: string; color: string }[] = [
  { value: 'confirmed', label: 'Confirmed Unauthorized', color: colors.severity.critical },
  { value: 'dismissed', label: 'Dismissed — False Positive', color: colors.muted },
  { value: 'monitoring', label: 'Under Monitoring', color: colors.severity.medium },
  { value: 'inaccessible', label: 'Site Inaccessible', color: colors.severity.high },
  { value: 'data_error', label: 'Data Error — Wrong Location', color: colors.muted },
];

interface Props {
  selected: InspectionVerdict | null;
  onChange: (v: InspectionVerdict) => void;
}

export default function VerdictPicker({ selected, onChange }: Props) {
  return (
    <View style={styles.container}>
      {VERDICTS.map((v, i) => {
        const isSelected = selected === v.value;
        return (
          <TouchableOpacity
            key={v.value}
            style={[
              styles.row,
              i < VERDICTS.length - 1 && styles.borderBottom,
              isSelected && { backgroundColor: v.color + '10' },
            ]}
            onPress={() => onChange(v.value)}
            activeOpacity={0.7}
          >
            <View style={[styles.leftBar, { backgroundColor: isSelected ? v.color : 'transparent' }]} />
            <Text style={styles.radio}>{isSelected ? '●' : '○'}</Text>
            <Text style={[styles.label, isSelected && { color: v.color, fontWeight: '700' }]}>
              {v.label}
            </Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: spacing.md,
    backgroundColor: colors.background,
  },
  borderBottom: { borderBottomWidth: 1, borderBottomColor: colors.border },
  leftBar: { width: 3, height: '100%', position: 'absolute', left: 0 },
  radio: { fontSize: 16, marginRight: 10, color: colors.muted },
  label: { fontSize: 15, color: colors.foreground, flex: 1 },
});
