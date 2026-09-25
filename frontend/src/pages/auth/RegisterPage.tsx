import { useForm } from "react-hook-form";
import { Link, useSearchParams } from "react-router-dom";

import { Button, Field, Input } from "@/components/ui/primitives";
import { describeError } from "@/services/api";
import { useAuth } from "@/stores/auth";
import { AuthLayout } from "./AuthLayout";

interface Values {
  full_name: string;
  email: string;
  password: string;
  organization_name: string;
}

/** Creates a workspace, or joins one when opened from an invitation link (?invite=…). */
export function RegisterPage() {
  const register = useAuth((s) => s.register);
  const [params] = useSearchParams();
  const invite = params.get("invite");
  const form = useForm<Values>({ defaultValues: { email: params.get("email") ?? "" } });
  const { errors, isSubmitting } = form.formState;

  const submit = form.handleSubmit(async (v) => {
    try {
      await register({
        full_name: v.full_name,
        email: v.email,
        password: v.password,
        ...(invite ? { invite_token: invite } : { organization_name: v.organization_name }),
      });
    } catch (e) {
      form.setError("root", { message: describeError(e) });
    }
  });

  return (
    <AuthLayout
      title={invite ? "Join your team" : "Create your workspace"}
      subtitle={invite ? "Set up your account to accept the invitation." : "Your team's CRM, ready in a minute."}
      footer={<>Already have an account? <Link to="/login" className="font-semibold text-jade hover:underline">Sign in</Link></>}
    >
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <Field label="Full name" htmlFor="full_name" error={errors.full_name?.message}>
          <Input id="full_name" autoComplete="name" autoFocus aria-invalid={Boolean(errors.full_name)}
            {...form.register("full_name", { required: "Enter your name" })} />
        </Field>
        <Field label="Work email" htmlFor="email" error={errors.email?.message}
          hint={invite ? "Use the address the invitation was sent to." : undefined}>
          <Input id="email" type="email" autoComplete="email" aria-invalid={Boolean(errors.email)}
            {...form.register("email", { required: "Enter your email", pattern: { value: /^\S+@\S+\.\S+$/, message: "Enter a valid email" } })} />
        </Field>
        <Field label="Password" htmlFor="password" error={errors.password?.message} hint="At least 10 characters.">
          <Input id="password" type="password" autoComplete="new-password" aria-invalid={Boolean(errors.password)}
            {...form.register("password", { required: "Choose a password", minLength: { value: 10, message: "Use at least 10 characters" } })} />
        </Field>
        {!invite ? (
          <Field label="Company name" htmlFor="organization_name" error={errors.organization_name?.message}>
            <Input id="organization_name" autoComplete="organization" aria-invalid={Boolean(errors.organization_name)}
              {...form.register("organization_name", { required: "Enter your company name" })} />
          </Field>
        ) : null}
        {errors.root ? <p role="alert" className="rounded-xl bg-danger-soft px-3 py-2 text-sm font-medium text-danger">{errors.root.message}</p> : null}
        <Button variant="primary" type="submit" loading={isSubmitting} className="mt-1 h-11">
          {invite ? "Join workspace" : "Create workspace"}
        </Button>
      </form>
    </AuthLayout>
  );
}
