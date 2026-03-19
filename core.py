"""
core.py
=======
All start.gg API calls and stats computation.
No UI code lives here — import this from app.py or use it standalone.
"""

import re
import time
import csv
import datetime
import requests

STARTGG_URL = "https://api.start.gg/gql/alpha"

# ---------------------------------------------------------------------------
# GraphQL queries
# ---------------------------------------------------------------------------

EVENT_INFO_QUERY = """
query EventInfo($slug: String!) {
  event(slug: $slug) {
    id
    name
    numEntrants
    tournament {
      name
    }
  }
}
"""

EVENT_STANDINGS_QUERY = """
query EventStandings($eventId: ID!, $page: Int!, $perPage: Int!) {
  event(id: $eventId) {
    standings(query: { page: $page, perPage: $perPage }) {
      pageInfo {
        totalPages
      }
      nodes {
        placement
        entrant {
          id
          name
          participants {
            player {
              id
              gamerTag
            }
          }
        }
      }
    }
  }
}
"""

ENTRANT_SETS_QUERY = """
query EntrantSets($eventId: ID!, $entrantId: ID!, $page: Int!, $perPage: Int!) {
  event(id: $eventId) {
    sets(
      page: $page
      perPage: $perPage
      filters: { entrantIds: [$entrantId] }
    ) {
      pageInfo {
        totalPages
      }
      nodes {
        id
        winnerId
        displayScore
        fullRoundText
        slots {
          entrant {
            id
            name
            participants {
              player {
                id
                gamerTag
              }
            }
          }
        }
      }
    }
  }
}
"""

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def gql(query: str, variables: dict, api_key: str, retries: int = 3) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    for attempt in range(retries):
        try:
            resp = requests.post(
                STARTGG_URL,
                json={"query": query, "variables": variables},
                headers=headers,
                timeout=30,
            )
            if resp.status_code == 429:
                wait = 2 ** (attempt + 1)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data:
                raise RuntimeError(f"GraphQL errors: {data['errors']}")
            return data.get("data", {})
        except requests.RequestException as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise RuntimeError(f"API request failed after {retries} attempts: {e}")
    return {}


def paginate(query, variables, api_key, page_key_path, nodes_path, log=None):
    all_nodes = []
    page = 1
    total_pages = None
    while total_pages is None or page <= total_pages:
        vars_with_page = {**variables, "page": page}
        data = gql(query, vars_with_page, api_key)
        pi = data
        for key in page_key_path:
            pi = pi.get(key, {})
        total_pages = pi.get("totalPages", 1)
        nodes = data
        for key in nodes_path:
            nodes = nodes.get(key, [])
        all_nodes.extend(nodes or [])
        page += 1
        time.sleep(0.15)
    return all_nodes

# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

def parse_event_slug(url: str) -> str:
    """
    Extract event slug from a full start.gg URL or return as-is if already a slug.
    e.g. https://www.start.gg/tournament/big-fish-137/event/ult-singles
      -> tournament/big-fish-137/event/ult-singles
    """
    url = url.strip()
    # Strip protocol and domain
    url = re.sub(r"https?://(www\.)?start\.gg/", "", url)
    # Strip trailing slash
    url = url.strip("/")
    return url


def parse_players(raw: str) -> list:
    """
    Parse the players text box.
    Expected format, one player per line:
        Tag, ID
    e.g.
        Sparg0, 1234567
        Tweek, 7654321
    Returns list of {tag, id}
    """
    players = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            raise ValueError(f"Could not parse player line (expected 'Tag, ID'): '{line}'")
        tag = parts[0]
        pid = parts[1]
        players.append({"tag": tag, "id": pid})
    return players


def parse_event_urls(raw: str) -> list:
    """
    Parse the events text box — one URL or slug per line.
    Returns list of slug strings.
    """
    slugs = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        slugs.append(parse_event_slug(line))
    return slugs

# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def get_event_info(slug: str, api_key: str) -> dict:
    """Fetch event name, tournament name, entrant count from a slug."""
    data = gql(EVENT_INFO_QUERY, {"slug": slug}, api_key)
    event = data.get("event")
    if not event:
        raise RuntimeError(f"Event not found for slug: '{slug}'")
    return {
        "event_id": str(event["id"]),
        "event_name": event["name"],
        "num_entrants": event.get("numEntrants") or 0,
        "tournament_name": event["tournament"]["name"],
        "slug": slug,
    }


