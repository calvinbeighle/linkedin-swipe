export interface Profile {
  id: number;
  linkedin_url: string;
  name: string;
  headline?: string;
  company?: string;
  location?: string;
  photo_url?: string;
  status: "pending" | "liked" | "skipped";
  created_at: string;
}

export interface SwipeStats {
  total: number;
  pending: number;
  liked: number;
  skipped: number;
}
