/**
 * The app's icon set, in one place. Phosphor icons under the names the screens use,
 * plus Nila's own marks. Swap an icon here and it changes everywhere.
 */
import type { IconProps, IconWeight } from "@phosphor-icons/react";
import type { ComponentType, SVGProps } from "react";

export {
  WarningIcon as AlertTriangle,
  ArrowDownIcon as ArrowDown,
  ArrowDownLeftIcon as ArrowDownLeft,
  ArrowLeftIcon as ArrowLeft,
  ArrowRightIcon as ArrowRight,
  ArrowCircleRightIcon as ArrowRightCircle,
  ArrowsLeftRightIcon as ArrowRightLeft,
  ArrowUpIcon as ArrowUp,
  ArrowUpRightIcon as ArrowUpRight,
  BookmarksSimpleIcon as Brain, // "Memory": saved facts, not a brain
  BuildingIcon as Building,
  BuildingsIcon as Building2,
  CalendarCheckIcon as CalendarClock,
  CalendarBlankIcon as CalendarDays,
  CalendarPlusIcon as CalendarPlus,
  CalendarDotsIcon as CalendarRange,
  CheckIcon as Check,
  CheckSquareIcon as CheckSquare,
  CaretDownIcon as ChevronDown,
  CaretLeftIcon as ChevronLeft,
  CaretRightIcon as ChevronRight,
  CaretUpDownIcon as ChevronsUpDown,
  CopyIcon as Copy,
  ArrowSquareOutIcon as ExternalLink,
  GlobeIcon as Globe,
  HandshakeIcon as Handshake,
  KanbanIcon as KanbanSquare,
  KeyIcon as KeyRound,
  LinkedinLogoIcon as Linkedin,
  SquaresFourIcon as LayoutDashboard,
  ListBulletsIcon as List,
  CircleNotchIcon as Loader2,
  LockIcon as Lock,
  LockKeyIcon as LockKeyhole,
  SignOutIcon as LogOut,
  MagnetIcon as Magnet,
  EnvelopeSimpleIcon as Mail,
  ArrowsOutIcon as Maximize2,
  ChatCircleDotsIcon as MessageSquarePlus,
  ChatCenteredTextIcon as MessageSquareText,
  MonitorIcon as Monitor,
  MoonIcon as Moon,
  DotsThreeIcon as MoreHorizontal,
  NotePencilIcon as NotebookPen,
  PaperclipIcon as Paperclip,
  PencilSimpleIcon as Pencil,
  PhoneIcon as Phone,
  PushPinIcon as Pin,
  PlusIcon as Plus,
  ArrowClockwiseIcon as RefreshCw,
  MagnifyingGlassIcon as Search,
  GearSixIcon as Settings,
  ShieldCheckIcon as ShieldCheck,
  SquareIcon as Square,
  NoteIcon as StickyNote,
  SunIcon as Sun,
  TrashIcon as Trash2,
  PlugsIcon as Unplug,
  UserMinusIcon as UserMinus,
  UserIcon as UserRound,
  UsersIcon as Users,
  UsersThreeIcon as UsersRound,
  XIcon as X,
} from "@phosphor-icons/react";

/** Anything that renders like an icon: Phosphor's or Nila's own. */
export type Icon = ComponentType<Pick<IconProps, "className" | "weight">>;
export type { IconWeight };

type MarkProps = Omit<SVGProps<SVGSVGElement>, "ref"> & { weight?: IconWeight };

/**
 * Nila's AI glyph: the Nila crescent with a spark beside it.
 * Used wherever the assistant appears, in place of generic sparkles or brains.
 */
export function Sparkles({ weight = "regular", className, ...rest }: MarkProps) {
  const stroke = weight === "bold" || weight === "fill" ? 2.1 : weight === "light" || weight === "thin" ? 1.25 : 1.6;
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={stroke} strokeLinecap="round"
      strokeLinejoin="round" aria-hidden="true" className={className} width="1em" height="1em" {...rest}>
      <path d="M18.86 14.67A8 8 0 1 1 9.53 5.34A6.6 6.6 0 0 0 18.86 14.67Z"
        fill={weight === "fill" ? "currentColor" : "none"} fillOpacity={weight === "fill" ? 0.16 : undefined} />
      <path d="M18.4 3.2v3.6M16.6 5h3.6" />
    </svg>
  );
}

/**
 * The Nila wordmark (design/logo/final/nila-wordmark.svg). Letters take currentColor, so the
 * light and dark themes both work; the crescent that dots the i is always the ice accent.
 */
export function NilaWordmark({ className, ...rest }: Omit<SVGProps<SVGSVGElement>, "ref">) {
  return (
    <svg viewBox="0 16 362 185" fill="currentColor" role="img" aria-label="Nila" className={className}
      width="1.96em" height="1em" {...rest}>
      <path d="M0 80H26V200H0ZM0 140A60 60 0 0 1 120 140V200H94V140A34 34 0 0 0 26 140Z" />
      <path d="M144 80H170V200H144Z" />
      <path fill="var(--ice)" d="M182.98 42.94A25 25 0 1 1 157.06 17.02A19 19 0 1 0 182.98 42.94Z" />
      <path d="M194 30H220V200H194Z" />
      <path fillRule="evenodd" d="M242 140A60 60 0 1 0 362 140A60 60 0 1 0 242 140ZM268 140A34 34 0 1 0 336 140A34 34 0 1 0 268 140Z" />
      <path d="M336 80H362V200H336Z" />
    </svg>
  );
}

/** "Nila" with its "by Meyora" endorsement underneath, right-aligned as in the lockup. */
export function NilaLogo({ className, wordmark = "h-10", endorsement = "text-[12px]" }: {
  className?: string; wordmark?: string; endorsement?: string;
}) {
  return (
    <span className={`inline-flex flex-col items-end gap-0.5 text-ink ${className ?? ""}`}>
      <NilaWordmark className={`${wordmark} w-auto`} />
      <span className={`font-brand leading-none tracking-[0.06em] text-ink-3 ${endorsement}`}>by Meyora</span>
    </span>
  );
}
