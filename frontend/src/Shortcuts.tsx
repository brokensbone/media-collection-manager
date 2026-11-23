import { useEffect, useRef, useState } from "react";
import { setHashPath } from "./hashState";
import { shouldIgnoreKey } from "./keys";
import { Modal } from "./Modal";
import { Kbd } from "./ui";

// g then a letter jumps to a view.
export const GO_KEYS: [key: string, path: string, label: string][] = [
	["h", "all", "Overview"],
	["r", "releases", "Releases"],
	["d", "decide", "Decide"],
	["a", "acquire", "Acquire"],
	["i", "import", "Import"],
	["t", "tasks", "Tasks"],
	["o", "owned", "Owned"],
	["c", "crates", "Crates"],
	["v", "activity", "Activity"],
];

const LIST_KEYS: [where: string, keys: [string, string][]][] = [
	["Every list with a cursor", [["j / k", "move down / up"]]],
	[
		"Releases",
		[
			["s", "save"],
			["w", "want"],
			["d", "dismiss"],
		],
	],
	[
		"Decide",
		[
			["y", "keep"],
			["x", "drop"],
			["s", "snooze"],
		],
	],
	[
		"Acquire",
		[
			["b", "open Bandcamp"],
			["m", "mark owned…"],
		],
	],
	["Import", [["i", "import"]]],
	[
		"Tasks",
		[
			["r", "retry"],
			["l", "show or hide the log"],
		],
	],
	["Crates", [["space", "select or unselect"]]],
];

// Global view shortcuts and the "?" overview. Registered in the capture phase so the letter after
// "g" is swallowed before a list's own shortcut (d, s, …) can see it.
export function Shortcuts() {
	const [open, setOpen] = useState(false);
	const pendingG = useRef(0);

	useEffect(() => {
		function onKey(e: KeyboardEvent) {
			if (shouldIgnoreKey(e)) return;
			if (pendingG.current && Date.now() - pendingG.current < 1500) {
				pendingG.current = 0;
				const go = GO_KEYS.find(([k]) => k === e.key.toLowerCase());
				if (go) {
					e.preventDefault();
					setHashPath(go[1]);
				}
				return;
			}
			if (e.key === "g") {
				pendingG.current = Date.now();
				e.preventDefault();
			} else if (e.key === "?") {
				e.preventDefault();
				setOpen(true);
			}
		}
		window.addEventListener("keydown", onKey, true);
		return () => window.removeEventListener("keydown", onKey, true);
	}, []);

	if (!open) return null;
	const sections: [string, [string, string][]][] = [
		[
			"Anywhere",
			[
				["/", "filter the list"],
				["?", "this overview"],
				...GO_KEYS.map(([k, , label]): [string, string] => [`g ${k}`, label]),
			],
		],
		...LIST_KEYS,
	];
	return (
		<Modal title="Keyboard shortcuts" onClose={() => setOpen(false)}>
			<div className="shortcuts">
				{sections.map(([where, keys]) => (
					<section key={where}>
						<h3>{where}</h3>
						<dl>
							{keys.map(([k, label]) => (
								<div key={k} className="shortcut-row">
									<dt>
										{k === "j / k" || k === "space" ? (
											<Kbd>{k}</Kbd>
										) : (
											k.split(" ").map((part) => <Kbd key={part}>{part}</Kbd>)
										)}
									</dt>
									<dd>{label}</dd>
								</div>
							))}
						</dl>
					</section>
				))}
			</div>
		</Modal>
	);
}