def get_event_standings(event_id: str, api_key: str) -> dict:
    """Return dict of entrant_id -> {placement, gamer_tag, player_id}."""
    nodes = paginate(
        EVENT_STANDINGS_QUERY,
        {"eventId": event_id, "perPage": 50},
        api_key,
        page_key_path=["event", "standings", "pageInfo"],
        nodes_path=["event", "standings", "nodes"],
    )
    standings = {}
    for node in nodes:
        entrant = node.get("entrant") or {}
        participants = entrant.get("participants") or []
        if not participants:
            continue
        player = participants[0].get("player") or {}
        standings[str(entrant["id"])] = {
            "placement": node["placement"],
            "gamer_tag": player.get("gamerTag", entrant.get("name", "?")),
            "player_id": str(player.get("id", "")),
        }
    return standings


def get_entrant_sets(event_id: str, entrant_id: str, api_key: str) -> list:
    return paginate(
        ENTRANT_SETS_QUERY,
        {"eventId": event_id, "entrantId": entrant_id, "perPage": 100},
        api_key,
        page_key_path=["event", "sets", "pageInfo"],
        nodes_path=["event", "sets", "nodes"],
    )


def find_entrant_id(standings: dict, player_id: str, tag: str) -> str | None:
    for eid, info in standings.items():
        if info["player_id"] == str(player_id):
            return eid
    for eid, info in standings.items():
        if info["gamer_tag"].lower() == tag.lower():
            return eid
    return None

# ---------------------------------------------------------------------------
# Stats computation
# ---------------------------------------------------------------------------

def compute_player_stats(player: dict, all_players: list, events: list, api_key: str,
                         standings_cache: dict = None, log=None) -> dict:
    """
    Compute full season stats for one player across all events.
    log: optional callable(str) for progress messages (e.g. GUI log function)
    """
    def emit(msg):
        if log:
            log(msg)

    pid = str(player["id"])
    tag = player["tag"]

    # Build pool lookups by both ID and tag (lowercased) for robust matching.
    # Tag matching is the reliable fallback since user-supplied IDs may be
    # user IDs rather than the player IDs the API returns in set data.
    pool_by_id  = {str(p["id"]): p["tag"] for p in all_players}
    pool_by_tag = {p["tag"].lower(): p["tag"] for p in all_players}

    def is_pool_player(api_pid: str, api_tag: str) -> bool:
        return api_pid in pool_by_id or api_tag.lower() in pool_by_tag

    placements = []
    total_sets_won = 0
    total_sets_played = 0

    # H2H keyed by canonical tag (from the pool list) for reliable lookup
    h2h = {
        p["tag"]: {"tag": p["tag"], "wins": 0, "losses": 0}
        for p in all_players if p["tag"].lower() != tag.lower()
    }
    wins   = {}  # opponent tag -> count (all opponents beaten, pool and non-pool)
    losses = {}  # opponent tag -> count (all opponents lost to, pool and non-pool)

    for event in events:
        eid = event["event_id"]
        entrants = event["num_entrants"]
        t_name = event["tournament_name"]
        e_name = event["event_name"]
        emit(f"  [{tag}] {e_name} @ {t_name}...")

        standings = standings_cache[eid] if standings_cache and eid in standings_cache else get_event_standings(eid, api_key)
        entrant_id = find_entrant_id(standings, pid, tag)

        if entrant_id is None:
            emit(f"    → did not attend")
            continue

        my_placement = standings[entrant_id]["placement"]
        placements.append({
            "tournament": t_name,
            "event": e_name,
            "placement": my_placement,
            "entrants": entrants,
        })

        sets = get_entrant_sets(eid, entrant_id, api_key)

        for s in sets:
            slots = s.get("slots") or []
            if len(slots) < 2:
                continue

            winner_id = str(s.get("winnerId") or "")
            i_won = winner_id == str(entrant_id)

            # Skip DQs — display score contains "DQ" for disqualified sets
            display_score = s.get("displayScore") or ""
            if "DQ" in display_score.upper():
                continue

            opp_entrant = None
            for slot in slots:
                e = slot.get("entrant") or {}
                if str(e.get("id", "")) != str(entrant_id):
                    opp_entrant = e

            if opp_entrant is None:
                continue

            opp_participants = opp_entrant.get("participants") or []
            if not opp_participants:
                continue
            opp_player = opp_participants[0].get("player") or {}
            opp_pid    = str(opp_player.get("id", ""))
            opp_tag    = opp_player.get("gamerTag", opp_entrant.get("name", "?"))

            total_sets_played += 1
            if i_won:
                total_sets_won += 1
                wins[opp_tag] = wins.get(opp_tag, 0) + 1
            else:
                losses[opp_tag] = losses.get(opp_tag, 0) + 1

            # H2H — match by tag (case-insensitive) as primary
            canonical_tag = pool_by_tag.get(opp_tag.lower())
            if canonical_tag and canonical_tag.lower() != tag.lower():
                emit(f"    [H2H] {'W' if i_won else 'L'} vs {canonical_tag}")
                if i_won:
                    h2h[canonical_tag]["wins"] += 1
                else:
                    h2h[canonical_tag]["losses"] += 1

        emit(f"    → position: {my_placement}, {len(sets)} sets found")

    placements.sort(key=lambda x: x["entrants"], reverse=True)
    win_pct = round((total_sets_won / total_sets_played) * 100, 1) if total_sets_played else 0.0

    return {
        "tag": tag,
        "player_id": pid,
        "placements": placements,
        "win_pct": win_pct,
        "sets_won": total_sets_won,
        "sets_played": total_sets_played,
        "h2h": h2h,
        "wins": wins,
        "losses": losses,
    }

