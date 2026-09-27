import { LayoutGroup, motion } from "motion/react";
import { NavLink, useLocation } from "react-router-dom";

import { usePrefetchRoute } from "@/hooks/resources";
import { cn } from "@/lib/format";
import { isActive, PRIMARY_NAV, SECONDARY_NAV, type NavItem } from "./nav";

/**
 * The floating dark glass rail. Collapsed it shows icons; hovering or tabbing
 * into it expands it over the content to reveal labels. A frosted "lens"
 * glides to the active item — the one piece of motion in the shell.
 */
export function Sidebar() {
  const { pathname } = useLocation();
  const prefetch = usePrefetchRoute();

  const renderItem = (item: NavItem) => {
    const active = isActive(pathname, item.to);
    const Icon = item.icon;
    return (
      <li key={item.to}>
        <NavLink
          to={item.to}
          end={item.to === "/"}
          aria-label={item.label}
          onMouseEnter={() => prefetch(item.to)}
          onFocus={() => prefetch(item.to)}
          className={cn(
            "group/item relative flex h-11 items-center gap-3 rounded-2xl px-3 outline-none",
            "text-[var(--rail-ink)] transition-colors hover:text-white focus-visible:text-white",
            active && "text-white",
          )}
        >
          {active ? (
            <motion.span
              layoutId="rail-lens"
              className="absolute inset-0 rounded-2xl bg-[var(--rail-lens)] shadow-[inset_0_1px_0_rgb(255_255_255/0.14)]"
              transition={{ type: "spring", stiffness: 520, damping: 40 }}
            />
          ) : null}
          <span className="pointer-events-none absolute inset-0 rounded-2xl ring-[var(--jade)] group-focus-visible/item:ring-2" />
          <Icon className="relative size-[19px] shrink-0" weight={active ? "fill" : "regular"} />
          <span className="relative text-sm font-semibold whitespace-nowrap opacity-0 transition-opacity duration-150 group-hover/rail:opacity-100 group-has-[:focus-visible]/rail:opacity-100">
            {item.label}
          </span>
        </NavLink>
      </li>
    );
  };

  return (
    <>
      {/* Desktop rail */}
      <nav
        aria-label="Main"
        className={cn(
          "group/rail glass-rail fixed top-1/2 left-4 z-30 hidden -translate-y-1/2 flex-col rounded-[28px] p-2 md:flex",
          "w-[60px] overflow-hidden transition-[width] duration-200 ease-out hover:w-[196px] has-[:focus-visible]:w-[196px]",
        )}
      >
        <LayoutGroup id="rail">
          <ul className="flex flex-col gap-1">{PRIMARY_NAV.map(renderItem)}</ul>
          <div className="mx-2 my-2 h-px bg-white/10" />
          <ul className="flex flex-col gap-1">{SECONDARY_NAV.map(renderItem)}</ul>
        </LayoutGroup>
      </nav>

      {/* Mobile dock */}
      <nav
        aria-label="Main"
        className="glass-rail fixed right-3 bottom-3 left-3 z-30 flex justify-between rounded-[24px] px-2 py-1.5 md:hidden"
      >
        <LayoutGroup id="dock">
          {[...PRIMARY_NAV.slice(0, 5), SECONDARY_NAV[0]].map((item) => {
            const active = isActive(pathname, item.to);
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                aria-label={item.label}
                className={cn("relative flex size-11 items-center justify-center rounded-2xl text-[var(--rail-ink)]", active && "text-white")}
              >
                {active ? (
                  <motion.span layoutId="dock-lens" className="absolute inset-0 rounded-2xl bg-[var(--rail-lens)]" transition={{ type: "spring", stiffness: 520, damping: 40 }} />
                ) : null}
                <Icon className="relative size-5" />
              </NavLink>
            );
          })}
        </LayoutGroup>
      </nav>
    </>
  );
}
