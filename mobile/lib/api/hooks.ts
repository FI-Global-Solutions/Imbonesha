import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import client from './client';
import type {
  FlagDetail, FlagImagery, FlagListItem, InspectionPhoto, MobileNotification,
  NotificationListResponse, PaginatedResponse, SubmitInspectionPayload,
  UnreadCountResponse, UploadPhotoPayload, User,
} from './types';
import * as ImageManipulator from 'expo-image-manipulator';

const STALE = 30_000;

export function useProfile() {
  return useQuery<User>({
    queryKey: ['me'],
    queryFn: async () => (await client.get('/me/')).data,
    staleTime: STALE,
    retry: 2,
  });
}

export function useMyAssignments() {
  return useQuery<PaginatedResponse<FlagListItem>>({
    queryKey: ['flags', 'assigned'],
    queryFn: async () => (await client.get('/flags/', { params: { status: 'assigned', page_size: 100 } })).data,
    staleTime: STALE,
    retry: 2,
  });
}

export function useCompletedInspections() {
  return useQuery<PaginatedResponse<FlagListItem>>({
    queryKey: ['flags', 'completed'],
    queryFn: async () =>
      (await client.get('/flags/', {
        params: { status__in: 'confirmed,dismissed,monitoring,inaccessible,data_error', page_size: 100 },
      })).data,
    staleTime: STALE,
    retry: 2,
  });
}

export function useFlag(id: number) {
  return useQuery<FlagDetail>({
    queryKey: ['flag', id],
    queryFn: async () => (await client.get(`/flags/${id}/`)).data,
    staleTime: STALE,
    retry: 2,
    enabled: !!id,
  });
}

export function useFlagImagery(id: number) {
  return useQuery<FlagImagery>({
    queryKey: ['flag', id, 'imagery'],
    queryFn: async () => (await client.get(`/flags/${id}/imagery/`)).data,
    staleTime: 60 * 60 * 1000, // imagery doesn't change
    retry: 1,
    enabled: !!id,
  });
}

export function useFlagPhotos(id: number) {
  return useQuery<InspectionPhoto[]>({
    queryKey: ['flag', id, 'photos'],
    queryFn: async () => (await client.get(`/flags/${id}/photos/`)).data,
    staleTime: STALE,
    retry: 2,
    enabled: !!id,
  });
}

export function useSubmitInspection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ flagId, payload }: { flagId: number; payload: SubmitInspectionPayload }) => {
      const res = await client.post(`/flags/${flagId}/inspect/`, payload);
      return res.data;
    },
    onSuccess: (_data, { flagId }) => {
      qc.invalidateQueries({ queryKey: ['flags'] });
      qc.invalidateQueries({ queryKey: ['flag', flagId] });
    },
  });
}

export function useNotifications(unreadOnly = false) {
  return useQuery<NotificationListResponse>({
    queryKey: ['notifications', { unreadOnly }],
    queryFn: async () =>
      (await client.get('/notifications/', { params: unreadOnly ? { unread_only: 'true' } : {} })).data,
    staleTime: STALE,
    retry: 2,
  });
}

export function useUnreadCount() {
  return useQuery<UnreadCountResponse>({
    queryKey: ['notifications', 'unread-count'],
    queryFn: async () => (await client.get('/notifications/unread-count/')).data,
    staleTime: 15_000,
    refetchInterval: 30_000,
    retry: 2,
  });
}

export function useMarkNotificationRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string): Promise<MobileNotification> =>
      (await client.patch(`/notifications/${id}/read/`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications'] });
    },
  });
}

export function useMarkAllRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => (await client.post('/notifications/mark-all-read/')).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications'] });
    },
  });
}

export function useUploadPhoto() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: UploadPhotoPayload): Promise<InspectionPhoto> => {
      // Resize to max 1920px client-side before upload.
      const manipulated = await ImageManipulator.manipulateAsync(
        params.uri,
        [{ resize: { width: 1920 } }],
        { compress: 0.85, format: ImageManipulator.SaveFormat.JPEG },
      );

      const formData = new FormData();
      formData.append('photo', {
        uri: manipulated.uri,
        type: 'image/jpeg',
        name: `photo_${Date.now()}.jpg`,
      } as unknown as Blob);
      formData.append('latitude', String(params.latitude));
      formData.append('longitude', String(params.longitude));
      if (params.accuracy != null) formData.append('accuracy_meters', String(params.accuracy));
      formData.append('captured_at', params.capturedAt);
      formData.append('caption', params.caption ?? '');

      const res = await client.post(`/flags/${params.flagId}/photos/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return res.data;
    },
    onSuccess: (_data, { flagId }) => {
      qc.invalidateQueries({ queryKey: ['flag', flagId, 'photos'] });
      qc.invalidateQueries({ queryKey: ['flag', flagId] });
    },
  });
}
