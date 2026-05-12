import axios from 'axios';
import Constants from 'expo-constants';
import { createNavigationContainerRef } from '@react-navigation/native';

function getApiBase(): string {
  if (__DEV__) {
    const host = Constants.expoConfig?.hostUri?.split(':')[0] ?? 'localhost';
    return `http://${host}:8007/api/v1`;
  }
  return 'https://api.imbonesha.gov.rw/api/v1';
}

export const API_BASE = getApiBase();

// Navigation ref so interceptor can navigate to login without being in a component.
export const navigationRef = createNavigationContainerRef();

const client = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
});

client.interceptors.request.use((config) => {
  // Import here to avoid circular dep at module load time
  const { useAuthStore } = require('../auth');
  const token = useAuthStore.getState().accessToken;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

client.interceptors.response.use(
  (res) => res,
  async (error) => {
    if (error.response?.status === 401 && !error.config._retry) {
      error.config._retry = true;
      const { useAuthStore } = require('../auth');
      const { refreshToken, setTokens, clearTokens } = useAuthStore.getState();
      if (refreshToken) {
        try {
          const res = await axios.post(`${API_BASE}/auth/refresh/`, { refresh: refreshToken });
          await setTokens(res.data.access, refreshToken);
          error.config.headers.Authorization = `Bearer ${res.data.access}`;
          return client(error.config);
        } catch {
          await clearTokens();
          if (navigationRef.isReady()) {
            navigationRef.navigate('login' as never);
          }
        }
      } else {
        await clearTokens();
        if (navigationRef.isReady()) {
          navigationRef.navigate('login' as never);
        }
      }
    }
    return Promise.reject(error);
  },
);

export default client;
