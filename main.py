import asyncio
import os
from datetime import datetime, timedelta
from typing import Dict, List

import httpx
from siak_track.session import SIAKSession
from rich.console import Console
from rich.table import Table
from dotenv import load_dotenv

load_dotenv()

SLEEP_DURATION = 60 * 60


con = Console()


async def get_score(session: SIAKSession, href: str):
    _, soup = await session.request("GET", "/main/Academic/" + href)
    tables = soup.select("#ti_m1 table")
    if len(tables) == 1:
        return {}

    score_tables = tables[-1]
    scores = {}
    for row in score_tables.select("tr")[1:]:
        tds = row.select("td")
        name = tds[0].text
        scores[name] = list(map(lambda x: x.text, tds[1:]))

    return scores


async def get_scores(sess: SIAKSession):
    _, soup = await sess.request("GET", "/main/Academic/HistoryByTerm")
    scores: Dict[str, Dict[str, List[str]]] = {}
    rows = soup.select("table.box tr")[2:]

    semester = 1
    for row in rows:
        if "class" not in row.attrs:
            semester += 1
            continue

        if semester == 3:
            tds = row.select("td")
            subject = tds[3].text
            score = list(map(lambda x: x.text, tds[7:-1]))
            if len(score) == 1:
                score = score * 2

            href = tds[-1].find("a").attrs["href"]
            subject_score = await get_score(sess, href)
            subject_score["final"] = score

            scores[subject] = subject_score

    return scores


def score_str(score: Dict[str, List[str]]):
    s = []
    for component in score.values():
        if "." in component[1]:
            s.append(f'{component[1].split(".")[0]:>2}')
        else:
            s.append(component[1].title())

    return " | ".join(s)


async def main():
    sess = SIAKSession(os.getenv("SIAK_USERNAME"), os.getenv("SIAK_PASSWORD"))

    last_run = {}
    while True:
        sess._client._cookies.clear()
        await sess.login()
        con.clear()
        modified = []
        scores = await get_scores(sess)
        table = Table(title="Scores")
        table.add_column("Subject")
        table.add_column("Scores")
        for subject, score in scores.items():
            score = score_str(score)
            table.add_row(subject, score)

            if last_run.get(subject) != score:
                modified.append(subject)
            last_run[subject] = score

        if modified:
            message = ""
            for subject, score in scores.items():
                score = score_str(score)
                message += f"{subject}: {score}\n"

            httpx.post(
                os.getenv("WEBHOOK_URL"),
                json={
                    "embeds": [
                        {
                            "title": "SIAK Score Modified",
                            "description": f"Score changed: {', '.join(modified)}\n```{message.strip()}```",
                        }
                    ]
                },
            )

        now = datetime.now()
        next_dt = now + timedelta(seconds=SLEEP_DURATION)

        con.print(table)
        con.print("[bold blue]Fetch time:[/] " + now.isoformat(" ", timespec="seconds"))
        con.print("[bold red]Next:[/] " + next_dt.isoformat(" ", timespec="seconds"))
        await asyncio.sleep(SLEEP_DURATION)


loop = asyncio.new_event_loop()
loop.run_until_complete(main())
