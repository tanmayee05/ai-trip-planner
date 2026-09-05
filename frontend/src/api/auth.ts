import { api } from "@/lib/api";
import type { AuthResponse, User } from "@/types/api";

export function signup(body: { email: string; name: string; password: string }) {
  return api.post<AuthResponse>("/auth/signup", body).then((r) => r.data);
}

export function login(body: { email: string; password: string }) {
  return api.post<AuthResponse>("/auth/login", body).then((r) => r.data);
}

export function fetchMe() {
  return api.get<User>("/auth/me").then((r) => r.data);
}
