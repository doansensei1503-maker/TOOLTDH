"""P17 dashboard HTTP server.

A small standard-library HTTP server that exposes the real backend to the
dashboard. The server binds to the loopback interface only, so the tool is
never reachable from another machine.

Every endpoint calls `dashboard_service`, which in turn calls the modules
that already exist. Nothing is simulated.
"""

from __future__ import annotations

import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

import dashboard_service as service

WEB_ROOT = Path(__file__).with_name("web")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8777


class ApiError(Exception):
    """Raised when an endpoint cannot serve the request."""


def _route(method: str, path: str) -> Callable[..., Any] | None:
    """Return the handler for a route, or None when the route is unknown."""
    routes: dict[tuple[str, str], Callable[..., Any]] = {
        ("GET", "/api/overview"): service.overview,
        ("GET", "/api/discovery/run"): lambda topic="": service.run_discovery_job(topic).to_dict(),
        ("POST", "/api/discovery/search"): service.discovery_search,
        ("POST", "/api/discovery/stop"): service.discovery_stop,
        ("POST", "/api/discovery/approve"): service.discovery_approve,
        ("POST", "/api/discovery/reject"): service.discovery_reject,
        ("POST", "/api/discovery/confirm-content"): service.discovery_confirm_content,
        ("POST", "/api/discovery/dismiss-content"): service.discovery_dismiss_content,
        ("GET", "/api/discovery/last"): service.discovery_last,
        ("GET", "/api/discovery/detail"): service.discovery_detail,
        ("POST", "/api/discovery/reanalyze"): service.reanalyze_with_media,
        ("GET", "/api/reviews"): service.review_list,
        ("POST", "/api/reviews/select"): service.select_review_candidate,
        ("POST", "/api/reviews/caption"): service.update_review_caption,
        ("POST", "/api/caption/generate"): service.generate_caption,
        ("GET", "/api/tasks"): service.tasks_list,
        ("GET", "/api/tasks/detail"): service.task_detail,
        ("POST", "/api/tasks/run"): service.run_task_job,
        ("POST", "/api/tasks/resume"): service.resume_task_job,
        ("GET", "/api/jobs"): service.jobs_list,
        ("GET", "/api/approvals"): service.approvals_list,
        ("POST", "/api/approvals/download"): service.approve_task,
        ("POST", "/api/approvals/publish"): service.publish_approved,
        ("GET", "/api/library"): service.library_list,
        ("GET", "/api/history"): service.history_list,
        ("GET", "/api/logs"): service.logs_list,
        ("GET", "/api/settings"): service.settings_get,
        ("POST", "/api/settings"): service.settings_update,
        ("POST", "/api/emergency-stop"): service.emergency_stop,
        ("POST", "/api/emergency-start"): service.emergency_start,
        ("GET", "/api/search-profiles"): service.search_profiles_list,
        ("POST", "/api/search-profiles"): service.search_profile_save,
        ("POST", "/api/search-profiles/delete"): service.search_profile_delete,
        ("GET", "/api/notifications"): service.notifications_list,
        ("POST", "/api/notifications/read"): service.notifications_read,
        ("GET", "/api/analytics"): service.analytics,
        ("GET", "/api/permissions"): service.permissions_list,
        ("GET", "/api/scheduler"): service.scheduler_status,
        ("POST", "/api/scheduler/start"): service.scheduler_start,
        ("POST", "/api/scheduler/stop"): service.scheduler_stop,
        ("GET", "/api/queue"): service.queue_list,
        ("POST", "/api/queue/enqueue"): service.queue_enqueue,
        ("POST", "/api/editor/inspect"): service.inspect_media,
    }
    handler = routes.get((method, path))
    return handler


def _call_handler(handler: Callable[..., Any], body: dict[str, Any]) -> Any:
    """Call a handler with the request body.

    A handler that takes a single mapping receives the whole body. A handler
    that takes named fields receives them as keyword arguments.
    """
    import inspect

    signature = inspect.signature(handler)
    parameters = list(signature.parameters.values())
    if len(parameters) == 1:
        annotation = parameters[0].annotation
        if annotation in {"dict[str, Any]", dict} or parameters[0].name in {
            "payload", "body", "profile", "settings",
        }:
            return handler(body)
    return handler(**body)


