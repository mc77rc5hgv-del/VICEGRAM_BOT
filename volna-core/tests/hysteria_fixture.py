"""Real Hysteria2/QUIC + TLS origin. Everything stays on loopback."""
import hashlib
import http.server
import json
import os
import pathlib
import socket
import ssl
import subprocess
import tempfile
import threading
import urllib.request

VERSION = "app/v2.12.3"
DIGEST = "8c7a68a906998b747a0db87586e364f995fbfddb95693ae6e2fdb68a6e920d3e"

class Origin(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(204)
            self.end_headers()
        elif self.path == "/payload":
            body = b"volna-real-quic"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)
    def log_message(self, *args):
        pass

def openssl(*args):
    subprocess.run(["openssl", *map(str,args)],check=True,
                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

with tempfile.TemporaryDirectory(prefix="volna-quic-") as tmp:
    tmp = pathlib.Path(tmp)
    binary = tmp / "hysteria"
    url = "https://github.com/HyNetworks/hysteria/releases/download/" + VERSION + "/hysteria-linux-amd64"
    with urllib.request.urlopen(url,timeout=60) as response:
        payload = response.read(64 * 1024 * 1024 + 1)
    if len(payload) > 64 * 1024 * 1024 or hashlib.sha256(payload).hexdigest() != DIGEST:
        raise RuntimeError("Hysteria release checksum mismatch")
    binary.write_bytes(payload)
    binary.chmod(0o700)
    ca, ca_key = tmp / "ca.pem", tmp / "ca.key"
    cert, key, csr = tmp / "cert.pem", tmp / "key.pem", tmp / "leaf.csr"
    openssl("req","-x509","-newkey","rsa:2048","-nodes","-keyout",ca_key,
            "-out",ca,"-days","1","-subj","/CN=VOLNA test CA",
            "-addext","basicConstraints=critical,CA:TRUE")
    openssl("req","-new","-newkey","rsa:2048","-nodes","-keyout",key,
            "-out",csr,"-subj","/CN=localhost")
    extensions = tmp / "extensions"
    extensions.write_text("subjectAltName=DNS:localhost\nbasicConstraints=critical,CA:FALSE\nextendedKeyUsage=serverAuth\n")
    openssl("x509","-req","-in",csr,"-CA",ca,"-CAkey",ca_key,"-CAcreateserial",
            "-out",cert,"-days","1","-extfile",extensions)
    der = ssl.PEM_cert_to_DER_cert(cert.read_text())
    pin = hashlib.sha256(der).hexdigest()
    origin = http.server.ThreadingHTTPServer(("127.0.0.1",0),Origin)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(cert,key)
    origin.socket = tls.wrap_socket(origin.socket,server_side=True)
    threading.Thread(target=origin.serve_forever,daemon=True).start()
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as reservation:
        reservation.bind(("127.0.0.1",0))
        endpoint = "127.0.0.1:" + str(reservation.getsockname()[1])
    config = tmp / "server.json"
    config.write_text(json.dumps({"listen":endpoint,
        "tls":{"cert":str(cert),"key":str(key)},
        "auth":{"type":"userpass","userpass":{"volna":"fixture-password"}}}))
    config.chmod(0o600)
    server = subprocess.Popen([str(binary),"server","--config",str(config),
        "--disable-update-check","--log-level","error"],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as reservation:
        reservation.bind(("127.0.0.1",0))
        backup_endpoint = "127.0.0.1:" + str(reservation.getsockname()[1])
    backup_config = tmp / "backup.json"
    backup_config.write_text(json.dumps({"listen":backup_endpoint,
        "tls":{"cert":str(cert),"key":str(key)},
        "auth":{"type":"userpass","userpass":{"volna":"fixture-password"}}}))
    backup_config.chmod(0o600)
    backup = subprocess.Popen([str(binary),"server","--config",str(backup_config),
        "--disable-update-check","--log-level","error"],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    stop_flag = tmp / "stop-primary"
    stop_monitor = threading.Event()
    def monitor():
        while not stop_monitor.wait(0.02):
            if stop_flag.exists():
                server.terminate()
                return
    threading.Thread(target=monitor,daemon=True).start()
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as dead:
        dead.bind(("127.0.0.1",0))
        env = dict(os.environ,TMPDIR=str(tmp),VOLNA_HYSTERIA_BIN=str(binary),
            VOLNA_HYSTERIA_SERVER=endpoint,VOLNA_HYSTERIA_PIN=pin,
            VOLNA_HYSTERIA_BACKUP_SERVER=backup_endpoint,VOLNA_STOP_PRIMARY=str(stop_flag),
            VOLNA_HYSTERIA_DEAD_SERVER="127.0.0.1:" + str(dead.getsockname()[1]),
            VOLNA_TEST_CA=str(ca),
            VOLNA_TEST_HEALTH="https://localhost:" + str(origin.server_port) + "/health")
        try:
            subprocess.run(["cargo","test","--manifest-path","volna-core/Cargo.toml",
                "--test","hysteria","--","--ignored","--test-threads=1"],env=env,check=True,timeout=180)
            if backup.poll() is not None:
                raise RuntimeError("Hysteria backup server exited")
        finally:
            stop_monitor.set()
            backup.terminate()
            try:
                backup.wait(timeout=5)
            except subprocess.TimeoutExpired:
                backup.kill()
                backup.wait(timeout=5)
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
            origin.shutdown()
