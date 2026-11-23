import {
	type KeyboardEvent,
	type ReactNode,
	useEffect,
	useSyncExternalStore,
} from "react";
import { setHashParams, useQuery } from "./hashState";
import { SearchIcon } from "./icons";

export type Tone = "ok" | "warn" | "danger" | "info" | "muted";

// A tiny external store, so hooks in any page can feed the shell (live region, document title).
function createStore<T>(initial: T) {
	let value = initial;
	const listeners = new Set<() => void>();
	return {
		get: () => value,
		set(next: T) {
			if (next === value) return;
			value = next;
			for (const l of listeners) l();
		},
		subscribe(l: () => void) {
			listeners.add(l);
			return () => listeners.delete(l);
		},
	};
}

const announcement = createStore("");
const titleOverride = createStore<string | null>(null);

export function PageHeader({
	title,
	count,
	children,
	filter,
	back,
	above,
}: {
	title: string;
	count?: number | string;
	children?: ReactNode;
	filter?: ReactNode;
	back?: { href: string; label: string };
	// A full-width line above the title, e.g. a breadcrumb.
	above?: ReactNode;
}) {
	return (
		<header className="page-header">
			{above && <div className="page-above">{above}</div>}
			<div className="page-title-group">
				{back && (
					<a className="page-back" href={back.href}>
						← {back.label}
					</a>
				)}
				<h1>{title}</h1>
				{count != null && <span className="page-count">{count}</span>}
			</div>
			{children && <div className="page-controls">{children}</div>}
			{filter && <div className="page-filter">{filter}</div>}
		</header>
	);
}

// The h2 holds only the title, so `getByRole("heading", { name })` and `getByText(title)` match
// it exactly; the count and any extras are siblings.
export function GroupHead({
	title,
	count,
	tone,
	children,
}: {
	title: string;
	count?: number;
	tone?: Tone;
	children?: ReactNode;
}) {
	return (
		<div className="group-head">
			<h2>{title}</h2>
			{count != null && (
				<span className={tone ? `group-count tone-${tone}` : "group-count"}>
					{count}
				</span>
			)}
			{children && <div className="group-extra">{children}</div>}
		</div>
	);
}

export function FilterBox({
	placeholder = "Filter artist or title",
}: {
	placeholder?: string;
}) {
	const q = useQuery();
	function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
		if (e.key !== "Escape") return;
		e.preventDefault();
		if (e.currentTarget.value) setHashParams({ q: null }, { replace: true });
		else e.currentTarget.blur();
	}
	return (
		<div className="filter-box">
			<span className="filter-icon">
				<SearchIcon size={14} />
			</span>
			<input
				type="search"
				className="filter-input"
				aria-label="Filter"
				placeholder={placeholder}
				value={q}
				onChange={(e) =>
					setHashParams({ q: e.target.value }, { replace: true })
				}
				onKeyDown={onKeyDown}
			/>
			<span className="kbd filter-kbd" aria-hidden="true">
				/
			</span>
		</div>
	);
}

export function Segmented<T extends string>({
	ariaLabel,
	value,
	onChange,
	options,
}: {
	ariaLabel: string;
	value: T;
	onChange: (value: T) => void;
	options: { value: T; label: string; count?: number }[];
}) {
	return (
		// biome-ignore lint/a11y/useSemanticElements: a fieldset would bring form semantics and legend styling to a toolbar-like control
		<div className="segmented" role="group" aria-label={ariaLabel}>
			{options.map((o) => (
				<button
					key={o.value}
					type="button"
					className="seg-item"
					aria-pressed={o.value === value}
					onClick={() => onChange(o.value)}
				>
					{o.label}
					{o.count != null && (
						<>
							{" "}
							<span className="seg-count">{o.count}</span>
						</>
					)}
				</button>
			))}
		</div>
	);
}

export function SegmentedLinks({
	ariaLabel,
	current,
	items,
	ariaCurrent = "page",
	onSelect,
}: {
	ariaLabel: string;
	current: string | null;
	items: { key: string; href: string; label: string; title?: string }[];
	ariaCurrent?: "page" | "date";
	onSelect?: (key: string) => void;
}) {
	return (
		<nav className="segmented" aria-label={ariaLabel}>
			{items.map((it) => (
				<a
					key={it.key}
					className="seg-item"
					href={it.href}
					title={it.title}
					aria-current={it.key === current ? ariaCurrent : undefined}
					onClick={() => onSelect?.(it.key)}
				>
					{it.label}
				</a>
			))}
		</nav>
	);
}

