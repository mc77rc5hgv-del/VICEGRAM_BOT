"""Real QUIC/TUN failover with an injected dual-stack route failure in a namespace."""
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

import shutil
import uuid
if os.geteuid() != 0:
    raise RuntimeError("namespace fixture requires root")
ip = shutil.which("ip")
namespace = "volna-" + uuid.uuid4().hex[:8]
host_link = "vh" + uuid.uuid4().hex[:8]
peer_link = "vp" + uuid.uuid4().hex[:8]
def run(*args):
    subprocess.run([ip,*args],check=True)
run("netns","add",namespace)
try:
    run("link","add",host_link,"type","veth","peer","name",peer_link)
    run("link","set",peer_link,"netns",namespace)
    run("addr","add","192.0.2.1/24","dev",host_link)
    run("link","set",host_link,"up")
    run("-n",namespace,"link","set","lo","up")
    run("-n",namespace,"addr","add","192.0.2.2/24","dev",peer_link)
    run("-n",namespace,"link","set",peer_link,"up")
    run("-n",namespace,"route","add","default","via","192.0.2.1")
    # Reverse-path validation otherwise consults the fail-closed policy table for
    # unmarked QUIC replies. These sysctls affect this fresh namespace only.
    run("netns","exec",namespace,"sysctl","-w","net.ipv4.conf.all.rp_filter=0",
        "net.ipv4.conf.default.rp_filter=0","net.ipv4.conf."+peer_link+".rp_filter=0")
    udp = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    udp.bind(("192.0.2.1",0))
    def echo():
        while True:
            try:
                data,address = udp.recvfrom(4096)
                udp.sendto(data,address)
            except OSError:
                return
    threading.Thread(target=echo,daemon=True).start()
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
        route_failure = tmp / "route-failed-once"
        ip_wrapper = tmp / "ip-wrapper"
        ip_wrapper.write_text("#!/usr/bin/python3\nimport os,subprocess,sys\n"
            + "args=sys.argv[1:]\nflag=" + repr(str(route_failure)) + "\n"
            + "if '-4' in args and 'replace' in args and 'volna1' in args and os.path.exists(flag):\n"
            + "    import json\n    for family in ['-4','-6']:\n"
            + "        routes=json.loads(subprocess.check_output([" + repr(ip) + ",family,'-j','route','show','table','20000']))\n"
            + "        assert any(r.get('dev') == 'volna0' and r.get('metric') == 10 for r in routes), 'rollback must restore both families before retry'\n"
            + "result=subprocess.run([" + repr(ip) + "]+args)\n"
            + "if result.returncode == 0 and '-6' in args and 'replace' in args and 'volna1' in args and not os.path.exists(flag):\n"
            + "    open(flag,'w').write('injected after IPv6 mutation')\n    sys.exit(1)\n"
            + "sys.exit(result.returncode)\n")
        ip_wrapper.chmod(0o700)
        client_log = tmp / "client-errors.log"
        wrapper = tmp / "client-wrapper"
        wrapper.write_text("#!/usr/bin/python3\nimport os,sys\n"
            + "fd=os.open(" + repr(str(client_log)) + ",os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)\n"
            + "os.dup2(fd,2)\nos.execv(" + repr(str(binary)) + ",[" + repr(str(binary)) + "]+sys.argv[1:])\n")
        wrapper.chmod(0o700)
        ca, ca_key = tmp / "ca.pem", tmp / "ca.key"
        cert, key, csr = tmp / "cert.pem", tmp / "key.pem", tmp / "leaf.csr"
        openssl("req","-x509","-newkey","rsa:2048","-nodes","-keyout",ca_key,
                "-out",ca,"-days","1","-subj","/CN=VOLNA test CA",
                "-addext","basicConstraints=critical,CA:TRUE")
        openssl("req","-new","-newkey","rsa:2048","-nodes","-keyout",key,
                "-out",csr,"-subj","/CN=localhost")
        extensions = tmp / "extensions"
        extensions.write_text("subjectAltName=DNS:localhost,IP:192.0.2.1\nbasicConstraints=critical,CA:FALSE\nextendedKeyUsage=serverAuth\n")
        openssl("x509","-req","-in",csr,"-CA",ca,"-CAkey",ca_key,"-CAcreateserial",
                "-out",cert,"-days","1","-extfile",extensions)
        der = ssl.PEM_cert_to_DER_cert(cert.read_text())
        pin = hashlib.sha256(der).hexdigest()
        origin = http.server.ThreadingHTTPServer(("192.0.2.1",0),Origin)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(cert,key)
        origin.socket = tls.wrap_socket(origin.socket,server_side=True)
        threading.Thread(target=origin.serve_forever,daemon=True).start()
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as reservation:
            reservation.bind(("192.0.2.1",0))
            endpoint = "192.0.2.1:" + str(reservation.getsockname()[1])
        config = tmp / "server.json"
        config.write_text(json.dumps({"listen":endpoint,
            "tls":{"cert":str(cert),"key":str(key)},
            "auth":{"type":"userpass","userpass":{"volna":"fixture-password"}}}))
        config.chmod(0o600)
        server = subprocess.Popen([str(binary),"server","--config",str(config),
            "--disable-update-check","--log-level","error"],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as reservation:
            reservation.bind(("192.0.2.1",0))
            backup_endpoint = "192.0.2.1:" + str(reservation.getsockname()[1])
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
            dead.bind(("192.0.2.1",0))
            env = dict(os.environ,VOLNA_IP=str(ip_wrapper),VOLNA_UDP="192.0.2.1:" + str(udp.getsockname()[1]),TMPDIR=str(tmp),VOLNA_HYSTERIA_BIN=str(wrapper),
                VOLNA_ROUTE_FAILURE=str(route_failure),VOLNA_HYSTERIA_SERVER=endpoint,VOLNA_HYSTERIA_PIN=pin,
                VOLNA_HYSTERIA_BACKUP_SERVER=backup_endpoint,VOLNA_STOP_PRIMARY=str(stop_flag),
                VOLNA_HYSTERIA_DEAD_SERVER="192.0.2.1:" + str(dead.getsockname()[1]),
                VOLNA_TEST_CA=str(ca),
                VOLNA_TEST_HEALTH="https://192.0.2.1:" + str(origin.server_port) + "/health")
            try:
                subprocess.run([ip,"netns","exec",namespace,"/usr/bin/python3","-c",
                    "import socket; s=socket.create_connection(('192.0.2.1'," + str(origin.server_port) + "),2); s.close()"],
                    check=True)
                subprocess.run([ip,"netns","exec",namespace,
                    str(pathlib.Path("volna-core/target/debug/examples/linux_tun_probe").resolve())],
                    env=env,check=True,timeout=90)
                if not route_failure.exists():
                    raise RuntimeError("route failure injection was not exercised")
                if backup.poll() is not None:
                    raise RuntimeError("Hysteria backup server exited")
            finally:
                if client_log.exists():
                    print(client_log.read_text(),flush=True)
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

finally:
    subprocess.run([ip,"netns","del",namespace],check=False)
    subprocess.run([ip,"link","del",host_link],check=False,
                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
