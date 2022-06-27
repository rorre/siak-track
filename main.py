import asyncio
from datetime import datetime, timedelta
from typing import Dict, List
from siak_track.session import SIAKSession
from rich.console import Console
from rich.table import Table
from notifypy import Notify
import sys

SLEEP_DURATION = 30 * 60


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

        if semester == 2:
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
            s.append("".join(map(lambda x: x[0], component[1].title().split(" "))))

    return " | ".join(s)


async def main():
    sess = SIAKSession(sys.argv[1], sys.argv[2])
    await sess.login()

    last_run = {}
    while True:
        con.clear()
        modified = []
        scores = await get_scores(sess)
        table = Table(title="Scores")
        table.add_column("Subject")
        table.add_column("Scores")
        for subject, score in scores.items():
            score = score_str(score)
            table.add_row(subject, score)

            if subject in last_run and last_run[subject] != score:
                modified.append(subject)
            last_run[subject] = score

        if modified:
            notification = Notify()
            notification.title = "Score Modified"
            notification.message = "\n".join(modified)
            notification.send(block=False)

        now = datetime.now()
        next_dt = now + timedelta(seconds=SLEEP_DURATION)

        con.print(table)
        con.print("[bold blue]Fetch time:[/] " + now.isoformat(" ", timespec="seconds"))
        con.print("[bold red]Next:[/] " + next_dt.isoformat(" ", timespec="seconds"))
        await asyncio.sleep(30 * 60)


loop = asyncio.new_event_loop()
loop.run_until_complete(main())