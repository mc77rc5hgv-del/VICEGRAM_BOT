"""Local HTTPS origin and SOCKS5 relay; no public internet or live VPN secrets."""
import http.server
import os
import pathlib
import select
import socket
import socketserver
import ssl
import struct
import subprocess
import tempfile
import threading

def exact(sock, count):
    data = b""
    while len(data) < count:
        part = sock.recv(count - len(data))
        if not part:
            raise ConnectionError("closed")
        data += part
    return data

class Origin(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(204)
            self.end_headers()
        elif self.path == "/payload":
            body = b"volna-through-socks"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)
    def log_message(self, *args):
        pass

class Relay(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            version, count = exact(self.request, 2)
            methods = exact(self.request, count)
            if version != 5 or 0 not in methods:
                return
            self.request.sendall(b"\\x05\\x00")
            version, command, reserved, address_type = exact(self.request, 4)
            if (version, command, reserved, address_type) != (5, 1, 0, 3):
                return  # require proxy DNS (socks5h), not local DNS
            host = exact(self.request, exact(self.request, 1)[0]).decode()
            port = struct.unpack("!H", exact(self.request, 2))[0]
            if host != "localhost" or port != self.server.origin_port:
                return
            with socket.create_connection(("127.0.0.1", port), timeout=3) as upstream:
                self.server.connections += 1
                self.request.sendall(b"\\x05\\x00\\x00\\x01\\x7f\\x00\\x00\\x01\\x00\\x00")
                peers = [self.request, upstream]
                while True:
                    ready, _, _ = select.select(peers, [], [], 5)
                    if not ready:
                        return
                    for source in ready:
                        chunk = source.recv(65536)
                        if not chunk:
                            return
                        (upstream if source is self.request else self.request).sendall(chunk)
        except (OSError, ConnectionError):
            pass

class SocksServer(socketserver.ThreadingTCPServer):
    daemon_threads = True

with tempfile.TemporaryDirectory(prefix="volna-socks-") as tmp:
    tmp = pathlib.Path(tmp)
    cert, key = tmp / "cert.pem", tmp / "key.pem"
    ca, ca_key = tmp / "ca.pem", tmp / "ca.key"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                    "-keyout", str(ca_key), "-out", str(ca), "-days", "1",
                    "-subj", "/CN=localhost",
                    "-addext", "subjectAltName=DNS:localhost",
                    "-addext", "basicConstraints=critical,CA:TRUE"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["openssl", "req", "-new", "-newkey", "rsa:2048", "-nodes",
                    "-keyout", str(key), "-out", str(tmp / "leaf.csr"),
                    "-subj", "/CN=localhost"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    extensions = tmp / "extensions"
    extensions.write_text("subjectAltName=DNS:localhost\nbasicConstraints=critical,CA:FALSE\nextendedKeyUsage=serverAuth\n")
    subprocess.run(["openssl", "x509", "-req", "-in", str(tmp / "leaf.csr"),
                    "-CA", str(ca), "-CAkey", str(ca_key), "-CAcreateserial",
                    "-out", str(cert), "-days", "1", "-extfile", str(extensions)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    origin = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Origin)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    origin.socket = context.wrap_socket(origin.socket, server_side=True)
    socks = SocksServer(("127.0.0.1", 0), Relay)
    socks.origin_port = origin.server_port
    socks.connections = 0
    # Reserve an unserved TCP port for the direct-fallback check.
    with socket.socket() as dead:
        dead.bind(("127.0.0.1", 0))
        for server in (origin, socks):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        env = dict(os.environ, VOLNA_TEST_PROXY="127.0.0.1:" + str(socks.server_address[1]),
                   VOLNA_TEST_DEAD_PROXY="127.0.0.1:" + str(dead.getsockname()[1]),
                   VOLNA_TEST_HEALTH="https://localhost:" + str(origin.server_port) + "/health",
                   VOLNA_TEST_CA=str(ca))
        try:
            subprocess.run(["cargo", "test", "--manifest-path", "volna-core/Cargo.toml",
                            "--test", "socks", "--", "--ignored"], env=env, check=True, timeout=180)
            assert socks.connections >= 3, "Requests must pass through the SOCKS relay"
        finally:
            socks.shutdown()
            origin.shutdown()
