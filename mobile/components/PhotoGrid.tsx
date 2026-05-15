import React from 'react';
import {
  ActionSheetIOS, ActivityIndicator, Alert, Image, Platform,
  StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { useTheme, radius, spacing } from '../lib/theme';
import { getCurrentPosition, gpsStatusColor } from '../lib/location';
import type { UploadPhotoPayload } from '../lib/api/types';

export interface LocalPhoto {
  localId: string;       // temp key before server responds
  uri: string;           // local file URI — always displayable
  serverId: string | null; // UUID returned by server after upload
  uploading: boolean;
  failed: boolean;
}

interface Props {
  photos: LocalPhoto[];
  onUpload: (payload: UploadPhotoPayload, localId: string) => void;
  onDelete: (localId: string) => void;
  onPhotoPress?: (uri: string) => void;
  flagId: number;
}

function DistanceBadge({ distanceM }: { distanceM: number | null }) {
  if (distanceM === null) return null;
  const status = gpsStatusColor(distanceM, null);
  const colorMap: Record<string, string> = { good: '#16a34a', warning: '#f59e0b', poor: '#dc2626' };
  return (
    <View style={[styles.badge, { backgroundColor: colorMap[status] }]}>
      <Text style={styles.badgeText}>{Math.round(distanceM)}m</Text>
    </View>
  );
}

export default function PhotoGrid({ photos, onUpload, onDelete, onPhotoPress, flagId }: Props) {
  const c = useTheme();
  const isUploading = photos.some((p) => p.uploading);

  async function getPosition() {
    try { return await getCurrentPosition(); } catch { return null; }
  }

  async function captureAndUpload(launchFn: () => Promise<ImagePicker.ImagePickerResult>) {
    const pos = await getPosition();
    const result = await launchFn();
    if (result.canceled || !result.assets[0]) return;
    const localId = `local_${Date.now()}_${Math.random()}`;
    onUpload(
      {
        flagId,
        uri: result.assets[0].uri,
        latitude: pos?.coords.latitude ?? 0,
        longitude: pos?.coords.longitude ?? 0,
        accuracy: pos?.coords.accuracy ?? null,
        capturedAt: new Date().toISOString(),
      },
      localId,
    );
  }

  async function launchCamera() {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Camera Permission Required', 'Please allow camera access in Settings to take site photos.');
      return;
    }
    await captureAndUpload(() =>
      ImagePicker.launchCameraAsync({ quality: 0.85, allowsEditing: false, exif: false }),
    );
  }

  async function launchGallery() {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Gallery Permission Required', 'Please allow photo library access in Settings.');
      return;
    }
    await captureAndUpload(() =>
      ImagePicker.launchImageLibraryAsync({ quality: 0.85, allowsEditing: false, exif: false }),
    );
  }

  function handleAddPhoto() {
    if (Platform.OS === 'ios') {
      ActionSheetIOS.showActionSheetWithOptions(
        { options: ['Cancel', 'Take photo with camera', 'Choose from gallery'], cancelButtonIndex: 0 },
        (idx) => {
          if (idx === 1) launchCamera();
          if (idx === 2) launchGallery();
        },
      );
    } else {
      Alert.alert('Add Photo', '', [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Take photo', onPress: launchCamera },
        { text: 'Choose from gallery', onPress: launchGallery },
      ]);
    }
  }

  return (
    <View>
      {photos.length > 0 && (
        <View style={styles.grid}>
          {photos.map((photo) => (
            <View key={photo.localId} style={styles.photoCell}>
              {/* Always show local uri — reliable on device/simulator */}
              <TouchableOpacity
                style={StyleSheet.absoluteFill}
                onPress={() => !photo.uploading && onPhotoPress?.(photo.uri)}
                activeOpacity={0.85}
                disabled={photo.uploading}
              >
                <Image source={{ uri: photo.uri }} style={styles.thumb} resizeMode="cover" />
              </TouchableOpacity>

              {/* Upload spinner overlay */}
              {photo.uploading && (
                <View style={styles.uploadOverlay}>
                  <ActivityIndicator color="#fff" size="small" />
                </View>
              )}

              {/* Failed indicator */}
              {photo.failed && (
                <View style={styles.failedOverlay}>
                  <Text style={styles.failedText}>!</Text>
                </View>
              )}

              {/* Delete button — top-right × */}
              {!photo.uploading && (
                <TouchableOpacity
                  style={styles.deleteBtn}
                  onPress={() => onDelete(photo.localId)}
                  hitSlop={{ top: 6, right: 6, bottom: 6, left: 6 }}
                >
                  <Text style={styles.deleteBtnText}>×</Text>
                </TouchableOpacity>
              )}
            </View>
          ))}
        </View>
      )}

      <TouchableOpacity
        style={[styles.addBtn, { borderColor: c.primary }, isUploading && { opacity: 0.5 }]}
        onPress={handleAddPhoto}
        activeOpacity={0.8}
        disabled={isUploading}
      >
        {isUploading
          ? <ActivityIndicator color={c.primary} />
          : <Text style={[styles.addBtnText, { color: c.primary }]}>+  Add photo</Text>}
      </TouchableOpacity>
    </View>
  );
}

const CELL = 100;

const styles = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginBottom: spacing.sm },
  photoCell: {
    width: CELL, height: CELL,
    borderRadius: radius.md, overflow: 'hidden',
    position: 'relative',
  },
  thumb: { width: '100%', height: '100%' },
  uploadOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.45)',
    justifyContent: 'center', alignItems: 'center',
  },
  failedOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(220,38,38,0.55)',
    justifyContent: 'center', alignItems: 'center',
  },
  failedText: { color: '#fff', fontSize: 22, fontWeight: '900' },
  deleteBtn: {
    position: 'absolute', top: 4, right: 4,
    width: 22, height: 22, borderRadius: 11,
    backgroundColor: 'rgba(0,0,0,0.65)',
    justifyContent: 'center', alignItems: 'center',
  },
  deleteBtnText: { color: '#fff', fontSize: 16, lineHeight: 20, fontWeight: '700' },
  badge: {
    position: 'absolute', bottom: 4, left: 4,
    paddingHorizontal: 5, paddingVertical: 2, borderRadius: 4,
  },
  badgeText: { fontSize: 10, color: '#fff', fontWeight: '700' },
  addBtn: {
    height: 48, borderRadius: radius.md, borderWidth: 1.5,
    justifyContent: 'center', alignItems: 'center', marginTop: spacing.sm,
  },
  addBtnText: { fontSize: 15, fontWeight: '600' },
});
