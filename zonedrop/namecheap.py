"""Namecheap API client — getHosts and setHosts over XML-RPC."""

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any


API_BASE = "https://api.namecheap.com/xml.response"


def _request(
    api_user: str,
    api_key: str,
    client_ip: str,
    params: dict[str, str],
    method: str = "GET",
    timeout: int = 30,
) -> str:
    params = {
        "ApiUser": api_user,
        "ApiKey": api_key,
        "UserName": api_user,
        "ClientIp": client_ip,
        **params,
    }
    encoded = urllib.parse.urlencode(params).encode()
    url = API_BASE + "?" + urllib.parse.urlencode(params) if method == "GET" else API_BASE
    req = urllib.request.Request(url, data=encoded if method == "POST" else None, method=method)
    return urllib.request.urlopen(req, timeout=timeout).read().decode()


def get_hosts(api_user: str, api_key: str, client_ip: str, sld: str, tld: str) -> list[dict[str, str]]:
    """Fetch all DNS records for a domain. Retries up to 3 times on failure."""
    last_error = None
    for attempt in range(1, 4):
        try:
            xml = _request(api_user, api_key, client_ip, {
                "Command": "namecheap.domains.dns.getHosts",
                "SLD": sld,
                "TLD": tld,
            })
            root = ET.fromstring(xml)
            if root.findtext(".//Status") == "ERROR":
                errs = [e.text or "" for e in root.findall(".//Error")]
                raise RuntimeError("API error: " + "; ".join(errs))
            hosts = []
            for host in root.findall(".//host"):
                hosts.append({
                    "Name": host.get("Name", ""),
                    "Type": host.get("Type", ""),
                    "Address": host.get("Address", ""),
                    "TTL": host.get("TTL", "300"),
                })
            if hosts:
                return hosts
        except Exception as e:
            last_error = e
            if attempt < 3:
                import time
                time.sleep(2)
    raise RuntimeError(f"Failed to fetch DNS after 3 attempts: {last_error}")


def set_hosts(
    api_user: str,
    api_key: str,
    client_ip: str,
    sld: str,
    tld: str,
    records: list[dict[str, str]],
) -> None:
    """Write all DNS records for a domain. Replaces the entire zone."""
    params: dict[str, Any] = {
        "Command": "namecheap.domains.dns.setHosts",
        "SLD": sld,
        "TLD": tld,
    }
    for i, r in enumerate(records, 1):
        params[f"HostName{i}"] = r["Name"]
        params[f"RecordType{i}"] = r["Type"]
        params[f"Address{i}"] = r["Address"]
        params[f"TTL{i}"] = r["TTL"]
    xml = _request(api_user, api_key, client_ip, params, method="POST")
    if 'Status="OK"' not in xml:
        errs = re.findall(r"<Error[^>]*>([^<]+)", xml)
        raise RuntimeError("Write failed: " + ("; ".join(errs) if errs else "unknown error"))
