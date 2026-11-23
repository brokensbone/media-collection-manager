import "./pages-tools.css";
import { type ReactNode, useCallback, useEffect, useState } from "react";
import { fetchJson } from "./api";
import { matchesQuery } from "./filter";
import { useQuery } from "./hashState";
import {
	EmptyState,
	ErrorState,
	FilterBox,
	GroupHead,
	IMPORT_STATE_TONE,
	Loading,
	NoMatches,
	PageHeader,
	StatusBadge,
	type Tone,
	useAnnounceCount,
} from "./ui";

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
type UploadResult = {
	position: number;
	filename: string;
	name: string;
	already_present: boolean;
};

const STATE_LABEL: Record<string, string> = {
	importing: "importing…",
	imported: "imported ✓",
};

function stateTone(state: string): Tone {
	return (IMPORT_STATE_TONE as Record<string, Tone>)[state] ?? "muted";
}

export function Transmission() {
	const query = useQuery();
	const [torrents, setTorrents] = useState<Torrent[] | null>(null);
	const [loadFailed, setLoadFailed] = useState(false);
	const [report, setReport] = useState<TestReport | null>(null);
	const [testing, setTesting] = useState(false);
	const [torrentFiles, setTorrentFiles] = useState<File[]>([]);
	const [uploading, setUploading] = useState(false);
	const [uploadStatus, setUploadStatus] = useState<{
		ok: boolean;
		text: string;
	} | null>(null);
	const [uploadResults, setUploadResults] = useState<UploadResult[]>([]);

	const loadTorrents = useCallback(() => {
		setLoadFailed(false);
		fetchJson<Torrent[]>("/transmission/torrents")
			.then(setTorrents)
			.catch(() => setLoadFailed(true));
	}, []);
	useEffect(loadTorrents, [loadTorrents]);

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
		setUploadResults([]);
		const form = new FormData();
		for (const torrentFile of torrentFiles) form.append("files", torrentFile);
		try {
			const response = await fetch("/transmission/torrents", {
				method: "POST",
				body: form,
			});
			const body = (await response.json()) as {
				detail?: string;
				results?: UploadResult[];
			};
			if (!response.ok) throw new Error(body.detail ?? "Upload failed.");
			setUploadStatus({
				ok: true,
				text: body.detail ?? "Torrents added to Transmission.",
			});
			setUploadResults(
				(body.results ?? []).filter((result) => result.already_present),
			);
			setTorrentFiles([]);
		} catch (error) {
			setUploadStatus({
				ok: false,
				text: error instanceof Error ? error.message : "Upload failed.",
			});
		} finally {
			setUploading(false);
		}
	}, [torrentFiles]);

	const shown = (torrents ?? []).filter((t) =>
		matchesQuery(`${t.name} ${t.matched ?? ""}`, query),
	);
	useAnnounceCount(
		shown.length,
		torrents?.length ?? 0,
		!!query && torrents !== null,
	);

	let list: ReactNode;
	if (torrents === null)
		list = loadFailed ? (
			<ErrorState what="torrents" onRetry={loadTorrents} />
		) : (
			<Loading />
		);
	else if (torrents.length === 0)
		list = (
			<EmptyState
				title="No torrents seen yet"
				hint="Connect Transmission and the poller will fill this in."
			/>
		);
	else if (shown.length === 0)
		list = <NoMatches query={query} what="torrents" />;
	else
		list = (
			<table className="rows tall no-cover torrents">
				<colgroup>
					<col />
					<col className="c-kind" />
					<col className="c-state" />
					<col className="c-matched" />
				</colgroup>
				<thead>
					<tr>
						<th scope="col">Name</th>
						<th scope="col">Kind</th>
						<th scope="col">State</th>
						<th scope="col">Matched</th>
					</tr>
				</thead>
				<tbody>
					{shown.map((t) => (
						<tr key={t.id}>
							<td className="cell-primary">
								{t.name}
								{(t.classification_detail || t.destination_path) && (
									<span className="row-meta">
										{t.classification_detail}
										{t.classification_detail && t.destination_path && " · "}
										{t.destination_path && (
											<span className="mono">{t.destination_path}</span>
										)}
									</span>
								)}
							</td>
							<td className="cell-kind muted">{kind(t)}</td>
							<td className="cell-state">
								<StatusBadge
									tone={stateTone(t.state)}
									pulse={t.state === "importing"}
								>
									{STATE_LABEL[t.state] ?? t.state}
								</StatusBadge>
							</td>
							<td className="cell-matched">
								{t.matched ?? <span className="muted">—</span>}
							</td>
						</tr>
					))}
				</tbody>
			</table>
		);

	return (
		<>
			<PageHeader
				title="Transmission"
				filter={<FilterBox placeholder="Filter name or match" />}
			/>
			<div className="tools-cards">
				<section className="card">
					<h2>Connection</h2>
					<p className="card-hint">
						Check the app can reach Transmission's RPC API and SSH to the
						seedbox.
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

				<section className="card">
					<h2>Add torrent</h2>
					<p className="card-hint">
						Upload one or more .torrent files to start their downloads in
						Transmission.
					</p>
					<div className="torrent-upload">
						<input
							aria-label="Upload a .torrent file"
							type="file"
							multiple
							onChange={(event) =>
								setTorrentFiles(Array.from(event.target.files ?? []))
							}
						/>
						<button
							type="button"
							className="btn-primary"
							onClick={uploadTorrent}
							disabled={torrentFiles.length === 0 || uploading}
						>
							{uploading ? "Adding…" : "Start download"}
						</button>
					</div>
					{uploadStatus && (
						<p
							className={`upload-status ${uploadStatus.ok ? "tone-ok" : "tone-danger"}`}
						>
							{uploadStatus.text}
						</p>
					)}
					{uploadResults.length > 0 && (
						<>
							<p className="upload-note">
								Already in Transmission — check for import:
							</p>
							<ul className="upload-results">
								{uploadResults.map((result) => (
									<li key={result.position}>
										{result.name || result.filename}
									</li>
								))}
							</ul>
						</>
					)}
				</section>
			</div>

			<section className="torrents-section">
				<GroupHead title="Torrents seen" count={torrents?.length}>
					{query && torrents && (
						<span className="muted">
							{shown.length} of {torrents.length} shown
						</span>
					)}
				</GroupHead>
				{list}
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
		<div className="check-line">
			<strong>{label}</strong>
			<StatusBadge tone={check.ok ? "ok" : "danger"}>
				{check.ok ? "✓ ok" : "✗ failed"}
			</StatusBadge>
			<span className="muted">{check.detail}</span>
		</div>
	);
}
