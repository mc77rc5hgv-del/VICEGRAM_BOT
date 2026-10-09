"""Happ schema: https://github.com/Flyfrog-LLC/Happ-docs/blob/main/dev-docs/routing.md"""
import base64
import json

DIRECT_DOMAINS = (
    "ru", "su", "xn--p1ai", "yandex.com", "yandex.net", "yastatic.net",
    "vk.com", "vk.me", "userapi.com", "vkuserphoto.net", "vkuseraudio.net",
    "ozon.com", "ozonusercontent.com", "wbstatic.net", "wbbasket.com",
    "sberbank.com", "tinkoffbank.com",
)
LOCAL_NETWORKS = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
                  "169.254.0.0/16", "fc00::/7", "fe80::/10")

def profile(mode):
    if mode not in ("universal", "full"):
        raise ValueError("Unknown routing mode")
    universal = mode == "universal"
    return {
        "Name": "MED VPN Routing", "GlobalProxy": "true",
        "RemoteDNSType": "DoH",
        "RemoteDNSDomain": "https://cloudflare-dns.com/dns-query",
        "RemoteDNSIP": "1.1.1.1",
        "DomesticDNSType": "DoU" if universal else "DoH",
        "DomesticDNSDomain": "" if universal else "https://cloudflare-dns.com/dns-query",
        "DomesticDNSIP": "77.88.8.8" if universal else "1.1.1.1",
        "DnsHosts": {"cloudflare-dns.com": "1.1.1.1"},
        "DirectSites": ["domain:" + d for d in DIRECT_DOMAINS] if universal else [],
        "DirectIp": list(LOCAL_NETWORKS),
        "ProxySites": [], "ProxyIp": [], "BlockSites": [], "BlockIp": [],
        "DomainStrategy": "IPIfNonMatch", "FakeDNS": "false",
    }

def routing_uri(mode):
    payload = json.dumps(profile(mode), ensure_ascii=True, separators=(",", ":"))
    return "happ://routing/onadd/" + base64.b64encode(payload.encode()).decode()
