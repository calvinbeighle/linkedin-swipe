import axios from "axios";
import { API_CONFIG } from "../config";
import type { Profile, SwipeStats } from "../types/profile";

const api = axios.create({
  baseURL: API_CONFIG.baseURL,
  headers: {
    Authorization: `Bearer ${API_CONFIG.apiKey}`,
    "Content-Type": "application/json",
    "ngrok-skip-browser-warning": "true",
  },
});

export async function getPendingProfiles(limit = 50): Promise<Profile[]> {
  const { data } = await api.get<Profile[]>(`/profiles?limit=${limit}`);
  return data;
}

export async function recordSwipe(
  profileId: number,
  direction: "right" | "left",
): Promise<void> {
  await api.post("/swipe", { profile_id: profileId, direction });
}

export async function getLikedProfiles(): Promise<Profile[]> {
  const { data } = await api.get<Profile[]>("/liked");
  return data;
}

export async function getStats(): Promise<SwipeStats> {
  const { data } = await api.get<SwipeStats>("/stats");
  return data;
}
