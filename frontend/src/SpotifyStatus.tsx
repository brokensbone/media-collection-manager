import { useEffect, useState } from "react";

type Status = {
	connected: boolean;
	authorized_at: string | null;
	reauth_in_days: number | null;
	reauth_due: boolean;
};

const LOGIN_URL = "/auth/spotify/login";

export function SpotifyStatus() {
	const [status, setStatus] = useState<Status | null>(null);

	useEffect(() => {
		fetch("/auth/spotify/status")
			.then((r) => r.json())
			.then(setStatus)
			.catch(() => setStatus(null));
	}, []);

	if (!status) return <span>Spotify: …</span>;

	if (!status.connected) {
		return <a href={LOGIN_URL}>Connect Spotify</a>;
	}

	const countdown =
		status.reauth_in_days !== null
			? ` · reauth in ${status.reauth_in_days}d`
			: "";

	return (
		<span title={`Connected${countdown}`}>
			Spotify
			{status.reauth_due && (
				<>
					{" · "}
					<a href={LOGIN_URL}>Reconnect</a>
				</>
			)}
		</span>
	);
}
