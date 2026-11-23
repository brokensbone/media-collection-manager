import "./pages-tools.css";
import { useEffect, useState } from "react";

type Status = {
	connected: boolean;
	authorized_at: string | null;
	reauth_in_days: number | null;
	reauth_due: boolean;
};

const LOGIN_URL = "/auth/spotify/login";
const COUNTDOWN_VISIBLE_DAYS = 14;

function Dot({ tone }: { tone: "ok" | "warn" | "danger" }) {
	return <span className={`spotify-dot dot-${tone}`} aria-hidden="true" />;
}

export function SpotifyStatus() {
	const [status, setStatus] = useState<Status | null>(null);

	useEffect(() => {
		fetch("/auth/spotify/status")
			.then((r) => r.json())
			.then(setStatus)
			.catch(() => setStatus(null));
	}, []);

	if (!status) return <span className="spotify-status muted">Spotify: …</span>;

	if (!status.connected) {
		return (
			<a className="spotify-status" href={LOGIN_URL}>
				<Dot tone="danger" />
				Connect Spotify
			</a>
		);
	}

	const countdown =
		status.reauth_in_days !== null
			? ` · reauth in ${status.reauth_in_days}d`
			: "";
	const soon =
		!status.reauth_due &&
		status.reauth_in_days !== null &&
		status.reauth_in_days <= COUNTDOWN_VISIBLE_DAYS;

	return (
		<span className="spotify-status" title={`Connected${countdown}`}>
			<Dot tone={status.reauth_due ? "warn" : "ok"} />
			Spotify
			{soon && <span className="muted">{countdown}</span>}
			{status.reauth_due && (
				<>
					{" · "}
					<a href={LOGIN_URL}>Reconnect</a>
				</>
			)}
		</span>
	);
}
