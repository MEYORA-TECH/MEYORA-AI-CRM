import { Building, Check, LogOut, Monitor, Moon, Search, Sun } from "@/components/icons";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Avatar, IconButton } from "@/components/ui/primitives";
import { DropdownMenu, MenuItem, MenuLabel, MenuSeparator } from "@/components/ui/overlay";
import { label } from "@/lib/format";
import { describeError } from "@/services/api";
import { useAuth } from "@/stores/auth";
import { useUi, type Theme } from "@/stores/ui";
import { Orb } from "@/ai/Orb";
import { useAiUi } from "@/ai/store";

const THEMES: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "system", label: "Match system", icon: Monitor },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
];

export function Topbar() {
  const me = useAuth((s) => s.me);
  const logout = useAuth((s) => s.logout);
  const switchOrganization = useAuth((s) => s.switchOrganization);
  const { theme, setTheme, setPaletteOpen } = useUi();
  const setPanelOpen = useAiUi((s) => s.setPanelOpen);
  const navigate = useNavigate();

  const current = me?.memberships.find((m) => m.organization.id === me.current_organization_id);
  const ThemeIcon = THEMES.find((t) => t.value === theme)?.icon ?? Monitor;

  return (
    <header className="relative z-20 flex-none px-4 pt-4 md:pr-6 md:pl-[100px]">
      <div className="glass-soft flex h-14 items-center gap-3 rounded-[20px] px-3 pl-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <img src="/favicon.svg" alt="" className="size-7" />
          <span className="hidden font-brand text-[13px] font-light tracking-[0.26em] text-ink uppercase sm:inline">Meyora</span>
          {current ? (
            <>
              <span className="text-ink-3">/</span>
              <DropdownMenu
                align="start"
                trigger={
                  <button className="focus-ring truncate rounded-lg px-1.5 py-1 text-sm font-semibold text-ink-2 hover:text-ink">
                    {current.organization.name}
                  </button>
                }
              >
                <MenuLabel>Organizations</MenuLabel>
                {me?.memberships.map((m) => (
                  <MenuItem
                    key={m.organization.id}
                    icon={<Building className="size-4 text-ink-3" />}
                    onSelect={async () => {
                      if (m.organization.id === me.current_organization_id) return;
                      try {
                        await switchOrganization(m.organization.id);
                        navigate("/");
                      } catch (e) {
                        toast.error(describeError(e));
                      }
                    }}
                  >
                    <span className="flex-1 truncate">{m.organization.name}</span>
                    {m.organization.id === me.current_organization_id ? <Check className="size-4 text-jade" /> : null}
                  </MenuItem>
                ))}
              </DropdownMenu>
            </>
          ) : null}
        </div>

        <button
          onClick={() => setPaletteOpen(true)}
          className="focus-ring glass-dense ml-auto flex h-9 w-full max-w-72 items-center gap-2 rounded-full px-3.5 text-sm text-ink-3 hover:text-ink-2"
        >
          <Search className="size-4" />
          <span className="flex-1 text-left">Search Meyora</span>
          <kbd className="hidden rounded-md border border-line px-1.5 font-mono text-[11px] sm:inline">Ctrl K</kbd>
        </button>

        <button
          onClick={() => setPanelOpen(!useAiUi.getState().panelOpen)}
          className="focus-ring glass-dense flex h-9 items-center gap-2 rounded-full pr-3.5 pl-1.5 text-sm font-semibold"
          aria-label="Ask Meyora (Ctrl J)"
        >
          <Orb className="size-6" />
          <span className="hidden lg:inline">Ask Meyora</span>
        </button>

        <DropdownMenu trigger={<IconButton label="Theme"><ThemeIcon className="size-[18px]" /></IconButton>}>
          <MenuLabel>Appearance</MenuLabel>
          {THEMES.map((t) => (
            <MenuItem key={t.value} icon={<t.icon className="size-4 text-ink-3" />} onSelect={() => setTheme(t.value)}>
              <span className="flex-1">{t.label}</span>
              {theme === t.value ? <Check className="size-4 text-jade" /> : null}
            </MenuItem>
          ))}
        </DropdownMenu>

        <DropdownMenu
          trigger={
            <button className="focus-ring rounded-full" aria-label="Account menu">
              <Avatar name={me?.full_name} size={34} />
            </button>
          }
        >
          <div className="px-3 pt-2 pb-2">
            <p className="text-sm font-bold">{me?.full_name}</p>
            <p className="text-xs text-ink-3">{me?.email}</p>
            {me?.role ? <p className="mt-1 text-xs font-semibold text-jade">{label(me.role)}</p> : null}
          </div>
          <MenuSeparator />
          <MenuItem icon={<LogOut className="size-4" />} onSelect={() => logout()}>Sign out</MenuItem>
        </DropdownMenu>
      </div>
    </header>
  );
}
