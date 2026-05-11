import React, { useCallback, useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import * as Location from 'expo-location';
import { colors } from '../lib/theme';
import { distanceMeters, gpsStatusColor } from '../lib/location';

interface Props {
  siteLat: number | null;
  siteLng: number | null;
}

interface GPSState {
  distanceM: number | null;
  accuracyM: number | null;
  acquiring: boolean;
  permissionDenied: boolean;
}

export default function GPSIndicator({ siteLat, siteLng }: Props) {
  const [gps, setGps] = useState<GPSState>({
    distanceM: null,
    accuracyM: null,
    acquiring: true,
    permissionDenied: false,
  });
  const watchRef = useRef<Location.LocationSubscription | null>(null);

  const startWatching = useCallback(async () => {
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== 'granted') {
      setGps((s) => ({ ...s, acquiring: false, permissionDenied: true }));
      return;
    }

    watchRef.current = await Location.watchPositionAsync(
      { accuracy: Location.Accuracy.High, timeInterval: 3000, distanceInterval: 5 },
      (loc) => {
        const { latitude, longitude, accuracy } = loc.coords;
        const dist =
          siteLat != null && siteLng != null
            ? distanceMeters(latitude, longitude, siteLat, siteLng)
            : null;
        setGps({ distanceM: dist, accuracyM: accuracy, acquiring: false, permissionDenied: false });
      },
    );
  }, [siteLat, siteLng]);

  useEffect(() => {
    startWatching();
    return () => {
      watchRef.current?.remove();
    };
  }, [startWatching]);

  if (gps.permissionDenied) {
    return (
      <View style={[styles.container, { borderColor: colors.gps.poor }]}>
        <Text style={[styles.main, { color: colors.gps.poor }]}>📍 Location permission denied</Text>
        <Text style={styles.sub}>Enable location in Settings to use GPS enforcement.</Text>
      </View>
    );
  }

  if (gps.acquiring) {
    return (
      <View style={[styles.container, { borderColor: colors.border }]}>
        <Text style={[styles.main, { color: colors.muted }]}>📍 Getting your location...</Text>
      </View>
    );
  }

  if (gps.accuracyM != null && gps.accuracyM > 50) {
    return (
      <View style={[styles.container, { borderColor: colors.gps.poor }]}>
        <Text style={[styles.main, { color: colors.gps.poor }]}>
          📍 GPS signal weak (±{Math.round(gps.accuracyM)}m accuracy) — move to open area
        </Text>
      </View>
    );
  }

  const status = gpsStatusColor(gps.distanceM, gps.accuracyM);
  const color = colors.gps[status];
  const distText = gps.distanceM != null ? `${Math.round(gps.distanceM)}m` : '—';

  let message = `📍 You are ${distText} from the site`;
  if (status === 'warning') message += ' — move closer';
  if (status === 'poor') message += ' — photos must be taken within 500m';

  return (
    <View style={[styles.container, { borderColor: color }]}>
      <Text style={[styles.main, { color }]}>{message}</Text>
      {gps.accuracyM != null && (
        <Text style={styles.sub}>GPS accuracy: ±{Math.round(gps.accuracyM)}m</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderWidth: 1,
    borderRadius: 10,
    padding: 12,
    backgroundColor: '#f8fafc',
  },
  main: { fontSize: 14, fontWeight: '600' },
  sub: { fontSize: 12, color: colors.muted, marginTop: 4 },
});
