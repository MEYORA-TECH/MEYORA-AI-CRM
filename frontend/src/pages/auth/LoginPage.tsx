import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";

import { Button, Field, Input } from "@/components/ui/primitives";
import { describeError } from "@/services/api";
import { useAuth } from "@/stores/auth";
import { AuthLayout } from "./AuthLayout";

export function LoginPage() {
  const login = useAuth((s) => s.login);
  const form = useForm<{ email: string; password: string }>();
  const { errors, isSubmitting } = form.formState;

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
