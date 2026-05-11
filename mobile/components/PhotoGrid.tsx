import React from 'react';
import {
  ActivityIndicator, Alert, Image, StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { colors, radius, spacing } from '../lib/theme';
import { getCurrentPosition, gpsStatusColor } from '../lib/location';
import type { InspectionPhoto, UploadPhotoPayload } from '../lib/api/types';

interface Props {
  flagId: number;
  photos: InspectionPhoto[];
  uploading: boolean;
  onUpload: (payload: UploadPhotoPayload) => void;
}

function DistanceBadge({ distanceM }: { distanceM: number | null }) {
  if (distanceM === null) return null;
  const status = gpsStatusColor(distanceM, null);
  const color = colors.gps[status];
  return (
    <View style={[styles.badge, { backgroundColor: color }]}>
      <Text style={styles.badgeText}>{Math.round(distanceM)}m</Text>
    </View>
  );
}

export default function PhotoGrid({ flagId, photos, uploading, onUpload }: Props) {
  async function capturePhoto() {
    let pos;
    try {
      pos = await getCurrentPosition();
    } catch {
      Alert.alert('GPS Error', 'Could not get your location. Enable GPS and try again.');
      return;
    }

    if (pos.coords.accuracy != null && pos.coords.accuracy > 50) {
      await new Promise<void>((resolve) =>
        Alert.alert(
          'Weak GPS Signal',
          `GPS accuracy is ±${Math.round(pos.coords.accuracy!)}m. Move to an open area for accurate location recording.`,
          [
            { text: 'Cancel', style: 'cancel', onPress: () => resolve() },
            { text: 'Continue Anyway', onPress: () => resolve() },
          ],
        ),
      );
    }

    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Camera Permission Required', 'Please allow camera access in Settings to take site photos.');
      return;
    }

    const result = await ImagePicker.launchCameraAsync({
      quality: 0.85,
      allowsEditing: false,
      exif: false,
    });

    if (!result.canceled && result.assets[0]) {
      onUpload({
        flagId,
        uri: result.assets[0].uri,
        latitude: pos.coords.latitude,
        longitude: pos.coords.longitude,
        accuracy: pos.coords.accuracy,
        capturedAt: new Date().toISOString(),
      });
    }
  }

  return (
    <View>
      <View style={styles.grid}>
        {photos.map((photo) => (
          <View key={photo.id} style={styles.photoCell}>
            {photo.url ? (
              <Image source={{ uri: photo.url }} style={styles.thumb} resizeMode="cover" />
            ) : (
              <View style={[styles.thumb, styles.placeholder]} />
            )}
            <DistanceBadge distanceM={photo.distance_from_site_m} />
          </View>
        ))}
        {uploading && (
          <View style={[styles.photoCell, styles.uploadingCell]}>
            <ActivityIndicator color={colors.primary} />
            <Text style={styles.uploadingText}>Uploading…</Text>
          </View>
        )}
      </View>
      <TouchableOpacity style={styles.takeBtn} onPress={capturePhoto} activeOpacity={0.8}>
        <Text style={styles.takeBtnText}>📷  Take Photo</Text>
      </TouchableOpacity>
    </View>
  );
}

const CELL = 160;

const styles = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginBottom: spacing.md },
  photoCell: { width: CELL, height: CELL, borderRadius: radius.md, overflow: 'hidden', position: 'relative' },
  thumb: { width: '100%', height: '100%' },
  placeholder: { backgroundColor: colors.border },
  badge: {
    position: 'absolute', bottom: 6, right: 6,
    paddingHorizontal: 6, paddingVertical: 2,
    borderRadius: 4,
  },
  badgeText: { fontSize: 11, color: '#fff', fontWeight: '700' },
  uploadingCell: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 6,
  },
  uploadingText: { fontSize: 12, color: colors.muted },
  takeBtn: {
    backgroundColor: colors.primary,
    height: 52,
    borderRadius: radius.md,
    justifyContent: 'center',
    alignItems: 'center',
  },
  takeBtnText: { color: '#fff', fontSize: 16, fontWeight: '600' },
});
