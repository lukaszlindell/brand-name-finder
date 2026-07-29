#!/usr/bin/env python3
"""Generate brand names and check .com/.se availability."""

from __future__ import annotations

import argparse
import csv
import html
import itertools
import random
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

import requests

COM_RDAP_URL = "https://rdap.verisign.com/com/v1/domain/{domain}"
SE_FREE_URL = "http://free.iis.se/free"
USER_AGENT = "brand-name-finder/1.0 (+https://github.com/lukaszlindell/brand-name-finder)"

PREFIXES = [
    "ave", "bri", "cal", "cle", "cor", "elo", "eva", "flo", "form", "fra",
    "kai", "kin", "lin", "lo", "lum", "mar", "mer", "mon", "nori", "nova",
    "ori", "pra", "pri", "ral", "rel", "sol", "tala", "valo", "vel", "vero",
    "via", "viva",
]
SUFFIXES = [
    "able", "ara", "aro", "ava", "era", "ero", "eva", "ia", "io", "ira",
    "ivo", "ly", "ora", "oro", "ova", "ra", "ria", "ro", "va", "via", "vo",
]
CURATED = [
    "Kindred", "Tandem", "Outline", "Resonant", "Grounded", "Formable",
    "Craftable", "Gatherly", "Forwardly", "Frameable", "Signalise",
    "Clarity", "Current", "Relay", "Beacon", "Canvas", "Thread", "Plainly",
]
BLOCKED_PARTS = {
    "porn", "fuck", "shit", "nazi", "isis", "kkk", "drug", "kill", "scam",
    "fraud",
}
BUSINESS_CLICHES = {
    "ai", "tech", "digital", "software", "saas", "consulting", "solutions",
    "ventures", "capital",
}
VOWELS = set("aeiouy")


@dataclass
class Candidate:
    rank: int
    name: str
    com_domain: str
    com_status: str
    se_domain: str
    se_status: str
    score: float
    length: int
    bolagsverket_url: str
    tmview_url: str
    checked_at_utc: str
    notes: str


def normalize(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.lower())


def reasonable_shape(name: str) -> bool:
    value = normalize(name)
    if not 5 <= len(value) <= 10:
        return False
    if any(part in value for part in BLOCKED_PARTS):
        return False
    if value in BUSINESS_CLICHES:
        return False
    if re.search(r"(.)\1\1", value):
        return False
    if re.search(r"[bcdfghjklmnpqrstvwxyz]{4,}", value):
        return False
    if re.search(r"[aeiouy]{3,}", value):
        return False
    return True


def generate_names(seed: int, custom_names: list[str]) -> list[str]:
    names: set[str] = set()
    for prefix, suffix in itertools.product(PREFIXES, SUFFIXES):
        combined = prefix + (suffix[1:] if prefix[-1] == suffix[0] else suffix)
        if reasonable_shape(combined):
            names.add(combined.capitalize())
    names.update(name.strip().capitalize() for name in CURATED if reasonable_shape(name))
    names.update(
        name.strip().capitalize()
        for name in custom_names
        if name.strip() and reasonable_shape(name)
    )
    result = sorted(names)
    random.Random(seed).shuffle(result)
    return result


def request_with_retries(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, str] | None = None,
    attempts: int = 3,
) -> requests.Response | None:
    for attempt in range(attempts):
        try:
            response = session.get(url, params=params, timeout=15)
            if response.status_code not in {429, 500, 502, 503, 504}:
                return response
        except requests.RequestException:
            pass
        time.sleep(1.5 * (attempt + 1))
    return None


def check_com(session: requests.Session, domain: str) -> str:
    response = request_with_retries(session, COM_RDAP_URL.format(domain=domain))
    if response is None:
        return "unknown"
    if response.status_code == 404:
        return "available"
    if response.status_code == 200:
        return "registered"
    return "unknown"


def check_se(session: requests.Session, domain: str) -> str:
    response = request_with_retries(session, SE_FREE_URL, params={"q": domain})
    if response is None or response.status_code != 200:
        return "unknown"
    value = response.text.strip().lower()
    if value.startswith("free "):
        return "available"
    if value.startswith("occupied "):
        return "registered"
    return "unknown"


