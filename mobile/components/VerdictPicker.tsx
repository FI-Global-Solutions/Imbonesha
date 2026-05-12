import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import * as Haptics from 'expo-haptics';
import { useTheme, radius, spacing } from '../lib/theme';
import type { InspectionVerdict } from '../lib/api/types';

const VERDICTS: { value: InspectionVerdict; label: string; colorKey: string }[] = [
  { value: 'confirmed', label: 'Confirmed Unauthorized', colorKey: 'critical' },
  { value: 'dismissed', label: 'Dismissed — False Positive', colorKey: 'muted' },
  { value: 'monitoring', label: 'Under Monitoring', colorKey: 'medium' },
  { value: 'inaccessible', label: 'Site Inaccessible', colorKey: 'high' },
  { value: 'data_error', label: 'Data Error — Wrong Location', colorKey: 'muted' },
];

interface Props {
  selected: InspectionVerdict | null;
  onChange: (v: InspectionVerdict) => void;
}

export default function VerdictPicker({ selected, onChange }: Props) {
  const c = useTheme();

  function resolveColor(key: string): string {
    if (key === 'muted') return c.muted;
    return c.severity[key as keyof typeof c.severity] ?? c.muted;
  }

  async function handleSelect(v: InspectionVerdict) {
    onChange(v);
    await Haptics.selectionAsync();
  }

  return (
    <View style={[styles.container, { borderColor: c.border, backgroundColor: c.surface }]}>
      {VERDICTS.map((v, i) => {
        const isSelected = selected === v.value;
        const color = resolveColor(v.colorKey);
        return (
          <TouchableOpacity
            key={v.value}
            style={[
              styles.row,
              { backgroundColor: c.surface },
              i < VERDICTS.length - 1 && [styles.borderBottom, { borderBottomColor: c.border }],
              isSelected && { backgroundColor: color + '0D' },
            ]}
            onPress={() => handleSelect(v.value)}
            activeOpacity={0.75}
          >
            {isSelected && <View style={[styles.leftBar, { backgroundColor: color }]} />}
            <Text style={[styles.radio, { color: isSelected ? color : c.muted }]}>
              {isSelected ? '●' : '○'}
            </Text>
            <Text style={[styles.label, { color: isSelected ? color : c.foreground }, isSelected && styles.labelSelected]}>
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
    borderRadius: radius.md,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    height: 52,
    paddingHorizontal: spacing.md,
  },
  borderBottom: { borderBottomWidth: 1 },
  leftBar: { position: 'absolute', left: 0, top: 0, bottom: 0, width: 4 },
  radio: { fontSize: 15, marginRight: 10 },
  label: { fontSize: 15, flex: 1 },
  labelSelected: { fontWeight: '700' },
});
