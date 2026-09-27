/**
 * The app's icon set, in one place. Phosphor icons under the names the screens use,
 * plus Meyora's own marks. Swap an icon here and it changes everywhere.
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

/** Anything that renders like an icon: Phosphor's or Meyora's own. */
export type Icon = ComponentType<Pick<IconProps, "className" | "weight">>;
export type { IconWeight };

type MarkProps = Omit<SVGProps<SVGSVGElement>, "ref"> & { weight?: IconWeight };

/**
 * Meyora's AI glyph: an orb carrying the "V" of the Meyora M, with a spark at its edge.
 * Used wherever the assistant appears, in place of generic sparkles or brains.
 */
export function Sparkles({ weight = "regular", className, ...rest }: MarkProps) {
  const stroke = weight === "bold" || weight === "fill" ? 2.1 : weight === "light" || weight === "thin" ? 1.25 : 1.6;
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={stroke} strokeLinecap="round"
      strokeLinejoin="round" aria-hidden="true" className={className} width="1em" height="1em" {...rest}>
      {weight === "fill" ? <circle cx="11.5" cy="12.5" r="8.25" fill="currentColor" fillOpacity={0.16} /> : null}
      <path d="M18.9 9.1A8.25 8.25 0 1 1 14.9 5" />
      <path d="M7.9 10.2 11.5 15l3.6-4.8" />
      <path d="M18.4 3.2v3.6M16.6 5h3.6" />
    </svg>
  );
}

/** The Meyora "M" monogram, from the brand. Inherits currentColor. */
export function LogoMark({ className, ...rest }: Omit<SVGProps<SVGSVGElement>, "ref">) {
  return (
    <svg viewBox="0 0 100 100" fill="currentColor" role="img" aria-label="Meyora" className={className}
      width="1em" height="1em" {...rest}>
      <path d="M6 94V6h26l18 36 18-36h26v88H70V54L56 78H44L30 54v40z" />
      <path d="M43 83h14l-7 12z" />
    </svg>
  );
}
