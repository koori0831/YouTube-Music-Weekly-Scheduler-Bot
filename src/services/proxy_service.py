from __future__ import annotations

import os
import re
from html import unescape
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import requests
except ModuleNotFoundError:
    requests = None

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:
    BeautifulSoup = None


class ProxyService:
    _SOURCE_URL = "http://spys.one/en/free-proxy-list/"
    _FORM_DATA = {"xpp": "1", "xf1": "0", "xf2": "0", "xf4": "0", "xf5": "2"}
    _HEADERS = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0",
    }
    _PORT_PATTERN = re.compile(r"\(([a-zA-Z0-9]+)\^[a-zA-Z0-9]+\)")
    _BODY_SCRIPT_PATTERN = re.compile(r"<body[^>]*>.*?<script[^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL)
    _ROW_PATTERN = re.compile(r"<tr[^>]*onmouseover[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
    _IP_PATTERN = re.compile(r"<font[^>]*class=(?:[\"'])?spy14(?:[\"'])?[^>]*>(.*?)</font>", re.IGNORECASE | re.DOTALL)
    _SCRIPT_PATTERN = re.compile(r"<script[^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL)
    _UPTIME_PATTERN = re.compile(r"(\d+)%")
    _TAG_PATTERN = re.compile(r"<[^>]+>")

    def __init__(self, timeout: int = 10) -> None:
        self._timeout = timeout

    def get_proxies(self) -> list[str]:
        html = self._fetch_proxy_html()
        if not html:
            return self._fallback_from_environment()

        proxies = self._parse_proxy_html(html)
        if proxies:
            return proxies

        return self._fallback_from_environment()

    def _fetch_proxy_html(self) -> str | None:
        if requests is not None:
            try:
                response = requests.post(
                    self._SOURCE_URL,
                    data=self._FORM_DATA,
                    headers=self._HEADERS,
                    timeout=self._timeout,
                )
                response.raise_for_status()
                return response.text
            except requests.RequestException:
                return None

        payload = urlencode(self._FORM_DATA).encode("utf-8")
        request = Request(
            self._SOURCE_URL,
            data=payload,
            headers=self._HEADERS,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                return response.read().decode("utf-8", errors="ignore")
        except OSError:
            return None

    def _parse_proxy_html(self, html: str) -> list[str]:
        if BeautifulSoup is not None:
            return self._parse_proxy_html_with_bs4(html)
        return self._parse_proxy_html_with_regex(html)

    def _parse_proxy_html_with_bs4(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        script_text = self._find_port_token_script_text(
            script.get_text()
            for script in soup.select("script")
        )
        port_tokens = self._extract_port_tokens(script_text)
        if not port_tokens:
            return []

        ranked: list[tuple[str, int]] = []
        for row in soup.select("tr[onmouseover]"):
            ip_node = row.select_one("font.spy14")
            port_nodes = row.select("script")
            if ip_node is None or not port_nodes:
                continue

            port = self._decode_port(port_nodes[-1].get_text(), port_tokens)
            if not port:
                continue

            for script_node in ip_node.find_all("script"):
                script_node.extract()

            ip = ip_node.get_text(strip=True)
            uptime = self._extract_uptime(row.get_text(" ", strip=True))
            if not ip or uptime is None:
                continue

            ranked.append((f"http://{ip}:{port}", uptime))

        ranked.sort(key=lambda item: item[1], reverse=True)
        return [proxy for proxy, _ in ranked]

    def _parse_proxy_html_with_regex(self, html: str) -> list[str]:
        script_text = self._find_port_token_script_text(match.group(1) for match in self._SCRIPT_PATTERN.finditer(html))
        port_tokens = self._extract_port_tokens(script_text)
        if not port_tokens:
            return []

        ranked: list[tuple[str, int]] = []
        for row_html in self._ROW_PATTERN.findall(html):
            ip_match = self._IP_PATTERN.search(row_html)
            scripts = self._SCRIPT_PATTERN.findall(row_html)
            if ip_match is None or not scripts:
                continue

            port = self._decode_port(" ".join(scripts), port_tokens)
            if not port:
                continue

            ip_html = re.sub(self._SCRIPT_PATTERN, "", ip_match.group(1))
            ip = self._clean_text(ip_html)
            uptime = self._extract_uptime(self._clean_text(row_html))
            if not ip or uptime is None:
                continue

            ranked.append((f"http://{ip}:{port}", uptime))

        ranked.sort(key=lambda item: item[1], reverse=True)
        return [proxy for proxy, _ in ranked]

    def _extract_port_tokens(self, script_text: str) -> dict[str, str]:
        ports: dict[str, str] = {}
        for row in script_text.split(";"):
            if "^" not in row or "=" not in row:
                continue

            name, expression = row.split("=", 1)
            token = name.strip()
            port_part = expression.split("^", 1)[0].strip()
            if token and port_part.isdigit():
                ports[token] = port_part
        return ports

    def _find_port_token_script_text(self, script_texts) -> str:
        for script_text in script_texts:
            if not script_text or "^" not in script_text or "=" not in script_text:
                continue
            if self._extract_port_tokens(script_text):
                return script_text
        return ""

    def _decode_port(self, script_text: str, port_tokens: dict[str, str]) -> str:
        return "".join(port_tokens[token] for token in self._PORT_PATTERN.findall(script_text) if token in port_tokens)

    def _extract_uptime(self, text: str) -> int | None:
        match = self._UPTIME_PATTERN.search(text)
        if match:
            return int(match.group(1))
        return None

    def _clean_text(self, value: str) -> str:
        without_tags = self._TAG_PATTERN.sub("", value)
        return unescape(without_tags).strip()

    def _fallback_from_environment(self) -> list[str]:
        proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
        if proxy and proxy.strip():
            return [proxy.strip()]
        return []
