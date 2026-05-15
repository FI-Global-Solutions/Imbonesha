import React, { useCallback, useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import * as Location from 'expo-location';
import { useTheme } from '../lib/theme';
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
  const c = useTheme();
  const [gps, setGps] = useState<GPSState>({
    distanceM: null, accuracyM: null, acquiring: true, permissionDenied: false,
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
        const dist = siteLat != null && siteLng != null
          ? distanceMeters(latitude, longitude, siteLat, siteLng)
          : null;
        setGps({ distanceM: dist, accuracyM: accuracy, acquiring: false, permissionDenied: false });
      },
    );
  }, [siteLat, siteLng]);

  useEffect(() => {
    startWatching();
    return () => { watchRef.current?.remove(); };
  }, [startWatching]);

  if (gps.permissionDenied) {
    return (
      <View style={[styles.container, { backgroundColor: c.surface, borderColor: c.border }]}>
        <Text style={[styles.main, { color: c.muted }]}>📍 Location permission denied</Text>
        <Text style={[styles.sub, { color: c.muted }]}>Enable location in Settings for distance info.</Text>
      </View>
    );
  }

  if (gps.acquiring) {
    return (
      <View style={[styles.container, { backgroundColor: c.surface, borderColor: c.border }]}>
        <Text style={[styles.main, { color: c.muted }]}>📍 Getting your location...</Text>
      </View>
    );
  }

  const status = gpsStatusColor(gps.distanceM, gps.accuracyM);
  const color = c.gps[status];
  const bgColor = status === 'good' ? '#f0fdf4' : status === 'warning' ? '#fffbeb' : c.surface;
  const distText = gps.distanceM != null ? `${Math.round(gps.distanceM)}m` : '—';

  return (
    <View style={[styles.container, { backgroundColor: bgColor, borderColor: color + '40' }]}>
      <Text style={[styles.main, { color }]}>📍 You are {distText} from the site</Text>
      {gps.accuracyM != null && (
        <Text style={[styles.sub, { color: c.muted }]}>GPS accuracy: ±{Math.round(gps.accuracyM)}m</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { borderWidth: 1, borderRadius: 10, padding: 12 },
  main: { fontSize: 14, fontWeight: '600' },
  sub: { fontSize: 12, marginTop: 4 },
});
