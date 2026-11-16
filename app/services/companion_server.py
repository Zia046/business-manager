"""The small local server the Android Companion app talks to (same Wi-Fi only).

Two sockets:
  * UDP  47821  - "is a Business Manager here?"  The phone shouts on the Wi-Fi and the PC answers with its
                  address, so nobody ever types an IP address and a changed IP address does not matter.
  * HTTP 47820  - GET /hello, POST /pair, POST /api (encrypted; see companion.py).

The server threads never touch the database. Every request is handed to `run(job)`, which the window
supplies and which executes the job on the program's main thread (the only thread allowed to use the
database), then gives the answer back."""
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import companion
from .companion import ApiError

MAX_BODY = 256 * 1024


def local_addresses() -> list:
    """The PC's own Wi-Fi / LAN addresses (shown to the owner; the phone finds the PC by itself)."""
    found = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except OSError:
        pass
    try:                                    # the address used for the local network (nothing is sent)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        found.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(a for a in found if not a.startswith("127."))


class CompanionServer:
    def __init__(self, run, db_getter, pairing, http_port=companion.HTTP_PORT,
                 discovery_port=companion.DISCOVERY_PORT, host="0.0.0.0"):
        """run(job) -> job() executed on the main thread. db_getter() -> the open Database."""
        self.run, self.db, self.pairing = run, db_getter, pairing
        self.host, self.http_port, self.discovery_port = host, http_port, discovery_port
        self.httpd = self.udp = None
        self.error = ""
        self._hello = None

    # ---- lifecycle ----
    def start(self) -> bool:
        if self.httpd:
            return True
        try:
            self._hello = self.run(lambda: companion.hello(self.db()))
            self.httpd = ThreadingHTTPServer((self.host, self.http_port), self._handler())
            self.httpd.daemon_threads = True
            self.http_port = self.httpd.server_address[1]
            self._hello["port"] = self.http_port
            threading.Thread(target=self.httpd.serve_forever, name="companion-http", daemon=True).start()
        except OSError as exc:
            self.httpd, self.error = None, f"Could not open port {self.http_port}: {exc}"
            return False
        try:
            self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp.bind((self.host, self.discovery_port))
            self.discovery_port = self.udp.getsockname()[1]
            threading.Thread(target=self._discovery_loop, name="companion-udp", daemon=True).start()
        except OSError as exc:              # the app still works: the phone can use the last known address
            self.udp, self.error = None, f"Automatic discovery is off (port {self.discovery_port}): {exc}"
        return True

    def stop(self):
        httpd, udp, self.httpd, self.udp = self.httpd, self.udp, None, None
        if httpd:
            threading.Thread(target=lambda: (httpd.shutdown(), httpd.server_close()), daemon=True).start()
        if udp:
            try:
                udp.close()
            except OSError:
                pass

    def running(self) -> bool:
        return self.httpd is not None

    # ---- discovery ----
    def _discovery_loop(self):
        sock = self.udp
        while sock is self.udp:
            try:
                data, addr = sock.recvfrom(256)
            except OSError:
                return
            if data.strip() == companion.DISCOVER_ASK and self._hello:
                answer = {k: self._hello[k] for k in ("app", "api", "server_id", "shop", "port")}
                try:
                    sock.sendto(json.dumps(answer).encode("utf-8"), addr)
                except OSError:
                    pass

    # ---- http ----
    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            server_version = "BNBC/1"

            def log_message(self, *args):       # nothing is written to the console
                pass

            def _send(self, status, obj):
                body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                if n <= 0 or n > MAX_BODY:
                    raise ApiError(400, "bad_request", "Badly formed data")
                try:
                    obj = json.loads(self.rfile.read(n).decode("utf-8"))
                except ValueError:
                    raise ApiError(400, "bad_request", "Badly formed data")
                if not isinstance(obj, dict):
                    raise ApiError(400, "bad_request", "Badly formed data")
                return obj

            def _answer(self, fn):
                try:
                    self._send(200, fn())
                except ApiError as exc:
                    self._send(exc.status, {"ok": False, "error": exc.code, "message": exc.message})
                except TimeoutError:
                    self._send(503, {"ok": False, "error": "busy", "message": "The computer is busy. Try again."})
                except Exception:               # never leak details of an internal error to the network
                    self._send(500, {"ok": False, "error": "server", "message": "Internal error"})

            def do_GET(self):
                if self.path.split("?")[0] == "/hello":
                    self._answer(lambda: server.run(lambda: companion.hello(server.db())) | {"port": server.http_port})
                else:
                    self._send(404, {"ok": False, "error": "not_found"})

            def do_POST(self):
                path = self.path.split("?")[0]
                if path == "/pair":
                    self._answer(lambda: (lambda b: server.run(
                        lambda: companion.pair(server.db(), server.pairing, b)))(self._body()))
                elif path == "/api":
                    self._answer(lambda: (lambda b: server.run(lambda: companion.api(server.db(), b)))(self._body()))
                else:
                    self._send(404, {"ok": False, "error": "not_found"})

        return Handler
