import React, { useRef, useState } from 'react';
import {
  ActivityIndicator, Image, KeyboardAvoidingView, Modal, Platform,
  ScrollView, SafeAreaView, StyleSheet, Switch, Text, TextInput,
  TouchableOpacity, View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { useFlag, useFlagImagery, useSubmitInspection, useUploadPhoto } from '../lib/api/hooks';
import GPSIndicator from '../components/GPSIndicator';
import PermitStatusBlock from '../components/PermitStatusBlock';
import SeverityBadge from '../components/SeverityBadge';
import VerdictPicker from '../components/VerdictPicker';
import PhotoGrid, { type LocalPhoto } from '../components/PhotoGrid';
import Toast from '../components/Toast';
import { useTheme, radius, spacing } from '../lib/theme';
import { useAuthStore } from '../lib/auth';
import type { UploadPhotoPayload, InspectionVerdict } from '../lib/api/types';

const STAGES = ['foundation', 'walls', 'roofing', 'finishing', 'completed', 'none_visible'];

export default function InspectionScreen() {
  const router = useRouter();
  const c = useTheme();
  const { flagId } = useLocalSearchParams<{ flagId: string }>();
  const id = Number(flagId);

  const { data: flag, isLoading } = useFlag(id);
  const { data: imagery } = useFlagImagery(id);
  const submitMutation = useSubmitInspection();
  const uploadMutation = useUploadPhoto();
  const { accessToken } = useAuthStore();

  const [verdict, setVerdict] = useState<InspectionVerdict | null>(null);
  const [notes, setNotes] = useState('');
  const [stage, setStage] = useState('');
  const [floors, setFloors] = useState<number>(1);
  const [occupancy, setOccupancy] = useState(false);
  const [toastMsg, setToastMsg] = useState('');
  const [fullscreenImg, setFullscreenImg] = useState<string | null>(null);

  // Local photo state — uri is always available for immediate preview.
  // serverId is set once the upload completes; only uploaded photos are sent on submit.
  const [localPhotos, setLocalPhotos] = useState<LocalPhoto[]>([]);
  const scrollRef = useRef<ScrollView>(null);
  const notesRef = useRef<View>(null);

  if (isLoading || !flag) {
    return (
      <SafeAreaView style={[styles.center, { backgroundColor: c.background }]}>
        <ActivityIndicator color={c.primary} size="large" />
      </SafeAreaView>
    );
  }

  const uploadedIds = localPhotos
    .filter((p) => p.serverId !== null && !p.failed)
    .map((p) => p.serverId as string);

  const canSubmit = verdict !== null && uploadedIds.length > 0 && !submitMutation.isPending;

  async function handleUpload(payload: UploadPhotoPayload, localId: string) {
    // Add local preview immediately — uri renders right away.
    setLocalPhotos((prev) => [
      ...prev,
      { localId, uri: payload.uri, serverId: null, uploading: true, failed: false },
    ]);
    try {
      const photo = await uploadMutation.mutateAsync(payload);
      setLocalPhotos((prev) =>
        prev.map((p) => p.localId === localId
          ? { ...p, serverId: photo.id, uploading: false }
          : p,
        ),
      );
    } catch (err: any) {
      setLocalPhotos((prev) =>
        prev.map((p) => p.localId === localId
          ? { ...p, uploading: false, failed: true }
          : p,
        ),
      );
      setToastMsg(err?.response?.data?.detail ?? 'Upload failed. Try again.');
    }
  }

  function handleDelete(localId: string) {
    setLocalPhotos((prev) => prev.filter((p) => p.localId !== localId));
  }

  async function handleSubmit() {
    if (!verdict) return;
    if (uploadedIds.length === 0) {
      setToastMsg('At least one site photo is required.');
      return;
    }
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
          photo_ids: uploadedIds,
        },
      });
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      router.replace('/(tabs)/assignments');
    } catch (err: any) {
      const data = err?.response?.data;
      setToastMsg(data?.error ?? 'Network error — check your connection and try again.');
    }
  }

  function imageryUrl(url: string | null | undefined): string | null {
    if (!url || !accessToken) return null;
    const sep = url.includes('?') ? '&' : '?';
    return `${url}${sep}token=${accessToken}`;
  }

  const centroidLat = flag.detection?.centroid_lat ?? null;
  const centroidLng = flag.detection?.centroid_lng ?? null;

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 24}
      >
      <ScrollView
        ref={scrollRef}
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >

        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Text style={[styles.backText, { color: c.primary }]}>← Assignments</Text>
        </TouchableOpacity>

        {/* Flag overview */}
        <View style={[styles.card, { backgroundColor: c.surface, borderColor: c.border }]}>
          <View style={[styles.severityBar, { backgroundColor: c.severity[flag.severity] ?? c.muted }]} />
          <View style={styles.cardInner}>
            <View style={styles.row}>
              <SeverityBadge severity={flag.severity} />
              <Text style={[styles.statusChip, { color: c.muted, backgroundColor: c.border }]}>
                {flag.status.replace(/_/g, ' ').toUpperCase()}
              </Text>
            </View>
            <Text style={[styles.upi, { color: c.foreground }]}>{flag.parcel_upi ?? 'Unregistered parcel'}</Text>
            {flag.parcel && (
              <Text style={[styles.location, { color: c.muted }]}>
                {[flag.parcel.cell, flag.parcel.sector, flag.parcel.district].filter(Boolean).join(' · ')}
              </Text>
            )}
            <View style={{ marginTop: spacing.sm }}>
              <PermitStatusBlock parcel={flag.parcel} permitStatus={flag.permit_status} />
            </View>
            {flag.detection && (
              <Text style={[styles.detectionMeta, { color: c.muted }]}>
                Confidence: {Math.round((flag.detection.confidence ?? 0) * 100)}%
                {flag.detection.area_sqm ? `  ·  ${Math.round(flag.detection.area_sqm)} m²` : ''}
              </Text>
            )}
          </View>
        </View>

        {/* GPS */}
        <View style={[styles.section, { borderBottomColor: c.border }]}>
          <Text style={[styles.sectionTitle, { color: c.muted }]}>Your Location</Text>
          <GPSIndicator siteLat={centroidLat} siteLng={centroidLng} />
        </View>

        {/* Imagery */}
        {(imagery?.t1_url || imagery?.t2_url) && (
          <View style={[styles.section, { borderBottomColor: c.border }]}>
            <Text style={[styles.sectionTitle, { color: c.muted }]}>Satellite Imagery</Text>
            <View style={styles.imageryRow}>
              {[
                { url: imageryUrl(imagery?.t1_url), label: 'BEFORE', date: imagery?.t1_captured_at },
                { url: imageryUrl(imagery?.t2_url), label: 'AFTER', date: imagery?.t2_captured_at },
              ].map(({ url, label, date }) => (
                <TouchableOpacity
                  key={label}
                  style={styles.imageryCell}
                  onPress={() => url && setFullscreenImg(url)}
                  activeOpacity={0.85}
                  disabled={!url}
                >
                  {url ? (
                    <Image source={{ uri: url }} style={[styles.imageryThumb, { backgroundColor: c.border }]} resizeMode="cover" />
                  ) : (
                    <View style={[styles.imageryThumb, { backgroundColor: c.border, justifyContent: 'center', alignItems: 'center' }]}>
                      <Text style={[styles.imageryUnavailable, { color: c.muted }]}>Unavailable</Text>
                    </View>
                  )}
                  <Text style={[styles.imageryLabel, { color: c.muted }]}>{label}</Text>
                  {date && (
                    <Text style={[styles.imageryDate, { color: c.muted }]}>
                      {new Date(date).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })}
                    </Text>
                  )}
                </TouchableOpacity>
              ))}
            </View>
          </View>
        )}

        {/* Photos */}
        <View style={[styles.section, { borderBottomColor: c.border }]}>
          <Text style={[styles.sectionTitle, { color: c.muted }]}>
            Site Photos{localPhotos.length > 0 ? ` (${uploadedIds.length}/${localPhotos.length})` : ''}
          </Text>
          <PhotoGrid
            flagId={id}
            photos={localPhotos}
            onUpload={handleUpload}
            onDelete={handleDelete}
            onPhotoPress={(uri) => setFullscreenImg(uri)}
          />
        </View>

        {/* Verdict */}
        <View style={[styles.section, { borderBottomColor: c.border }]}>
          <Text style={[styles.sectionTitle, { color: c.muted }]}>Verdict</Text>
          <VerdictPicker selected={verdict} onChange={setVerdict} />
        </View>

        {/* Details */}
        <View style={[styles.section, { borderBottomColor: c.border }]}>
          <Text style={[styles.sectionTitle, { color: c.muted }]}>Site Details</Text>

          <Text style={[styles.fieldLabel, { color: c.foreground }]}>Construction Stage</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipScroll}>
            {STAGES.map((s) => (
              <TouchableOpacity
                key={s}
                style={[
                  styles.chip,
                  { borderColor: c.border, backgroundColor: c.surface },
                  stage === s && { backgroundColor: c.primary, borderColor: c.primary },
                ]}
                onPress={() => setStage(s === stage ? '' : s)}
                activeOpacity={0.8}
              >
                <Text style={[
                  styles.chipText, { color: c.muted },
                  stage === s && { color: '#fff', fontWeight: '600' },
                ]}>
                  {s.replace(/_/g, ' ')}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <Text style={[styles.fieldLabel, { color: c.foreground }]}>Estimated Floors</Text>
          <View style={styles.stepper}>
            <TouchableOpacity style={[styles.stepBtn, { borderColor: c.border }]} onPress={() => setFloors((f) => Math.max(1, f - 1))}>
              <Text style={[styles.stepBtnText, { color: c.foreground }]}>−</Text>
            </TouchableOpacity>
            <Text style={[styles.stepValue, { color: c.foreground }]}>{floors}</Text>
            <TouchableOpacity style={[styles.stepBtn, { borderColor: c.border }]} onPress={() => setFloors((f) => Math.min(30, f + 1))}>
              <Text style={[styles.stepBtnText, { color: c.foreground }]}>+</Text>
            </TouchableOpacity>
          </View>

          <View style={styles.switchRow}>
            <Text style={[styles.fieldLabel, { color: c.foreground }]}>Occupancy Observed</Text>
            <Switch value={occupancy} onValueChange={setOccupancy} trackColor={{ true: c.primary }} />
          </View>

          <View ref={notesRef}>
            <Text style={[styles.fieldLabel, { color: c.foreground }]}>Notes</Text>
            <TextInput
              style={[styles.notesInput, { borderColor: c.border, color: c.foreground, backgroundColor: c.surface }]}
              placeholder="Describe what you observed at the site..."
              placeholderTextColor={c.muted}
              value={notes}
              onChangeText={setNotes}
              multiline
              numberOfLines={5}
              textAlignVertical="top"
              onFocus={() => {
                notesRef.current?.measureInWindow((_x, y) => {
                  scrollRef.current?.scrollTo({ y: y - 120, animated: true });
                });
              }}
            />
          </View>
        </View>

        {/* Submit */}
        <TouchableOpacity
          style={[styles.submitBtn, { backgroundColor: c.primary }, !canSubmit && styles.submitBtnDisabled]}
          onPress={handleSubmit}
          disabled={!canSubmit}
          activeOpacity={0.85}
        >
          {submitMutation.isPending
            ? <ActivityIndicator color="#fff" />
            : <Text style={styles.submitBtnText}>Submit Inspection</Text>}
        </TouchableOpacity>
        <View style={{ height: spacing.xl * 2 }} />
      </ScrollView>
      </KeyboardAvoidingView>

      <Toast message={toastMsg} onDismiss={() => setToastMsg('')} />

      <Modal visible={!!fullscreenImg} animationType="fade" transparent>
        <View style={styles.modalOverlay}>
          <Image source={{ uri: fullscreenImg! }} style={styles.modalImage} resizeMode="contain" />
          <TouchableOpacity style={styles.modalClose} onPress={() => setFullscreenImg(null)}>
            <Text style={styles.modalCloseText}>✕</Text>
          </TouchableOpacity>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  scroll: { padding: spacing.md },
  backBtn: { marginBottom: spacing.md },
  backText: { fontSize: 16, fontWeight: '600' },

  card: {
    flexDirection: 'row',
    borderRadius: radius.md, borderWidth: 1,
    marginBottom: spacing.lg, overflow: 'hidden',
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06, shadowRadius: 4, elevation: 2,
  },
  severityBar: { width: 4 },
  cardInner: { flex: 1, padding: spacing.md, gap: 4 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 },
  statusChip: {
    fontSize: 11, fontWeight: '700',
    borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2,
  },
  upi: { fontSize: 17, fontWeight: '800', fontFamily: 'monospace' },
  location: { fontSize: 13 },
  detectionMeta: { fontSize: 12, marginTop: 4 },

  section: {
    marginBottom: spacing.lg, paddingBottom: spacing.lg,
    borderBottomWidth: 1,
  },
  sectionTitle: {
    fontSize: 12, fontWeight: '700',
    textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: spacing.sm,
  },

  imageryRow: { flexDirection: 'row', gap: spacing.sm },
  imageryCell: { flex: 1 },
  imageryThumb: { width: '100%', aspectRatio: 1, borderRadius: radius.md },
  imageryUnavailable: { fontSize: 12 },
  imageryLabel: { fontSize: 11, fontWeight: '700', marginTop: 4, textTransform: 'uppercase', letterSpacing: 0.5 },
  imageryDate: { fontSize: 11 },

  fieldLabel: { fontSize: 13, fontWeight: '600', marginBottom: 6, marginTop: spacing.md },
  chipScroll: { marginBottom: spacing.sm },
  chip: {
    paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20,
    borderWidth: 1, marginRight: spacing.sm,
  },
  chipText: { fontSize: 13, textTransform: 'capitalize' },

  stepper: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  stepBtn: {
    width: 40, height: 40, borderRadius: 20,
    borderWidth: 1, justifyContent: 'center', alignItems: 'center',
  },
  stepBtnText: { fontSize: 20 },
  stepValue: { fontSize: 24, fontWeight: '700', minWidth: 32, textAlign: 'center' },
  switchRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  notesInput: {
    borderWidth: 1, borderRadius: radius.md,
    padding: spacing.md, fontSize: 15, minHeight: 120,
  },

  submitBtn: {
    height: 52, borderRadius: radius.md,
    justifyContent: 'center', alignItems: 'center', marginBottom: spacing.md,
  },
  submitBtnDisabled: { opacity: 0.35 },
  submitBtnText: { color: '#fff', fontSize: 16, fontWeight: '700' },

  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.92)', justifyContent: 'center', alignItems: 'center' },
  modalImage: { width: '100%', height: '80%' },
  modalClose: {
    position: 'absolute', top: 56, right: 20,
    width: 36, height: 36, borderRadius: 18,
    backgroundColor: 'rgba(255,255,255,0.2)',
    justifyContent: 'center', alignItems: 'center',
  },
  modalCloseText: { color: '#fff', fontSize: 16, fontWeight: '700' },
});
