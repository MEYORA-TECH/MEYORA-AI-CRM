import { useForm } from "react-hook-form";
import { Link, useSearchParams } from "react-router-dom";

import { useAuthProviders } from "@/email/api";
import { Button, Field, Input } from "@/components/ui/primitives";
import { describeError, apiUrl } from "@/services/api";
import { useAuth } from "@/stores/auth";
import { AuthLayout } from "./AuthLayout";

export function LoginPage() {
  const login = useAuth((s) => s.login);
  const form = useForm<{ email: string; password: string }>();
  const { errors, isSubmitting } = form.formState;
  const providers = useAuthProviders();
  const [params] = useSearchParams();
  const googleError = {
    google_failed: "Google sign-in didn't work. Please try again.",
    google_cancelled: "Google sign-in was cancelled.",
    google_disabled: "Google sign-in isn't available right now.",
  }[params.get("error") ?? ""];

  const submit = form.handleSubmit(async ({ email, password }) => {
    try {
      await login(email, password);
    } catch (e) {
      form.setError("root", { message: describeError(e) });
    }
  });

  return (
    <AuthLayout
      title="Welcome back"
      subtitle="Sign in to your workspace."
      footer={<>New to Meyora? <Link to="/register" className="font-semibold text-jade hover:underline">Create a workspace</Link></>}
    >
      {providers.data?.google ? (
        <>
          <a href={apiUrl("/auth/google/start")}
            className="focus-ring glass-dense flex h-11 items-center justify-center gap-2.5 rounded-[var(--radius-control)] text-sm font-semibold transition hover:bg-[var(--glass-2)]">
            <GoogleMark /> Continue with Google
          </a>
          <div className="my-5 flex items-center gap-3 text-xs text-ink-3"><span className="h-px flex-1 bg-[var(--line-strong)]" />or<span className="h-px flex-1 bg-[var(--line-strong)]" /></div>
        </>
      ) : null}
      {googleError ? <p role="alert" className="mb-4 rounded-xl bg-danger-soft px-3 py-2 text-sm font-medium text-danger">{googleError}</p> : null}
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <Field label="Work email" htmlFor="email" error={errors.email?.message}>
          <Input id="email" type="email" autoComplete="email" autoFocus aria-invalid={Boolean(errors.email)}
            {...form.register("email", { required: "Enter your email" })} />
        </Field>
        <Field label="Password" htmlFor="password" error={errors.password?.message}>
          <Input id="password" type="password" autoComplete="current-password" aria-invalid={Boolean(errors.password)}
            {...form.register("password", { required: "Enter your password" })} />
        </Field>
        {errors.root ? <p role="alert" className="rounded-xl bg-danger-soft px-3 py-2 text-sm font-medium text-danger">{errors.root.message}</p> : null}
        <Button variant="primary" type="submit" loading={isSubmitting} className="mt-1 h-11">Sign in</Button>
      </form>
    </AuthLayout>
  );
}

function GoogleMark() {
  return (
    <svg viewBox="0 0 18 18" className="size-[18px]" aria-hidden>
      <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z" />
      <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z" />
      <path fill="#FBBC05" d="M3.97 10.72A5.4 5.4 0 0 1 3.69 9c0-.6.1-1.18.28-1.72V4.95H.96A9 9 0 0 0 0 9c0 1.45.35 2.83.96 4.05l3.01-2.33z" />
      <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z" />
    </svg>
  );
}