# ---------------------------------------------------------------------------
# Output helpers — shared between CSV and HTML
# ---------------------------------------------------------------------------

def format_placement(p) -> str:
    if not isinstance(p, int):
        return str(p)
    suffixes = {1: "st", 2: "nd", 3: "rd"}
    return f"{p}{suffixes.get(p if p <= 20 else p % 10, 'th')}"


def format_name_list(counts: dict) -> str:
    if not counts:
        return ""
    sorted_items = sorted(counts.items(), key=lambda x: (-x[1], x[0].lower()))
    parts = [f"{name} (x{count})" if count > 1 else name for name, count in sorted_items]
    return ", ".join(parts)


def get_contenders_pct(stats: dict) -> float:
    w = sum(h["wins"] for h in stats["h2h"].values())
    l = sum(h["losses"] for h in stats["h2h"].values())
    total = w + l
    return round(w / total * 100, 1) if total else 0.0


def sort_stats(all_stats: list) -> list:
    """Sort players by overall win% descending — used consistently for all outputs."""
    return sorted(all_stats, key=lambda s: s["win_pct"], reverse=True)


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

def write_csv(all_stats: list, output_path: str):
    sorted_stats = sort_stats(all_stats)
    all_tags = [s["tag"] for s in sorted_stats]
    rows = []

    # H2H table — rows and columns both in contenders win% order
    rows.append(["H2H RECORDS"])
    rows.append(["Player"] + all_tags + ["Contenders W", "Contenders L", "Contenders W%"])
    for stats in sorted_stats:
        row = [stats["tag"]]
        c_w, c_l = 0, 0
        for other in sorted_stats:
            if other["tag"] == stats["tag"]:
                row.append("—")
            else:
                h = stats["h2h"].get(other["tag"], {"wins": 0, "losses": 0})
                w, l = h["wins"], h["losses"]
                c_w += w
                c_l += l
                # Space prefix prevents Excel auto-formatting as a date
                row.append(f" {w}-{l}" if (w + l) > 0 else " 0-0")
        total = c_w + c_l
        pct = f"{round(c_w / total * 100, 1)}%" if total else "N/A"
        row += [c_w, c_l, pct]
        rows.append(row)

    rows.append([])
    rows.append([])

    for stats in sorted_stats:
        tag = stats["tag"]
        c_w = sum(h["wins"] for h in stats["h2h"].values())
        c_l = sum(h["losses"] for h in stats["h2h"].values())
        c_total = c_w + c_l
        c_pct = f"{round(c_w / c_total * 100, 1)}%" if c_total else "N/A"

        rows.append([f"=== {tag} ==="])
        rows.append([
            "Overall Win %", f"{stats['win_pct']}%",
            "W", stats["sets_won"],
            "L", stats["sets_played"] - stats["sets_won"],
            "Total Sets", stats["sets_played"],
        ])
        rows.append([
            "Contenders Win %", c_pct,
            "Contenders W", c_w,
            "Contenders L", c_l,
            "Contenders Sets", c_total,
        ])
        rows.append([])

        rows.append(["PLACEMENTS (by event size)"])
        rows.append(["Placement", "Tournament", "Entrants"])
        for p in stats["placements"]:
            rows.append([format_placement(p["placement"]), p["tournament"], p["entrants"]])
        if stats["placements"]:
            avg = round(sum(p["placement"] for p in stats["placements"]) / len(stats["placements"]), 1)
            rows.append(["Average placement", avg])
        rows.append([])

        rows.append(["WINS"])
        rows.append([format_name_list(stats["wins"]) or "None"])
        rows.append([])

        rows.append(["LOSSES"])
        rows.append([format_name_list(stats["losses"]) or "None"])
        rows.append([])
        rows.append([])

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


