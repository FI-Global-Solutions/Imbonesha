import axios from 'axios';
import * as SecureStore from 'expo-secure-store';
import Constants from 'expo-constants';

// On simulator/device via Expo Go, hostUri is the dev machine IP:port.
// Split off the port to get just the IP, then use port 8007 (API port).
const devHost = Constants.expoConfig?.hostUri?.split(':')[0] ?? 'localhost';
const API_URL = __DEV__
  ? `http://${devHost}:8007`
  : 'https://api.imbonesha.gov.rw';

const client = axios.create({
  baseURL: `${API_URL}/api/v1`,
  timeout: 30000,
});

client.interceptors.request.use(async (config) => {
  const token = await SecureStore.getItemAsync('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

client.interceptors.response.use(
  (res) => res,
  async (error) => {
    if (error.response?.status === 401) {
      const refresh = await SecureStore.getItemAsync('refresh_token');
      if (refresh) {
        try {
          const res = await axios.post(`${API_URL}/api/v1/auth/refresh/`, { refresh });
          await SecureStore.setItemAsync('access_token', res.data.access);
          error.config.headers.Authorization = `Bearer ${res.data.access}`;
          return client(error.config);
        } catch {
          await SecureStore.deleteItemAsync('access_token');
          await SecureStore.deleteItemAsync('refresh_token');
        }
      }
    }
    return Promise.reject(error);
  },
);

export default client;