def pronounceability_score(value: str) -> float:
    transitions = sum(
        (a in VOWELS) != (b in VOWELS) for a, b in zip(value, value[1:])
    )
    transition_ratio = transitions / max(1, len(value) - 1)
    score = 18 - abs(0.62 - transition_ratio) * 20
    if 6 <= len(value) <= 8:
        score += 12
    elif len(value) in {5, 9}:
        score += 6
    if value[-1] in "aeoy":
        score += 3
    if value.startswith(("north", "nord")):
        score -= 5
    return score


def calculate_score(name: str, com_status: str, se_status: str) -> float:
    score = pronounceability_score(normalize(name))
    score += {"available": 65, "registered": -100, "unknown": -15}[com_status]
    score += {"available": 18, "registered": -4, "unknown": -5}[se_status]
    return round(score, 1)


def search_links(name: str) -> tuple[str, str]:
    query = quote_plus(name)
    bolagsverket = "https://foretagsinfo.bolagsverket.se/sok-foretagsinformation-web/foretag"
    tmview = (
        "https://www.tmdn.org/tmview/#/tmview/results"
        f"?page=1&pageSize=30&criteria=C&basicSearch={query}"
    )
    return bolagsverket, tmview


def note_for(com_status: str, se_status: str) -> str:
    messages = {
        "available": "verkar ledig",
        "registered": "registrerad",
        "unknown": "kunde inte avgöras",
    }
    return f".com {messages[com_status]}; .se {messages[se_status]}"


def check_names(
    names: list[str],
    max_names: int,
    delay: float,
    dry_run: bool,
) -> list[Candidate]:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    checked_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows: list[Candidate] = []

    for index, name in enumerate(names[:max_names], start=1):
        value = normalize(name)
        com_domain, se_domain = f"{value}.com", f"{value}.se"
        if dry_run:
            com_status = se_status = "unknown"
        else:
            com_status = check_com(session, com_domain)
            time.sleep(delay)
            se_status = check_se(session, se_domain)
            time.sleep(delay)
        bolagsverket, tmview = search_links(name)
        rows.append(
            Candidate(
                rank=0,
                name=name,
                com_domain=com_domain,
                com_status=com_status,
                se_domain=se_domain,
                se_status=se_status,
                score=calculate_score(name, com_status, se_status),
                length=len(value),
                bolagsverket_url=bolagsverket,
                tmview_url=tmview,
                checked_at_utc=checked_at,
                notes=note_for(com_status, se_status),
            )
        )
        print(
            f"[{index:>3}/{min(max_names, len(names))}] "
            f"{name:<12} .com={com_status:<10} .se={se_status:<10}"
        )

    rows.sort(
        key=lambda row: (
            row.com_status == "available",
            row.se_status == "available",
            row.score,
        ),
        reverse=True,
    )
    for rank, row in enumerate(rows, start=1):
        row.rank = rank
    return rows


def write_csv(rows: list[Candidate], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=asdict(rows[0]).keys())
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)


def status_sv(status: str) -> str:
    return {
        "available": "✅ Verkar ledig",
        "registered": "❌ Registrerad",
        "unknown": "⚠️ Oklar",
    }[status]


