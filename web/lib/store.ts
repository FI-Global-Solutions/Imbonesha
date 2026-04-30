import { create } from "zustand";

interface UIState {
  selectedFlagId: number | null;
  drawerOpen: boolean;
  triggerDialogOpen: boolean;
  setSelectedFlag: (id: number | null) => void;
  openDrawer: (id: number) => void;
  closeDrawer: () => void;
  setTriggerDialogOpen: (open: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  selectedFlagId: null,
  drawerOpen: false,
  triggerDialogOpen: false,
  setSelectedFlag: (id) => set({ selectedFlagId: id }),
  openDrawer: (id) => set({ selectedFlagId: id, drawerOpen: true }),
  closeDrawer: () => set({ drawerOpen: false }),
  setTriggerDialogOpen: (open) => set({ triggerDialogOpen: open }),
}));
