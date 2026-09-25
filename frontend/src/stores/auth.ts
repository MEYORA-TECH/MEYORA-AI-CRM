import { create } from "zustand";

import { api, configureSession, refreshSession, setAccessToken } from "@/services/api";
import type { Me, Perm, TokenResponse } from "@/types";

type Status = "loading" | "authenticated" | "anonymous";

interface AuthState {
  status: Status;
  me: Me | null;
  bootstrap: () => Promise<void>;
  applyTokens: (body: TokenResponse) => void;
  login: (email: string, password: string) => Promise<void>;
  register: (input: {
    email: string;
    password: string;
    full_name: string;
    organization_name?: string;
    invite_token?: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
  switchOrganization: (organizationId: string) => Promise<void>;
  can: (perm: Perm) => boolean;
}

export const useAuth = create<AuthState>((set, get) => ({
  status: "loading",
  me: null,

  async bootstrap() {
    const ok = await refreshSession();
    if (!ok) set({ status: "anonymous", me: null });
  },

  applyTokens(body) {
    setAccessToken(body.access_token);
    set({ status: "authenticated", me: body.me });
  },

  async login(email, password) {
    get().applyTokens(await api.post<TokenResponse>("/auth/login", { email, password }));
  },

  async register(input) {
    get().applyTokens(await api.post<TokenResponse>("/auth/register", input));
  },

  async logout() {
    try {
      await api.post("/auth/logout");
    } finally {
      setAccessToken(null);
      set({ status: "anonymous", me: null });
    }
  },

  async switchOrganization(organizationId) {
    get().applyTokens(
      await api.post<TokenResponse>("/auth/switch-organization", { organization_id: organizationId }),
    );
  },

  can(perm) {
    return get().me?.permissions.includes(perm) ?? false;
  },
}));

configureSession({
  onExpired: () => {
    setAccessToken(null);
    useAuth.setState({ status: "anonymous", me: null });
  },
  onRefreshed: (body) => useAuth.getState().applyTokens(body as TokenResponse),
});

export const useCan = (perm: Perm) => useAuth((s) => s.me?.permissions.includes(perm) ?? false);

/** The current organization's default currency (dashboard and board totals use it). */
export const useCurrency = () =>
  useAuth((s) => s.me?.memberships.find((m) => m.organization.id === s.me?.current_organization_id)?.organization.default_currency ?? "INR");
