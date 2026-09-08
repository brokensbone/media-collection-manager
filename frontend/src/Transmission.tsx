import { useCallback, useEffect, useState } from "react";

type Torrent = {
	id: number;
	name: string;
	media_kind: "music" | "tv" | "film" | "workspace" | "unknown";
	import_target: "beets" | "tv" | "film" | "workspace" | "review";
	classification_detail: string | null;
	destination_path: string | null;
	state: string;
	matched: string | null;
	has_audio: boolean | null;
};

type Check = { ok: boolean; detail: string };
type TestReport = { api: Check; ssh: Check };

export function Transmission() {
	const [torrents, setTorrents] = useState<Torrent[] | null>(null);
	const [report, setReport] = useState<TestReport | null>(null);
	const [testing, setTesting] = useState(false);
	const [torrentFiles, setTorrentFiles] = useState<File[]>([]);
	const [uploading, setUploading] = useState(false);
	const [uploadStatus, setUploadStatus] = useState<string | null>(null);

	useEffect(() => {
		fetch("/transmission/torrents")
			.then((r) => r.json())
			.then(setTorrents)
			.catch(() => setTorrents([]));
	}, []);

	const runTest = useCallback(() => {
		setTesting(true);
		setReport(null);
		fetch("/transmission/test", { method: "POST" })
			.then((r) => r.json())
			.then(setReport)
			.catch(() => setReport(null))
			.finally(() => setTesting(false));
	}, []);

	const uploadTorrent = useCallback(async () => {
		if (torrentFiles.length === 0) return;
		setUploading(true);
		setUploadStatus(null);
		const form = new FormData();
		for (const torrentFile of torrentFiles) form.append("files", torrentFile);
		try {
			const response = await fetch("/transmission/torrents", {
				method: "POST",
				body: form,
			});
			const body = (await response.json()) as { detail?: string };
			if (!response.ok) throw new Error(body.detail ?? "Upload failed.");
			setUploadStatus(body.detail ?? "Torrents added to Transmission.");
			setTorrentFiles([]);
		} catch (error) {
			setUploadStatus(
				error instanceof Error ? error.message : "Upload failed.",
			);
		} finally {
			setUploading(false);
		}
	}, [torrentFiles]);

	return (
		<>
			<section>
				<h2>Connection</h2>
				<p className="muted">
					Check the app can reach Transmission's RPC API and SSH to the seedbox.
				</p>
				<button type="button" onClick={runTest} disabled={testing}>
					{testing ? "Testing…" : "Test connection"}
				</button>
				{report && (
					<div className="checks">
						<CheckLine label="API" check={report.api} />
						<CheckLine label="SSH" check={report.ssh} />
					</div>
				)}
			</section>

			<section>
				<h2>Add torrent</h2>
				<p className="muted">
					Upload one or more .torrent files to start their downloads in
					Transmission.
				</p>
				<div className="torrent-upload">
					<input
						aria-label="Upload a .torrent file"
						type="file"
						accept=".torrent,application/x-bittorrent"
						multiple
						onChange={(event) =>
							setTorrentFiles(Array.from(event.target.files ?? []))
						}
					/>
					<button
						type="button"
						onClick={uploadTorrent}
						disabled={torrentFiles.length === 0 || uploading}
					>
						{uploading ? "Adding…" : "Start download"}
					</button>
				</div>
				{uploadStatus && <p className="upload-status">{uploadStatus}</p>}
			</section>

			<section>
				<h2>Torrents seen</h2>
				{!torrents ? (
					<p>Loading…</p>
				) : torrents.length === 0 ? (
					<p className="muted">
						No torrents seen yet — connect Transmission and the poller will fill
						this in.
					</p>
				) : (
					<table>
						<colgroup>
							<col />
							<col className="c-kind" />
							<col />
							<col className="c-state" />
							<col className="c-matched" />
						</colgroup>
						<thead>
							<tr>
								<th>name</th>
								<th>kind</th>
								<th>destination</th>
								<th>state</th>
								<th>matched</th>
							</tr>
						</thead>
						<tbody>
							{torrents.map((t) => (
								<tr key={t.id}>
									<td>
										<div>{t.name}</div>
										{t.classification_detail && (
											<div className="muted">{t.classification_detail}</div>
										)}
									</td>
									<td className="muted">{kind(t)}</td>
									<td className="muted">{t.destination_path ?? "—"}</td>
									<td className="muted">{t.state}</td>
									<td>{t.matched ?? <span className="muted">—</span>}</td>
								</tr>
							))}
						</tbody>
					</table>
				)}
			</section>
		</>
	);
}

function kind(torrent: Torrent): string {
	if (torrent.media_kind === "unknown" && torrent.has_audio === false)
		return "non-media";
	if (torrent.media_kind === "music") return "music";
	if (torrent.media_kind === "tv") return "tv";
	if (torrent.media_kind === "film") return "film";
	if (torrent.media_kind === "workspace") return "workspace";
	return "unknown";
}

function CheckLine({ label, check }: { label: string; check: Check }) {
	return (
		<div>
			<strong>{label}:</strong> {check.ok ? "✓ ok" : "✗ failed"}{" "}
			<span className="muted">{check.detail}</span>
		</div>
	);
}