class DashboardHandler(BaseHTTPRequestHandler):
    """Serve the dashboard and the JSON API."""

    server_version = "TOOLTDH/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        """Keep the server output quiet so the console stays readable."""
        return

    # ------------------------------------------------------------- helpers

    def _send_json(self, payload: Any, status: int = 200) -> None:
        """Send a JSON response."""
        body = json.dumps(payload, indent=2, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict[str, Any]:
        """Read the JSON request body."""
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError(f"The request body was not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ApiError("The request body must be a JSON object.")
        return payload

    def _serve_static(self, path: str) -> None:
        """Serve a file from the web directory."""
        relative = path.lstrip("/") or "index.html"
        if relative.endswith("/"):
            relative += "index.html"
        target = (WEB_ROOT / relative).resolve()
        try:
            root = WEB_ROOT.resolve()
        except OSError:
            self._send_json({"error": "The web directory is not available."}, 500)
            return
        if root != target and root not in target.parents:
            self._send_json({"error": "Rejected: the path is outside the web root."}, 403)
            return
        if not target.exists() or not target.is_file():
            self._send_json({"error": f"Not found: {relative}"}, 404)
            return
        content_type, _ = mimetypes.guess_type(str(target))
        if content_type is None:
            content_type = "application/octet-stream"
        if content_type.startswith("text/") or content_type in {
            "application/javascript",
            "application/json",
        }:
            content_type += "; charset=utf-8"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_media(self, path: str) -> None:
        """Stream a local video file to the dashboard player.

        The file has to be one of the preview files that the service found,
        so the request can never read an arbitrary path. The response
        supports a byte range, because a browser player asks for the
        ranges of a video while it plays it.
        """
        query = parse_qs(urlparse(path).query)
        source_url = query.get("source_url", [""])[0]
        task_id = query.get("task_id", [""])[0]
        try:
            media = service.preview_media(source_url=source_url, task_id=task_id)
        except service.ServiceError as exc:
            self._send_json({"error": str(exc)}, 404)
            return

        target = Path(str(media["path"]))
        try:
            size = target.stat().st_size
        except OSError as exc:
            self._send_json({"error": f"The media file is not readable: {exc}"}, 404)
            return

        content_type, _ = mimetypes.guess_type(str(target))
        if content_type is None:
            content_type = "video/mp4"

        start = 0
        end = size - 1
        partial = False
        range_header = self.headers.get("Range", "")
        if range_header.startswith("bytes="):
            spec = range_header.split("=", 1)[1].split(",")[0].strip()
            try:
                if spec.startswith("-"):
                    length = int(spec[1:])
                    start = max(0, size - length)
                else:
                    bounds = spec.split("-", 1)
                    start = int(bounds[0])
                    if len(bounds) > 1 and bounds[1].strip():
                        end = min(int(bounds[1]), size - 1)
            except ValueError:
                start = 0
            else:
                partial = True

        if start >= size or start < 0:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return

        length = end - start + 1
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with target.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(65536, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    # The browser closed the player; nothing to do.
                    break
                remaining -= len(chunk)

    def _serve_frames(self, path: str) -> None:
        """Send the real frames that were read from a candidate.

        The frames are the picture of the video that the analysis judged.
        They are sent so the dashboard can show what the AI saw, even when
        the video itself was not downloaded. Nothing is downloaded here.
        """
        query = parse_qs(urlparse(path).query)
        source_url = query.get("source_url", [""])[0]
        try:
            frame = service.preview_frames(source_url=source_url)
        except service.ServiceError as exc:
            self._send_json({"error": str(exc)}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(frame)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(frame)
        except (BrokenPipeError, ConnectionResetError):
            return

    # ------------------------------------------------------------- verbs

    def do_GET(self) -> None:  # noqa: N802 - the name is required
        """Handle a GET request."""
        parsed = urlparse(self.path)
        path = parsed.path
        if not path.startswith("/api/"):
            self._serve_static(path)
            return
        if path == "/api/media/preview":
            self._serve_media(self.path)
            return
        if path == "/api/media/frames":
            self._serve_frames(self.path)
            return
        route = _route("GET", path)
        if route is None:
            self._send_json({"error": f"Unknown endpoint: {path}"}, 404)
            return
        handler = route
        query = parse_qs(parsed.query)
        try:
            kwargs: dict[str, Any] = {}
            if "topic" in query:
                kwargs["topic"] = query["topic"][0]
            if "task_id" in query:
                kwargs["task_id"] = query["task_id"][0]
            if "source_url" in query:
                kwargs["source_url"] = query["source_url"][0]
            if "limit" in query:
                kwargs["limit"] = int(query["limit"][0])
            payload = handler(**kwargs)
        except ApiError as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        except service.ServiceError as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        except TypeError as exc:
            self._send_json({"error": f"Bad request: {exc}"}, 400)
            return
        except Exception as exc:  # noqa: BLE001 - the reason is reported
            self._send_json({"error": f"{type(exc).__name__}: {exc}"}, 500)
            return
        self._send_json(payload)

    def do_POST(self) -> None:  # noqa: N802 - the name is required
        """Handle a POST request."""
        parsed = urlparse(self.path)
        path = parsed.path
        route = _route("POST", path)
        if route is None:
            self._send_json({"error": f"Unknown endpoint: {path}"}, 404)
            return
        handler = route
        try:
            body = self._read_body()
        except ApiError as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        try:
            payload = _call_handler(handler, body)
        except service.ServiceError as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        except TypeError as exc:
            self._send_json({"error": f"Bad request: {exc}"}, 400)
            return
        except Exception as exc:  # noqa: BLE001 - the reason is reported
            self._send_json({"error": f"{type(exc).__name__}: {exc}"}, 500)
            return
        self._send_json(payload)


def serve(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    open_browser: bool = False,
) -> ThreadingHTTPServer:
    """Start the dashboard server and return it."""
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, name="toolt-dh-dashboard", daemon=True)
    thread.start()
    url = f"http://{host}:{port}/"
    print(f"TOOLTDH dashboard is running at {url}")
    print("Press Ctrl+C to stop it.")

    # The background scheduler is started with the server so a scheduled pass
    # does not depend on the dashboard page staying open.
    try:
        if service.scheduler_status().get("enabled"):
            service.scheduler_start()
            print("The background scheduler was started.")
    except Exception as exc:  # noqa: BLE001 - the reason is printed
        print(f"The background scheduler was not started: {exc}")

    if open_browser:
        import webbrowser

        webbrowser.open(url)
    return server


def main() -> None:
    """Run the dashboard server until it is interrupted."""
    import argparse

    parser = argparse.ArgumentParser(description="TOOLTDH dashboard server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="interface to bind to")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="port to listen on")
    parser.add_argument(
        "--open",
        action="store_true",
        help="open the dashboard in the default browser",
    )
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print(
            "REJECTED: the dashboard only binds to the loopback interface so the "
            f"tool is not reachable from the network. Got host={args.host!r}."
        )
        raise SystemExit(2)

    server = serve(args.host, args.port, open_browser=args.open)
    try:
        while True:
            threading.Event().wait(1)
    except KeyboardInterrupt:
        print("\nStopping the dashboard server.")
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
