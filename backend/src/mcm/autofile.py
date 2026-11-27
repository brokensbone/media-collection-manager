"""Reusable autofile entry point for manual review and future acquisition hooks."""

import logging
from dataclasses import asdict
from typing import Any, Protocol

from .adapters.autofile_repo import AutofileRepo, RunView
from .adapters.box_repo import BoxRepo
from .crates import CrateError
from .domain.autofile import PROMPT_VERSION, build_request, interpret
from .library_assist import LibraryAssistService
from .ports.events import EventSink

log = logging.getLogger(__name__)


class CrateJudge(Protocol):
    def evaluate(self, request: dict[str, Any]) -> dict[str, Any]: ...


class AlbumDescriptions(Protocol):
    def lookup(self, album: dict[str, Any]) -> dict[str, Any]: ...


class AutofileService:
    def __init__(
        self,
        *,
        repo: AutofileRepo,
        boxes: BoxRepo,
        library: LibraryAssistService,
        judge: CrateJudge,
        descriptions: AlbumDescriptions,
        events: EventSink,
        model: str = "jev-1.14.0",
        cap: int = 50,
    ) -> None:
        self.repo = repo
        self._boxes = boxes
        self._library = library
        self._judge = judge
        self._descriptions = descriptions
        self._events = events
        self._model = model
        self._cap = cap

    def suggest(self, beets_id: str, *, trigger: str = "manual") -> RunView:
        """Persist a decision without moving anything. Safe for future worker callers too."""
        root = self._boxes.root()
        boxes = self._boxes.list_boxes()
        records = [asdict(r) for r in self._library.owned_library()]
        album = next((r for r in records if r["beets_id"] == beets_id), None)
        if album is None:
            raise CrateError("No such album in the owned library")
        by_id = {b.id: b for b in boxes}
        membership = self._boxes.membership()
        source = membership.get(beets_id, root.id)
        if source not in by_id:
            source = root.id
        tree: list[dict[str, Any]] = []
        for b in boxes:
            names = [b.name]
            parent = b.parent_id
            while parent is not None:
                names.append(by_id[parent].name)
                parent = by_id[parent].parent_id
            tree.append(
                {
                    "id": b.id,
                    "name": b.name,
                    "parent_id": b.parent_id,
                    "path": " / ".join(reversed(names)),
                    "children": [asdict(c) for c in boxes if c.parent_id == b.id],
                    "records": [
                        r for r in records if membership.get(r["beets_id"], root.id) == b.id
                    ],
                }
            )
        run = self.repo.start(
            beets_id=beets_id,
            trigger=trigger,
            source_box_id=source,
            prompt_version=PROMPT_VERSION,
            model=self._model,
            album=album,
        )
        self._emit(run, "autofile_started", "Autofile started")
        evidence: dict[str, Any] = {}
        request: dict[str, Any] = {}
        response: dict[str, Any] = {}
        result: dict[str, Any] = {"tree": [asdict(b) for b in boxes], "steps": []}
        try:
            evidence = self._descriptions.lookup(album)
            request = build_request(album, tree, evidence, self._model)
            if not request["questions"]:
                result["reason"] = "Create a sub-crate before asking Autofile for a destination."
                status = "review"
                destination = None
            else:
                self.repo.finish(
                    run.id, completed=False, evidence=evidence, request=request, result=result
                )
                response = self._judge.evaluate(request)
                steps, destination = interpret(request, response, tree)
                result["steps"] = steps
                status = "suggested"
                if destination is None:
                    result["reason"] = "No suitable child crate was found along this route."
                    status = "review"
                else:
                    target = next(b for b in tree if b["id"] == destination)
                    result["destination"] = target["path"]
                    result["destination_count"] = len(target["records"])
                    result["capacity"] = self._cap
                    if destination == source:
                        result["reason"] = "This album is already in the suggested crate."
                        status = "review"
                    elif len(target["records"]) >= self._cap:
                        result["reason"] = "The suggested crate is full. Split it before filing."
                        status = "review"
                # No threshold is calibrated yet: show uncertainty for human acceptance.
                result["needs_review"] = any(s["probability"] < 0.8 for s in steps)
            run = self.repo.finish(
                run.id,
                status=status,
                destination_box_id=destination,
                evidence=evidence,
                request=request,
                response=response,
                result=result,
                model=str(response.get("model", self._model)),
            )
            self._emit(run, "autofile_suggested", "Autofile suggestion saved")
            return run
        except Exception as exc:  # provider failures must also leave a retrievable audit result
            log.warning("Autofile run %s failed (%s)", run.id, type(exc).__name__)
            run = self.repo.finish(
                run.id,
                status="failed",
                evidence=evidence,
                request=request,
                response=response,
                result=result,
                error="Autofile could not complete. Check Jev configuration or retry.",
            )
            self._emit(run, "error", "Autofile failed")
            return run

    def accept(self, run_id: int) -> RunView:
        run, changed = self.repo.accept(run_id, self._cap)
        if changed:
            self._emit(run, "autofile_accepted", f"Filed in {run.result['destination']}")
        return run

    def dismiss(self, run_id: int) -> RunView:
        run, changed = self.repo.dismiss(run_id)
        if changed:
            self._emit(run, "autofile_dismissed", "Autofile suggestion dismissed")
        return run

    def _emit(self, run: RunView, kind: str, message: str) -> None:
        self._events.emit(
            job="autofile",
            type=kind,
            message=f"{message}: {run.album['artist']} — {run.album['title']} (run #{run.id})",
            album_id=run.album.get("album_id"),
        )
