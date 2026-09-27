import { lazy, useEffect, type ComponentType } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { Spinner } from "@/components/ui/primitives";
import { AppShell } from "@/layouts/AppShell";
import { AcceptInvitePage } from "@/pages/auth/AcceptInvitePage";
import { LoginPage } from "@/pages/auth/LoginPage";
import { RegisterPage } from "@/pages/auth/RegisterPage";

// Each module loads on first visit, keeping the initial bundle small.
const named = <K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) =>
  lazy(() => load().then((m) => ({ default: m[name] })));
const CompaniesPage = named(() => import("@/pages/CompaniesPage"), "CompaniesPage");
const CompanyDetailPage = named(() => import("@/pages/CompaniesPage"), "CompanyDetailPage");
const ContactsPage = named(() => import("@/pages/ContactsPage"), "ContactsPage");
const ContactDetailPage = named(() => import("@/pages/ContactsPage"), "ContactDetailPage");
const DashboardPage = named(() => import("@/pages/DashboardPage"), "DashboardPage");
const DealsPage = named(() => import("@/pages/DealsPage"), "DealsPage");
const DealDetailPage = named(() => import("@/pages/DealsPage"), "DealDetailPage");
const LeadsPage = named(() => import("@/pages/LeadsPage"), "LeadsPage");
const LeadDetailPage = named(() => import("@/pages/LeadsPage"), "LeadDetailPage");
const SettingsPage = named(() => import("@/pages/SettingsPage"), "SettingsPage");
const ActivitiesPage = named(() => import("@/pages/WorkPages"), "ActivitiesPage");
const TasksPage = named(() => import("@/pages/WorkPages"), "TasksPage");
const AssistantPage = named(() => import("@/pages/AssistantPage"), "AssistantPage");
const MemoryPage = named(() => import("@/pages/MemoryPage"), "MemoryPage");
const EmailsPage = named(() => import("@/pages/EmailsPage"), "EmailsPage");
import { useAuth } from "@/stores/auth";

function NoWorkspace() {
  const logout = useAuth((s) => s.logout);
  return (
    <div className="flex min-h-full flex-col items-center justify-center gap-3 p-6 text-center">
      <div className="ambient" aria-hidden />
      <h1 className="text-2xl font-display font-bold tracking-tight">You're not in a workspace</h1>
      <p className="max-w-sm text-sm text-ink-2">Ask an admin to invite you, then open the invitation link.</p>
      <button className="text-sm font-semibold text-jade hover:underline" onClick={() => logout()}>Sign out</button>
    </div>
  );
}

export function App() {
  const status = useAuth((s) => s.status);
  const me = useAuth((s) => s.me);
  const bootstrap = useAuth((s) => s.bootstrap);
  const location = useLocation();

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  if (status === "loading") {
    return (
      <div className="flex min-h-full items-center justify-center">
        <div className="ambient" aria-hidden />
        <Spinner />
      </div>
    );
  }

  if (status === "anonymous") {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="*" element={<Navigate to="/login" replace state={{ from: location.pathname }} />} />
      </Routes>
    );
  }

  if (location.pathname === "/register" && new URLSearchParams(location.search).get("invite")) {
    return <AcceptInvitePage />;
  }
  if (!me?.current_organization_id) return <NoWorkspace />;

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<DashboardPage />} />
        <Route path="companies" element={<CompaniesPage />} />
        <Route path="companies/:id" element={<CompanyDetailPage />} />
        <Route path="contacts" element={<ContactsPage />} />
        <Route path="contacts/:id" element={<ContactDetailPage />} />
        <Route path="leads" element={<LeadsPage />} />
        <Route path="leads/:id" element={<LeadDetailPage />} />
        <Route path="deals" element={<DealsPage />} />
        <Route path="deals/:id" element={<DealDetailPage />} />
        <Route path="activities" element={<ActivitiesPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="assistant" element={<AssistantPage />} />
        <Route path="assistant/:id" element={<AssistantPage />} />
        <Route path="memory" element={<MemoryPage />} />
        <Route path="emails" element={<EmailsPage />} />
        <Route path="emails/:id" element={<EmailsPage />} />
      </Route>
      <Route path="/login" element={<Navigate to="/" replace />} />
      <Route path="/register" element={<Navigate to="/" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