# ---------------------------------------------------------------------------
# HTML output
# ---------------------------------------------------------------------------

def _pct_colour(pct: float) -> str:
    """Green for winning record, red for losing, neutral at 50%."""
    if pct >= 50:
        intensity = int((pct - 50) / 50 * 120)
        return f"rgb({200 - intensity},{230},{200 - intensity})"
    else:
        intensity = int((50 - pct) / 50 * 120)
        return f"rgb({230},{200 - intensity},{200 - intensity})"


def write_html(all_stats: list, output_path: str):
    sorted_stats = sort_stats(all_stats)
    all_tags = [s["tag"] for s in sorted_stats]
    generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # H2H table
    h2h_header = "".join(f"<th>{t}</th>" for t in all_tags)
    h2h_body = ""
    for stats in sorted_stats:
        c_w, c_l = 0, 0
        cells = ""
        for other in sorted_stats:
            if other["tag"] == stats["tag"]:
                cells += '<td class="self">—</td>'
            else:
                h = stats["h2h"].get(other["tag"], {"wins": 0, "losses": 0})
                w, l = h["wins"], h["losses"]
                c_w += w
                c_l += l
                total = w + l
                pct = w / total * 100 if total else 50
                colour = _pct_colour(pct)
                label = f"{w}-{l}" if total > 0 else "—"
                cells += f'<td style="background:{colour}">{label}</td>'
        total = c_w + c_l
        pct_str = f"{round(c_w / total * 100, 1)}%" if total else "N/A"
        h2h_body += f"<tr><td class='name'>{stats['tag']}</td>{cells}<td class='sum'>{c_w}-{c_l}</td><td class='sum'>{pct_str}</td></tr>\n"

    # Per-player cards
    cards = ""
    for stats in sorted_stats:
        tag = stats["tag"]
        c_w = sum(h["wins"] for h in stats["h2h"].values())
        c_l = sum(h["losses"] for h in stats["h2h"].values())
        c_total = c_w + c_l
        c_pct = f"{round(c_w / c_total * 100, 1)}%" if c_total else "N/A"

        placement_rows = "".join(
            f"<tr><td>{format_placement(p['placement'])}</td><td>{p['tournament']}</td><td>{p['entrants']}</td></tr>"
            for p in stats["placements"]
        )
        avg_row = ""
        if stats["placements"]:
            avg = round(sum(p["placement"] for p in stats["placements"]) / len(stats["placements"]), 1)
            avg_row = f'<tr class="avg"><td colspan="1">Average placement: {avg}</tr>'

        cards += f"""
        <div class="card">
            <h2>{tag}</h2>
            <div class="records">
                <div class="rec-box">
                    <div class="rec-label">Overall Win %</div>
                    <div class="rec-val">{stats['win_pct']}%</div>
                    <div class="rec-sub">{stats['sets_won']}W – {stats['sets_played'] - stats['sets_won']}L &nbsp;({stats['sets_played']} sets)</div>
                </div>
                <div class="rec-box">
                    <div class="rec-label">Contenders Win %</div>
                    <div class="rec-val">{c_pct}</div>
                    <div class="rec-sub">{c_w}W – {c_l}L &nbsp;({c_total} sets)</div>
                </div>
            </div>
            <h3>Placements</h3>
            <table class="dt">
                <thead><tr><th>Placement</th><th>Tournament</th><th>Entrants</th></tr></thead>
                <tbody>{placement_rows}{avg_row}</tbody>
            </table>
            <div class="wl">
                <div class="wl-box wins">
                    <h3>Wins</h3>
                    <p>{format_name_list(stats['wins']) or 'None'}</p>
                </div>
                <div class="wl-box losses">
                    <h3>Losses</h3>
                    <p>{format_name_list(stats['losses']) or 'None'}</p>
                </div>
            </div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Season Recap</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f0f0f;color:#e8e8e8;padding:32px 24px}}
h1{{font-size:1.8rem;font-weight:700;margin-bottom:4px}}
.sub{{color:#666;font-size:0.85rem;margin-bottom:40px}}
h2{{font-size:1.25rem;font-weight:700;margin-bottom:16px;color:#fff}}
h3{{font-size:0.8rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#888;margin-bottom:10px}}
.section-label{{font-size:.85rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#555;margin:48px 0 14px}}

/* H2H */
.h2h-wrap{{overflow-x:auto;margin-bottom:48px}}
table.h2h{{border-collapse:collapse;font-size:.8rem;white-space:nowrap}}
table.h2h th{{background:#1c1c1c;padding:7px 11px;text-align:center;font-weight:600;color:#bbb;border:1px solid #2a2a2a}}
table.h2h th:first-child{{text-align:left;min-width:90px}}
table.h2h td{{padding:6px 11px;text-align:center;border:1px solid #2a2a2a;font-weight:600;font-size:.8rem;color:#111}}
table.h2h td.name{{background:#1c1c1c;color:#e8e8e8;text-align:left}}
table.h2h td.self{{background:#222;color:#444}}
table.h2h td.sum{{background:#1c1c1c;color:#e8e8e8}}

/* Cards */
.card{{background:#1a1a1a;border:1px solid #272727;border-radius:10px;padding:28px;margin-bottom:20px}}
.records{{display:flex;gap:14px;margin-bottom:24px;flex-wrap:wrap}}
.rec-box{{background:#202020;border:1px solid #2e2e2e;border-radius:8px;padding:14px 22px;min-width:170px}}
.rec-label{{font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;color:#666;margin-bottom:3px}}
.rec-val{{font-size:1.8rem;font-weight:700;color:#fff;line-height:1;margin-bottom:3px}}
.rec-sub{{font-size:.78rem;color:#666}}

/* Data tables */
table.dt{{border-collapse:collapse;width:100%;font-size:.84rem;margin-bottom:20px}}
table.dt th{{background:#202020;padding:7px 12px;text-align:left;font-weight:600;color:#999;border-bottom:1px solid #2e2e2e}}
table.dt td{{padding:6px 12px;border-bottom:1px solid #1e1e1e;color:#ccc}}
table.dt tr.avg td{{color:#666;font-style:italic;border-top:1px solid #2a2a2a}}

/* Wins / losses */
.wl{{display:flex;gap:14px;flex-wrap:wrap;margin-top:4px}}
.wl-box{{flex:1;min-width:220px;background:#202020;border:1px solid #2e2e2e;border-radius:8px;padding:14px 18px}}
.wl-box p{{font-size:.84rem;color:#bbb;line-height:1.65}}
.wins h3{{color:#6dbf7e}}
.losses h3{{color:#cf6679}}
</style>
</head>
<body>
<h1>Season Recap</h1>
<p class="sub">Generated {generated}</p>

<p class="section-label">Head to Head</p>
<div class="h2h-wrap">
  <table class="h2h">
    <thead><tr><th>Player</th>{h2h_header}<th>Record</th><th>W%</th></tr></thead>
    <tbody>{h2h_body}</tbody>
  </table>
</div>

<p class="section-label">Player Recaps</p>
{cards}
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(api_key: str, event_urls: str, players_raw: str, output_path: str, log=None):
    import os
    log_lines = []

    def emit(msg):
        log_lines.append(msg)
        if log:
            log(msg)

    def flush_log():
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log.txt")
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("\n".join(log_lines))
        except Exception as e:
            if log:
                log(f"Warning: could not write log.txt: {e}")

    emit("Parsing inputs...")
    players = parse_players(players_raw)
    slugs = parse_event_urls(event_urls)

    if not players:
        raise ValueError("No players found. Check the players box format.")
    if not slugs:
        raise ValueError("No event URLs found.")

    emit(f"Found {len(players)} players and {len(slugs)} events.\n")

    emit("Fetching event info...")
    events = []
    for slug in slugs:
        emit(f"  {slug}")
        info = get_event_info(slug, api_key)
        emit(f"    → {info['event_name']} @ {info['tournament_name']} ({info['num_entrants']} entrants)")
        events.append(info)

    emit(f"\nFetching standings for {len(events)} events...")
    standings_cache = {}
    for event in events:
        eid = event["event_id"]
        emit(f"  Standings: {event['event_name']} @ {event['tournament_name']}...")
        standings_cache[eid] = get_event_standings(eid, api_key)
        emit(f"    → {len(standings_cache[eid])} entrants loaded")

    emit(f"\nProcessing {len(players)} players...\n")

    all_stats = []
    for i, player in enumerate(players, 1):
        emit(f"[{i}/{len(players)}] {player['tag']}")
        stats = compute_player_stats(player, players, events, api_key,
                                     standings_cache=standings_cache, log=emit)
        all_stats.append(stats)
        emit(f"  Done — {stats['sets_played']} sets, {stats['win_pct']}% win rate\n")

    base = os.path.splitext(output_path)[0]
    csv_path  = base + ".csv"
    html_path = base + ".html"

    emit("Writing CSV...")
    write_csv(all_stats, csv_path)
    emit("Writing HTML...")
    write_html(all_stats, html_path)
    emit(f"\nCSV:  {csv_path}")
    emit(f"HTML: {html_path}")
    emit("Done!")
    flush_log()