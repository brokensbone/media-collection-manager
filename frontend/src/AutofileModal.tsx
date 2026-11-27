import { useEffect, useRef, useState } from "react";
import { Modal } from "./Modal";

export type AutofileRun = {
	id: number;
	status: string;
	model: string;
	error: string | null;
	evidence: {
		notice?: string;
		sources?: { url: string; description: string; tags: string[] }[];
	};
	result: {
		destination?: string;
		destination_count?: number;
		capacity?: number;
		reason?: string;
		needs_review?: boolean;
		steps: {
			node_id: number;
			node: string;
			choice: string;
			probability: number;
			alternatives: { choice: string; probability: number }[];
		}[];
	};
};

async function post(url: string, body?: unknown): Promise<AutofileRun> {
	const response = await fetch(url, {
		method: "POST",
		headers: { "content-type": "application/json" },
		...(body ? { body: JSON.stringify(body) } : {}),
	});
	const data = await response.json();
	if (!response.ok)
		throw new Error(
			data.detail ?? "Autofile could not complete. Please try again.",
		);
	return data as AutofileRun;
}

const percentage = (n: number) => `${Math.round(n * 100)}%`;
const choiceName = (name: string) => name.replace(/ \[\d+\]$/, "");

export function AutofileModal({
	album,
	onClose,
	onAccepted,
}: {
	album: { beets_id: string; artist: string; title: string };
	onClose: () => void;
	onAccepted: () => void;
}) {
	const [run, setRun] = useState<AutofileRun | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [busy, setBusy] = useState(false);
	// Reuse the request when React StrictMode replays the effect.
	const pending = useRef<Promise<AutofileRun> | null>(null);
	useEffect(() => {
		let active = true;
		pending.current ??= post("/crates/autofile", { beets_id: album.beets_id });
		pending.current.then(
			(value) => {
				if (active) setRun(value);
			},
			(err: Error) => {
				if (active) setError(err.message);
			},
		);
		return () => {
			active = false;
		};
	}, [album.beets_id]);

	async function resolve(action: "accept" | "dismiss") {
		if (busy) return;
		if (!run) {
			onClose();
			return;
		}
		setBusy(true);
		setError(null);
		try {
			await post(`/crates/autofile/${run.id}/${action}`);
			if (action === "accept") onAccepted();
			onClose();
		} catch (err) {
			setError(
				err instanceof Error
					? err.message
					: "That didn’t work. Please try again.",
			);
		} finally {
			setBusy(false);
		}
	}

	return (
		<Modal
			title="Autofile"
			className="autofile-modal"
			footer={
				<div className="autofile-actions">
					{run?.status === "suggested" && run.result.destination && (
						<button
							type="button"
							disabled={busy}
							onClick={() => void resolve("accept")}
						>
							File in {run.result.destination.split(" / ").at(-1)}
						</button>
					)}
					<button
						type="button"
						className="btn-quiet"
						disabled={busy}
						onClick={() => void resolve("dismiss")}
					>
						{run ? "Dismiss" : "Close"}
					</button>
				</div>
			}
			onClose={() => {
				if (!busy) void resolve("dismiss");
			}}
		>
			<div className="autofile-scroll">
				<p>
					<strong>{album.artist}</strong> — {album.title}
				</p>
				{!run && !error && <p role="status">Finding a crate…</p>}
				{error && <p role="alert">{error}</p>}
				{run && (
					<>
						{run.error && <p role="alert">{run.error}</p>}
						{run.result.destination && (
							<div className="autofile-destination">
								<span className="cell-meta">Suggested crate</span>
								<strong>{run.result.destination.split(" / ").at(-1)}</strong>
								<span className="cell-meta">{run.result.destination}</span>
							</div>
						)}
						{run.status === "review" && !run.result.destination ? (
							<p>
								<strong>No destination suggested.</strong> The album will stay
								in its current crate.
							</p>
						) : run.result.reason ? (
							<p>{run.result.reason}</p>
						) : null}
						{run.status === "suggested" && run.result.needs_review && (
							<p>
								Low-confidence suggestion. Check the alternatives below, then
								file in the suggested crate or dismiss.
							</p>
						)}
						{run.result.steps.length > 0 && (
							<ol className="autofile-steps">
								{run.result.steps.map((step) => (
									<li key={step.node_id}>
										<div>
											<strong>{choiceName(step.choice)}</strong>{" "}
											<span className="cell-meta">
												{percentage(step.probability)}
											</span>
										</div>
										<details>
											<summary>Show alternatives</summary>
											<ul>
												{step.alternatives.map((option) => (
													<li key={option.choice}>
														{choiceName(option.choice)}:{" "}
														{percentage(option.probability)}
													</li>
												))}
											</ul>
										</details>
									</li>
								))}
							</ol>
						)}
						{run.result.destination_count != null && (
							<p>
								Destination: {run.result.destination_count} albums · limit{" "}
								{run.result.capacity}
							</p>
						)}
						{run.evidence.notice && (
							<p className="cell-meta">{run.evidence.notice}</p>
						)}
						{(run.evidence.sources ?? []).map((source) => (
							<details key={source.url}>
								<summary>Album description</summary>
								<p>{source.description}</p>
								{source.tags.length > 0 && <p>{source.tags.join(" · ")}</p>}
								<a href={source.url} target="_blank" rel="noreferrer">
									Source
								</a>
							</details>
						))}
						<p className="cell-meta">
							Saved result #{run.id} · {run.model}
						</p>
					</>
				)}
			</div>
		</Modal>
	);
}