export function Badge({
	children,
	title,
}: {
	children: ReactNode;
	title?: string;
}) {
	return (
		<span className="badge" title={title}>
			{children}
		</span>
	);
}

export function StatusBadge({
	tone,
	children,
	pulse = false,
}: {
	tone: Tone;
	children: ReactNode;
	pulse?: boolean;
}) {
	return (
		<span className={`status status-${tone}${pulse ? " pulse" : ""}`}>
			{children}
		</span>
	);
}

export const IMPORT_STATE_TONE: Record<
	| "detected"
	| "queued"
	| "importing"
	| "imported"
	| "skipped"
	| "failed"
	| "dismissed",
	Tone
> = {
	detected: "muted",
	queued: "info",
	importing: "info",
	imported: "ok",
	skipped: "muted",
	failed: "danger",
	dismissed: "muted",
};

// Always aria-hidden: shortcut hints are visual, and must not change a button's accessible name.
export function Kbd({ children }: { children: string }) {
	return (
		<span className="kbd" aria-hidden="true">
			{children}
		</span>
	);
}

export function ListHints({
	items,
}: {
	items: [keys: string, label: string][];
}) {
	return (
		<p className="list-hints" aria-hidden="true">
			{items.map(([keys, label]) => (
				<span key={keys}>
					<Kbd>{keys}</Kbd>
					{label}
				</span>
			))}
		</p>
	);
}

export function Loading({
	rows = 3,
	compact = false,
}: {
	rows?: number;
	compact?: boolean;
}) {
	return (
		<div role="status">
			<span className="sr-only">Loading…</span>
			<div
				className={compact ? "skeleton compact" : "skeleton"}
				aria-hidden="true"
			>
				{Array.from({ length: rows }, (_, i) => (
					// biome-ignore lint/suspicious/noArrayIndexKey: static placeholder rows
					<div className="skeleton-row" key={i}>
						<span className="skeleton-bar skeleton-cover" />
						<span className="skeleton-bar" style={{ width: "22%" }} />
						<span className="skeleton-bar" style={{ width: "34%" }} />
					</div>
				))}
			</div>
		</div>
	);
}

export function EmptyState({
	title,
	hint,
	action,
}: {
	title: string;
	hint?: ReactNode;
	action?: ReactNode;
}) {
	return (
		<div className="state">
			<p className="state-title">{title}</p>
			{hint && <p className="state-hint">{hint}</p>}
			{action && <div className="state-action">{action}</div>}
		</div>
	);
}

export function NoMatches({ query, what }: { query: string; what?: string }) {
	return (
		<EmptyState
			title={`No matches for “${query}”`}
			hint={what ? `Nothing in ${what} matches the filter.` : undefined}
			action={
				<button
					type="button"
					onClick={() => setHashParams({ q: null }, { replace: true })}
				>
					Clear filter
				</button>
			}
		/>
	);
}

export function ErrorState({
	what,
	onRetry,
}: {
	what: string;
	onRetry?: () => void;
}) {
	return (
		<div className="state state-error" role="alert">
			<p className="state-title">Couldn’t load {what}.</p>
			<p className="state-hint">The server didn’t respond.</p>
			{onRetry && (
				<div className="state-action">
					<button type="button" onClick={onRetry}>
						Retry
					</button>
				</div>
			)}
		</div>
	);
}

export function PollWarning({ show }: { show: boolean }) {
	if (!show) return null;
	return <p className="poll-warning">Reconnecting…</p>;
}

export function useAnnounceCount(
	shown: number,
	total: number,
	active: boolean,
): void {
	useEffect(() => {
		announcement.set(active ? `${shown} of ${total} shown` : "");
	}, [shown, total, active]);
	useEffect(() => () => announcement.set(""), []);
}

// The shell's only live region.
export function LiveRegion() {
	const text = useSyncExternalStore(
		announcement.subscribe,
		announcement.get,
		announcement.get,
	);
	return (
		<div className="sr-only" aria-live="polite">
			{text}
		</div>
	);
}

// A page that knows a better title than the shell's default (e.g. a crate's name) sets it here,
// without the " · mcm" suffix. Pass null to fall back to the default.
export function usePageTitle(title: string | null): void {
	useEffect(() => {
		titleOverride.set(title);
		return () => titleOverride.set(null);
	}, [title]);
}

export function usePageTitleOverride(): string | null {
	return useSyncExternalStore(
		titleOverride.subscribe,
		titleOverride.get,
		titleOverride.get,
	);
}
