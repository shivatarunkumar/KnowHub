import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function Icon({ children, ...props }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={24}
      height={24}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

export const MenuIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 6h16M4 12h16M4 18h16" />
  </Icon>
);
export const SearchIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.5-3.5" />
  </Icon>
);
export const CreateIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3" y="6" width="13" height="12" rx="2" />
    <path d="m16 10 5-3v10l-5-3M9.5 9.5v5M7 12h5" />
  </Icon>
);
export const UserIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21a8 8 0 0 1 16 0" />
  </Icon>
);
export const HomeIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 11 12 4l8 7v9h-5v-6H9v6H4z" />
  </Icon>
);
export const ShortsIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="6" y="2.5" width="12" height="19" rx="3" />
    <path d="m10.5 9.5 4 2.5-4 2.5z" fill="currentColor" />
  </Icon>
);
export const SubscriptionsIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3" y="8" width="18" height="13" rx="2" />
    <path d="M6 5h12M8 2h8M10.5 12v5l4-2.5z" />
  </Icon>
);
export const HistoryIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
    <path d="M3 3v5h5M12 7v5l3 2" />
  </Icon>
);
export const PlaylistIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 6h12M4 11h12M4 16h7M16 14v6l5-3z" />
  </Icon>
);
export const ClockIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </Icon>
);
export const TopicIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 9h14M5 15h14M10 3 8 21M16 3l-2 18" />
  </Icon>
);
export const LogoMark = (p: IconProps) => (
  <svg viewBox="0 0 32 24" width={30} height={22} aria-hidden="true" {...p}>
    <rect width="32" height="24" rx="6" fill="var(--brand)" />
    <path d="M12.5 7v10l8.5-5z" fill="var(--brand-contrast)" />
  </svg>
);

export const SparkleIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 3.5 13.7 8.3 18.5 10 13.7 11.7 12 16.5 10.3 11.7 5.5 10 10.3 8.3z" />
    <path d="M18 16.5 18.7 18.3 20.5 19 18.7 19.7 18 21.5 17.3 19.7 15.5 19 17.3 18.3z" />
  </Icon>
);

export const SpinnerIcon = (p: IconProps) => (
  <svg viewBox="0 0 24 24" width={18} height={18} aria-hidden="true" {...p}>
    <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2.5" opacity="0.25" />
    <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
      <animateTransform
        attributeName="transform"
        type="rotate"
        from="0 12 12"
        to="360 12 12"
        dur="0.8s"
        repeatCount="indefinite"
      />
    </path>
  </svg>
);

export const RetryIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M20 12a8 8 0 1 1-2.3-5.6" />
    <path d="M20 4v4h-4" />
  </Icon>
);

export const CloseIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Icon>
);

export const LikeIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M7 10v10H4a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1z" />
    <path d="M7 10l4.2-7a2 2 0 0 1 3.7 1.3L14 9h4.6a2 2 0 0 1 2 2.5l-1.7 6.9a2 2 0 0 1-2 1.6H7" />
  </Icon>
);

export const DislikeIcon = (p: IconProps) => (
  <Icon {...p} style={{ transform: "rotate(180deg)", ...(p.style ?? {}) }}>
    <path d="M7 10v10H4a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1z" />
    <path d="M7 10l4.2-7a2 2 0 0 1 3.7 1.3L14 9h4.6a2 2 0 0 1 2 2.5l-1.7 6.9a2 2 0 0 1-2 1.6H7" />
  </Icon>
);

export const ShareIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 12v7a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-7" />
    <path d="M12 15V3M8 7l4-4 4 4" />
  </Icon>
);

export const TrashIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 7h16M10 11v6M14 11v6" />
    <path d="M6 7l1 13h10l1-13M9 7V4h6v3" />
  </Icon>
);

export const PencilIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 20h4L19.5 8.5a2.1 2.1 0 0 0-3-3L5 17v3z" />
    <path d="M14.5 6.5l3 3" />
  </Icon>
);

export const GlobeIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18M12 3c2.5 2.6 2.5 15 0 18-2.5-3-2.5-15.4 0-18z" />
  </Icon>
);

export const LinkIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M10 13.5a4 4 0 0 0 5.7 0l2.8-2.8a4 4 0 0 0-5.7-5.7l-1.3 1.3" />
    <path d="M14 10.5a4 4 0 0 0-5.7 0l-2.8 2.8a4 4 0 0 0 5.7 5.7l1.3-1.3" />
  </Icon>
);

export const PeopleIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="9" cy="8" r="3.4" />
    <path d="M2.5 20a6.5 6.5 0 0 1 13 0" />
    <path d="M16 5.2a3.4 3.4 0 0 1 0 5.6M17.5 14.2A6.5 6.5 0 0 1 21.5 20" />
  </Icon>
);

export const LockIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="4.5" y="10" width="15" height="10" rx="2" />
    <path d="M8 10V7a4 4 0 0 1 8 0v3" />
  </Icon>
);

export const CommentIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 5h16v11H9l-5 4z" />
  </Icon>
);

export const EyeIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
    <circle cx="12" cy="12" r="3" />
  </Icon>
);
