import { type ReactNode, useEffect, useId, useRef } from "react";
import { CloseIcon } from "./icons";

// Native modal dialog: showModal() traps focus and gives Esc and the backdrop for free. Focus goes
// to the first `[data-autofocus]` descendant, and back to the opener on close.
export function Modal({
	title,
	onClose,
	children,
}: {
	title: string;
	onClose: () => void;
	children: ReactNode;
}) {
	const ref = useRef<HTMLDialogElement>(null);
	const titleId = useId();
	// Captured on first render: by the time an effect re-runs (StrictMode), focus is already inside.
	const opener = useRef(
		document.activeElement instanceof HTMLElement
			? document.activeElement
			: null,
	);

	useEffect(() => {
		const dialog = ref.current;
		if (!dialog) return;
		// jsdom has no showModal; the open attribute still gives the dialog its role.
		if (typeof dialog.showModal === "function") {
			if (!dialog.open) dialog.showModal();
		} else dialog.setAttribute("open", "");
		dialog.querySelector<HTMLElement>("[data-autofocus]")?.focus();
		return () => {
			const el = opener.current;
			if (el?.isConnected) el.focus();
		};
	}, []);

	return (
		<dialog
			ref={ref}
			className="modal"
			aria-labelledby={titleId}
			onCancel={(e) => {
				// Let React unmount the dialog rather than the browser closing it under us.
				e.preventDefault();
				onClose();
			}}
			onClick={(e) => {
				if (e.target === e.currentTarget) onClose();
			}}
			onKeyDown={(e) => {
				if (e.key === "Escape" && typeof ref.current?.showModal !== "function")
					onClose();
			}}
		>
			<div className="modal-body">
				<div className="modal-head">
					<h2 id={titleId}>{title}</h2>
					<button
						type="button"
						className="btn-quiet modal-close"
						aria-label="Close"
						title="Close"
						onClick={onClose}
					>
						<CloseIcon />
					</button>
				</div>
				{children}
			</div>
		</dialog>
	);
}
