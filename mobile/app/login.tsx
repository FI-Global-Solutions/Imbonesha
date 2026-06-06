import React, { useRef, useState } from 'react';
import {
  ActivityIndicator, KeyboardAvoidingView, Platform,
  ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import { useRouter } from 'expo-router';
import client from '../lib/api/client';
import { useAuthStore } from '../lib/auth';
import { useTheme, radius, spacing } from '../lib/theme';

export default function LoginScreen() {
  const router = useRouter();
  const c = useTheme();
  const { setTokens } = useAuthStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [otpStep, setOtpStep] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const passwordRef = useRef<TextInput>(null);
  const otpRef = useRef<TextInput>(null);

  async function handleLogin() {
    if (!email.trim() || !password) {
      setError('Please enter your email and password.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      await client.post('/auth/login/', { email: email.trim(), password });
      setOtpStep(true);
    } catch (err: any) {
      const detail = err?.response?.data?.detail ?? err?.response?.data?.non_field_errors?.[0];
      setError(detail ?? 'Invalid credentials. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  async function handleVerifyOtp() {
    if (otp.length !== 6) return;
    setLoading(true);
    setError('');
    try {
      const res = await client.post('/auth/verify-otp/', { email: email.trim(), otp });
      await setTokens(res.data.access, res.data.refresh);
      router.replace('/(tabs)/assignments');
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(detail ?? 'Invalid or expired code. Try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={[styles.flex, { backgroundColor: c.background }]}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.wordmarkBlock}>
          <Text style={[styles.title, { color: c.primary }]}>Imbonesha</Text>
          <Text style={[styles.subtitle, { color: c.muted }]}>Field Inspector</Text>
        </View>

        {!otpStep ? (
          <View style={styles.form}>
            <Text style={[styles.label, { color: c.foreground }]}>Email</Text>
            <TextInput
              style={[styles.input, { borderColor: c.border, color: c.foreground, backgroundColor: c.surface }]}
              value={email}
              onChangeText={setEmail}
              placeholder="inspector@imbonesha.gov.rw"
              placeholderTextColor={c.muted}
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
              textContentType="emailAddress"
              autoComplete="email"
              returnKeyType="next"
              onSubmitEditing={() => passwordRef.current?.focus()}
              editable={!loading}
            />

            <Text style={[styles.label, { marginTop: spacing.md, color: c.foreground }]}>Password</Text>
            <TextInput
              ref={passwordRef}
              style={[styles.input, { borderColor: c.border, color: c.foreground, backgroundColor: c.surface }]}
              value={password}
              onChangeText={setPassword}
              placeholder="••••••••••••"
              placeholderTextColor={c.muted}
              secureTextEntry
              textContentType="password"
              autoComplete="password"
              returnKeyType="done"
              onSubmitEditing={handleLogin}
              editable={!loading}
            />

            <TouchableOpacity
              style={[styles.btn, { backgroundColor: c.primary }, loading && styles.btnActive]}
              onPress={handleLogin}
              disabled={loading}
              activeOpacity={0.85}
            >
              {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.btnText}>Continue</Text>}
            </TouchableOpacity>

            {error ? <Text style={[styles.error, { color: c.severity.critical }]}>{error}</Text> : null}
          </View>
        ) : (
          <View style={styles.form}>
            <Text style={[styles.otpHint, { color: c.muted }]}>
              Enter the 6-digit code sent to {email}
            </Text>

            <Text style={[styles.label, { marginTop: spacing.md, color: c.foreground }]}>Login code</Text>
            <TextInput
              ref={otpRef}
              style={[styles.input, styles.otpInput, { borderColor: c.border, color: c.foreground, backgroundColor: c.surface }]}
              value={otp}
              onChangeText={(t) => setOtp(t.replace(/\D/g, '').slice(0, 6))}
              placeholder="000000"
              placeholderTextColor={c.muted}
              keyboardType="number-pad"
              textContentType="oneTimeCode"
              autoComplete="one-time-code"
              returnKeyType="done"
              onSubmitEditing={handleVerifyOtp}
              editable={!loading}
              autoFocus
            />

            <TouchableOpacity
              style={[styles.btn, { backgroundColor: c.primary }, (loading || otp.length !== 6) && styles.btnActive]}
              onPress={handleVerifyOtp}
              disabled={loading || otp.length !== 6}
              activeOpacity={0.85}
            >
              {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.btnText}>Verify &amp; sign in</Text>}
            </TouchableOpacity>

            <TouchableOpacity onPress={() => { setOtpStep(false); setOtp(''); setError(''); }} style={styles.backBtn}>
              <Text style={[styles.backText, { color: c.muted }]}>← Back to sign in</Text>
            </TouchableOpacity>

            {error ? <Text style={[styles.error, { color: c.severity.critical }]}>{error}</Text> : null}
          </View>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  scroll: { flexGrow: 1, justifyContent: 'center', paddingHorizontal: 32, paddingVertical: 60 },
  wordmarkBlock: { marginBottom: 48 },
  title: { fontSize: 36, fontWeight: '800', letterSpacing: -0.5 },
  subtitle: { fontSize: 15, marginTop: 4 },
  form: {},
  label: { fontSize: 14, fontWeight: '600', marginBottom: 8 },
  input: {
    height: 52, borderWidth: 1, borderRadius: radius.md,
    paddingHorizontal: 16, fontSize: 15,
  },
  btn: {
    height: 52, borderRadius: radius.md,
    justifyContent: 'center', alignItems: 'center', marginTop: 24,
  },
  btnActive: { opacity: 0.85 },
  btnText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  error: { marginTop: 16, fontSize: 13, textAlign: 'center' },
  otpHint: { fontSize: 14, textAlign: 'center', marginBottom: 4 },
  otpInput: { textAlign: 'center', fontSize: 28, fontWeight: '700', letterSpacing: 12 },
  backBtn: { marginTop: 16, alignItems: 'center' },
  backText: { fontSize: 13 },
});
