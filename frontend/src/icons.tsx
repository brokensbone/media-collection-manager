import type { ReactNode } from "react";

type IconProps = { size?: number };

function Stroke({ size = 16, children }: IconProps & { children: ReactNode }) {
	return (
		<svg
			width={size}
			height={size}
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			strokeWidth="1.75"
			strokeLinecap="round"
			strokeLinejoin="round"
			aria-hidden="true"
			focusable="false"
		>
			{children}
		</svg>
	);
}

// Chain link, for the shareable permalink pill.
export function LinkIcon(props: IconProps) {
	return (
		<Stroke {...props}>
			<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
			<path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
		</Stroke>
	);
}

// The Spotify glyph stays a filled path: it is a logo, not a line icon.
export function SpotifyIcon({ size = 16 }: IconProps) {
	return (
		<svg
			width={size}
			height={size}
			viewBox="0 0 24 24"
			fill="currentColor"
			aria-hidden="true"
			focusable="false"
		>
			<path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.5 17.3a.75.75 0 0 1-1.03.25c-2.82-1.72-6.37-2.11-10.55-1.16a.75.75 0 1 1-.33-1.46c4.57-1.04 8.5-.59 11.66 1.34.36.22.47.68.25 1.03zm1.47-3.27a.94.94 0 0 1-1.29.31c-3.23-1.98-8.15-2.56-11.97-1.4a.94.94 0 1 1-.54-1.8c4.36-1.32 9.78-.68 13.49 1.6.44.27.58.85.31 1.29zm.13-3.4C15.36 8.4 8.9 8.16 5.2 9.29a1.12 1.12 0 1 1-.65-2.15c4.25-1.29 11.38-1.04 15.85 1.61a1.12 1.12 0 1 1-1.15 1.93z" />
		</svg>
	);
}

export function ExternalIcon(props: IconProps) {
	return (
		<Stroke {...props}>
			<path d="M14 4h6v6" />
			<path d="M20 4l-9 9" />
			<path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
		</Stroke>
	);
}

export function SearchIcon(props: IconProps) {
	return (
		<Stroke {...props}>
			<circle cx="11" cy="11" r="6.5" />
			<path d="M20 20l-4.2-4.2" />
		</Stroke>
	);
}

export function CloseIcon(props: IconProps) {
	return (
		<Stroke {...props}>
			<path d="M6 6l12 12" />
			<path d="M18 6L6 18" />
		</Stroke>
	);
}

// Points right; rotate with CSS for other directions.
export function ChevronIcon(props: IconProps) {
	return (
		<Stroke {...props}>
			<path d="M9 6l6 6-6 6" />
		</Stroke>
	);
}

export function AlertIcon(props: IconProps) {
	return (
		<Stroke {...props}>
			<circle cx="12" cy="12" r="9" />
			<path d="M12 7.5v5.5" />
			<path d="M12 16.5h.01" />
		</Stroke>
	);
}
