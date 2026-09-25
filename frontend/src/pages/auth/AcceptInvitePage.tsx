import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { Spinner } from "@/components/ui/primitives";
import { api, describeError } from "@/services/api";
import { useAuth } from "@/stores/auth";
import type { TokenResponse } from "@/types";
import { AuthLayout } from "./AuthLayout";

/** Opened from an invitation link while already signed in: join the workspace directly. */
export function AcceptInvitePage() {
  const [params] = useSearchParams();
  const token = params.get("invite");
  const applyTokens = useAuth((s) => s.applyTokens);
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(token ? null : "This link has no invitation in it.");
  const started = useRef(false);

  useEffect(() => {
    if (!token || started.current) return;
    started.current = true;
    api
      .post<TokenResponse>("/auth/accept-invitation", { token })
      .then((body) => {
        applyTokens(body);
        navigate("/", { replace: true });
      })
      .catch((e) => setError(describeError(e)));
  }, [token, applyTokens, navigate]);

  return (
    <AuthLayout
      title={error ? "Couldn't accept the invitation" : "Joining workspace…"}
      subtitle={error ?? "One moment."}
      footer={<Link to="/" className="font-semibold text-jade hover:underline">Go to your dashboard</Link>}
    >
      {error ? null : <div className="flex justify-center py-4"><Spinner /></div>}
    </AuthLayout>
  );
}