def write_markdown(rows: list[Candidate], path: Path) -> None:
    available = [row for row in rows if row.com_status == "available"]
    lines = [
        "# Resultat – namnförslag",
        "",
        f"Senast kontrollerad: `{rows[0].checked_at_utc}`",
        "",
        "> Domänstatus är en ögonblicksbild, inte en reservation. Kontrollera hos en "
        "registrar och granska företagsnamn/varumärken innan du bestämmer dig.",
        "",
        f"**{len(available)} av {len(rows)}** kontrollerade namn hade en `.com` som "
        "verkade ledig.",
        "",
        "| # | Namn | .com | .se | Poäng | Bolagsnamn | Varumärke |",
        "|---:|---|---|---|---:|---|---|",
    ]
    for row in rows[:100]:
        lines.append(
            f"| {row.rank} | **{row.name}** | {status_sv(row.com_status)} "
            f"`{row.com_domain}` | {status_sv(row.se_status)} `{row.se_domain}` | "
            f"{row.score} | [Bolagsverket]({row.bolagsverket_url}) | "
            f"[TMview]({row.tmview_url}) |"
        )
    lines.extend(
        [
            "",
            "## Så tolkar du resultatet",
            "",
            "- Prioritera namn där både `.com` och `.se` verkar lediga.",
            "- Klicka sedan på Bolagsverket och sök namnet manuellt.",
            "- Kontrollera liknande varumärken i TMview, inte bara exakt stavning.",
            "- Registrera domänerna direkt när du har gjort slutkontrollen.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_html(rows: list[Candidate], path: Path) -> None:
    table_rows = []
    for row in rows:
        table_rows.append(
            "<tr>"
            f"<td>{row.rank}</td><td><strong>{html.escape(row.name)}</strong></td>"
            f"<td data-status='{row.com_status}'>{html.escape(status_sv(row.com_status))}"
            f"<br><code>{row.com_domain}</code></td>"
            f"<td data-status='{row.se_status}'>{html.escape(status_sv(row.se_status))}"
            f"<br><code>{row.se_domain}</code></td>"
            f"<td>{row.score:.1f}</td>"
            f"<td><a href='{row.bolagsverket_url}'>Bolagsverket</a></td>"
            f"<td><a href='{row.tmview_url}'>TMview</a></td>"
            "</tr>"
        )
    document = f"""<!doctype html>
<html lang="sv">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Brand Name Finder – resultat</title>
<style>
body{{font:16px system-ui;margin:0;background:#f6f7fb;color:#172033}}
main{{max-width:1180px;margin:auto;padding:32px 18px}}
.card{{background:white;border-radius:16px;padding:24px;box-shadow:0 8px 30px #17203312}}
.note{{background:#fff8df;border-left:4px solid #e6a700;padding:12px 16px}}
table{{border-collapse:collapse;width:100%;margin-top:20px}}th,td{{padding:11px;border-bottom:1px solid #e5e7eb;text-align:left}}
th{{position:sticky;top:0;background:#172033;color:white}}tr:hover{{background:#f3f6ff}}
code{{font-size:.88em}}a{{color:#3157c8}}[data-status=available]{{color:#126b3a}}[data-status=registered]{{color:#9b2730}}
@media(max-width:760px){{.card{{overflow-x:auto}}table{{min-width:900px}}}}
</style>
</head>
<body><main><h1>Brand Name Finder</h1>
<p>Kontrollerad {html.escape(rows[0].checked_at_utc)} · {len(rows)} namn</p>
<p class="note"><strong>Viktigt:</strong> status är en ögonblicksbild och reserverar
inte domänen. Slutkontrollera hos en registrar samt hos Bolagsverket och TMview.</p>
<div class="card"><table><thead><tr><th>#</th><th>Namn</th><th>.com</th><th>.se</th>
<th>Poäng</th><th>Bolagsnamn</th><th>Varumärke</th></tr></thead>
<tbody>{''.join(table_rows)}</tbody></table></div>
</main></body></html>"""
    path.write_text(document, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-names", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument("--custom", default="", help="Kommaavgränsade egna namn")
    parser.add_argument("--dry-run", action="store_true", help="Skippa nätverksuppslag")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 1 <= args.max_names <= 500:
        raise SystemExit("--max-names måste vara mellan 1 och 500")
    custom = [item.strip() for item in args.custom.split(",") if item.strip()]
    names = generate_names(args.seed, custom)
    rows = check_names(names, args.max_names, max(0.05, args.delay), args.dry_run)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(rows, args.output_dir / "results.csv")
    write_markdown(rows, args.output_dir / "RESULTS.md")
    write_html(rows, args.output_dir / "results.html")
    print(f"\nKlart: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
