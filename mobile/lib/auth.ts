import * as SecureStore from 'expo-secure-store';
import client from './api/client';

const ACCESS_KEY = 'access_token';
const REFRESH_KEY = 'refresh_token';

export async function login(email: string, password: string): Promise<void> {
  const res = await client.post('/auth/login/', { email, password });
  await SecureStore.setItemAsync(ACCESS_KEY, res.data.access);
  await SecureStore.setItemAsync(REFRESH_KEY, res.data.refresh);
}

export async function logout(): Promise<void> {
  await SecureStore.deleteItemAsync(ACCESS_KEY);
  await SecureStore.deleteItemAsync(REFRESH_KEY);
}

export async function getAccessToken(): Promise<string | null> {
  return SecureStore.getItemAsync(ACCESS_KEY);
}

export async function getRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(REFRESH_KEY);
}

export async function isAuthenticated(): Promise<boolean> {
  const token = await getAccessToken();
  if (!token) return false;
  try {
    await client.get('/me/');
    return true;
  } catch {
    return false;
  }
}
