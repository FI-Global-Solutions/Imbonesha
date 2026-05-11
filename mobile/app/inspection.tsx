import React, { useState } from 'react';
import {
  ActivityIndicator, Alert, SafeAreaView, ScrollView, StyleSheet,
  Switch, Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { useFlag, useSubmitInspection, useUploadPhoto } from '../lib/api/hooks';
import GPSIndicator from '../components/GPSIndicator';
import PermitStatusBlock from '../components/PermitStatusBlock';
import SeverityBadge from '../components/SeverityBadge';
import VerdictPicker from '../components/VerdictPicker';
import PhotoGrid from '../components/PhotoGrid';
import { colors, radius, spacing } from '../lib/theme';
import type { InspectionPhoto, InspectionVerdict } from '../lib/api/types';

const STAGES = ['foundation', 'walls', 'roofing', 'finishing', 'completed', 'none_visible'];

export default function InspectionScreen() {
  const router = useRouter();
  const { flagId } = useLocalSearchParams<{ flagId: string }>();
  const id = Number(flagId);

  const { data: flag, isLoading } = useFlag(id);
  const submitMutation = useSubmitInspection();
  const uploadMutation = useUploadPhoto();

  const [verdict, setVerdict] = useState<InspectionVerdict | null>(null);
  const [notes, setNotes] = useState('');
  const [stage, setStage] = useState('');
  const [floors, setFloors] = useState<number>(1);
  const [occupancy, setOccupancy] = useState(false);
  const [localPhotos, setLocalPhotos] = useState<InspectionPhoto[]>([]);
  const [submitError, setSubmitError] = useState('');

  if (isLoading || !flag) {
    return (
      <SafeAreaView style={styles.center}>
        <ActivityIndicator color={colors.primary} size="large" />
      </SafeAreaView>
    );
  }

  const allPhotos = [...(flag.photos ?? []), ...localPhotos];
  const canSubmit = verdict !== null && allPhotos.length > 0 && !submitMutation.isPending;

  async function handleUpload(payload: Parameters<typeof uploadMutation.mutateAsync>[0]) {
    try {
      const photo = await uploadMutation.mutateAsync(payload);
      setLocalPhotos((prev) => [...prev, photo]);
    } catch (err: any) {
      Alert.alert('Upload Failed', err?.response?.data?.detail ?? 'Could not upload photo. Try again.');
    }
  }

  async function handleSubmit() {
    if (!verdict) return;
    setSubmitError('');

    const photoIds = allPhotos.map((p) => p.id);
    try {
      await submitMutation.mutateAsync({
        flagId: id,
        payload: {
          verdict,
          notes,
          construction_stage: stage,
          estimated_floors: floors,
          occupancy_observed: occupancy,
          visited_at: new Date().toISOString(),
          photo_ids: photoIds,
        },
      });
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      router.replace('/(tabs)/assignments');
    } catch (err: any) {
      const data = err?.response?.data;
      if (data?.error) {
        setSubmitError(data.error + (data.closest_photo_distance_m ? ` (closest: ${Math.round(data.closest_photo_distance_m)}m)` : ''));
      } else {
        setSubmitError('Network error — check your connection and try again.');
      }
    }
  }

  const centroidLat = flag.detection?.centroid_lat ?? null;
  const centroidLng = flag.detection?.centroid_lng ?? null;

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">

        {/* Header */}
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backText}>← Assignments</Text>
        </TouchableOpacity>

        {/* Section 1 — Flag overview */}
        <View style={styles.section}>
          <View style={styles.row}>
            <SeverityBadge severity={flag.severity} />
            <Text style={styles.upi}>{flag.parcel_upi ?? 'Unregistered parcel'}</Text>
          </View>
          {flag.parcel && (
            <>
              <Text style={styles.owner}>{flag.parcel.owner_name}</Text>
              <Text style={styles.location}>
                {[flag.parcel.cell, flag.parcel.sector, flag.parcel.district].filter(Boolean).join(', ')}
              </Text>
            </>
          )}
          <View style={{ marginTop: spacing.sm }}>
            <PermitStatusBlock parcel={flag.parcel} permitStatus={flag.permit_status} />
          </View>
        </View>

        {/* Section 2 — GPS indicator */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Your Location</Text>
          <GPSIndicator siteLat={centroidLat} siteLng={centroidLng} />
        </View>

        {/* Section 3 — Site photos */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Site Photos ({allPhotos.length})</Text>
          <PhotoGrid
            flagId={id}
            photos={allPhotos}
            uploading={uploadMutation.isPending}
            onUpload={handleUpload}
          />
        </View>

        {/* Section 4 — Verdict */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Verdict</Text>
          <VerdictPicker selected={verdict} onChange={setVerdict} />
        </View>

        {/* Section 5 — Details */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Site Details</Text>

          <Text style={styles.fieldLabel}>Construction Stage</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipScroll}>
            {STAGES.map((s) => (
              <TouchableOpacity
                key={s}
                style={[styles.chip, stage === s && styles.chipSelected]}
                onPress={() => setStage(s === stage ? '' : s)}
              >
                <Text style={[styles.chipText, stage === s && styles.chipTextSelected]}>
                  {s.replace('_', ' ')}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <Text style={styles.fieldLabel}>Estimated Floors</Text>
          <View style={styles.stepper}>
            <TouchableOpacity
              style={styles.stepBtn}
              onPress={() => setFloors((f) => Math.max(1, f - 1))}
            >
              <Text style={styles.stepBtnText}>−</Text>
            </TouchableOpacity>
            <Text style={styles.stepValue}>{floors}</Text>
            <TouchableOpacity
              style={styles.stepBtn}
              onPress={() => setFloors((f) => Math.min(20, f + 1))}
            >
              <Text style={styles.stepBtnText}>+</Text>
            </TouchableOpacity>
          </View>

          <View style={styles.switchRow}>
            <Text style={styles.fieldLabel}>Occupancy Observed</Text>
            <Switch
              value={occupancy}
              onValueChange={setOccupancy}
              trackColor={{ true: colors.primary }}
            />
          </View>

          <Text style={styles.fieldLabel}>Notes</Text>
          <TextInput
            style={styles.notesInput}
            placeholder="Describe what you observed at the site..."
            placeholderTextColor={colors.muted}
            value={notes}
            onChangeText={setNotes}
            multiline
            numberOfLines={4}
            textAlignVertical="top"
          />
        </View>

        {/* Section 6 — Submit */}
        {submitError ? <Text style={styles.error}>{submitError}</Text> : null}
        <TouchableOpacity
          style={[styles.submitBtn, !canSubmit && styles.submitBtnDisabled]}
          onPress={handleSubmit}
          disabled={!canSubmit}
          activeOpacity={0.8}
        >
          {submitMutation.isPending
            ? <ActivityIndicator color="#fff" />
            : <Text style={styles.submitBtnText}>Submit Inspection</Text>
          }
        </TouchableOpacity>
        <View style={{ height: spacing.xl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  scroll: { padding: spacing.md },
  backBtn: { marginBottom: spacing.md },
  backText: { color: colors.primary, fontSize: 16, fontWeight: '600' },
  section: {
    marginBottom: spacing.lg,
    paddingBottom: spacing.lg,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.muted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: spacing.sm,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.sm },
  upi: { fontSize: 16, fontWeight: '800', fontFamily: 'monospace', color: colors.foreground, flex: 1 },
  owner: { fontSize: 15, fontWeight: '600', color: colors.foreground, marginBottom: 2 },
  location: { fontSize: 14, color: colors.muted },
  fieldLabel: { fontSize: 13, fontWeight: '600', color: colors.foreground, marginBottom: 6, marginTop: spacing.md },
  chipScroll: { marginBottom: spacing.sm },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: colors.border,
    marginRight: spacing.sm,
    backgroundColor: colors.card,
  },
  chipSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { fontSize: 13, color: colors.muted, textTransform: 'capitalize' },
  chipTextSelected: { color: '#fff', fontWeight: '600' },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  stepBtn: {
    width: 40, height: 40,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: colors.border,
    justifyContent: 'center',
    alignItems: 'center',
  },
  stepBtnText: { fontSize: 20, color: colors.foreground },
  stepValue: { fontSize: 24, fontWeight: '700', color: colors.foreground, minWidth: 32, textAlign: 'center' },
  switchRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  notesInput: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    fontSize: 15,
    color: colors.foreground,
    backgroundColor: colors.card,
    minHeight: 100,
  },
  error: { color: colors.severity.critical, fontSize: 14, marginBottom: spacing.md, textAlign: 'center' },
  submitBtn: {
    height: 52,
    backgroundColor: colors.primary,
    borderRadius: radius.md,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  submitBtnDisabled: { opacity: 0.4 },
  submitBtnText: { color: '#fff', fontSize: 16, fontWeight: '700' },
});
