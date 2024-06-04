# MIT License
#
# Copyright (c) 2023 Rendy Arya Kemal
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations
import json
from datetime import datetime, timedelta
import os
import time
from typing import Any, Generic, Type, TypeVar
from typing_extensions import TypedDict

import httpx
from rich.console import Console
from rich.table import Table

T = TypeVar("T")


class BaseResponse(TypedDict, Generic[T]):
    status: int
    message: str
    data: T


class ScoreHistory(TypedDict):
    period: str
    semester: int
    scores: list[CourseScore]


class CourseScore(TypedDict):
    code: str
    curriculum: str
    name: str
    credits: int
    status: str
    final_score: str
    final_index: str
    class_id: str


class CourseDetailScore(TypedDict):
    name: str
    weight: str
    score: str
    final: str


with open("config.json", "r") as f:
    config = json.load(f)

    SLEEP_DURATION = config["sleep_duration"]
    DISCORD_WEBHOOK = config["discord_webhook"]
    USERNAME = config["username"]
    PASSWORD = config["password"]
    DISCORD_UID = config["discord_uid"]


class SIAKSession:
    BASE_URL = "https://siak-rest.up.railway.app"

    def __init__(self, username: str, passwd: str):
        self._username = username
        self._passwd = passwd
        self._client = httpx.Client()
        self._token = {}

    def login(self):
        form = {
            "username": self._username,
            "password": self._passwd,
        }
        resp = self.request(
            "POST",
            "/login",
            data=form,
        )

        if resp["status"] != 200:
            raise Exception("Failed to log in.")

        self._token = resp["data"]

    def request(
        self,
        method: str,
        path: str,
        *,
        data: dict | None = None,
        as_: Type[T] | None = None,
    ) -> T | Any:
        url = self.BASE_URL + path
        response = self._client.request(
            method,
            url,
            json=data,
            headers={
                "X-Mojavi": self._token.get("mojavi", ""),
                "X-SiakNG-CC": self._token.get("siakng_cc", ""),
            },
        )
        print(response.text)

        res = response.json()
        if as_:
            return as_(res)

        return res


con = Console()


def get_score(session: SIAKSession, class_id: str):
    resp: BaseResponse[list[CourseDetailScore]] = session.request(
        "GET", "/academic/course/" + class_id
    )

    scores = resp["data"]
    if len(scores) == 1:
        return {}

    return {score["name"]: [score["weight"], score["score"]] for score in scores}


def get_scores(sess: SIAKSession):
    data: BaseResponse[list[ScoreHistory]] = sess.request("GET", "/academic/history")
    scores: dict[str, dict[str, list[str]]] = {}

    for subject_data in data["data"][-1]["scores"]:
        subject = subject_data["name"]
        score = subject_data["final_score"]
        score_index = subject_data["final_index"]

        subject_score = get_score(sess, subject_data["class_id"])
        subject_score["final"] = [score, score_index]

        scores[subject] = subject_score

    return scores


def send_webhook(modified: list[str], scores: dict[str, dict[str, list[str]]]):
    message = ""
    for subject, score in scores.items():
        score = score_str(score)
        message += f"{subject}: {score}\n"

    if DISCORD_WEBHOOK:
        httpx.post(
            DISCORD_WEBHOOK,
            json={
                "content": f"<@{DISCORD_UID}>",
                "embeds": [
                    {
                        "title": "SIAK Score Modified",
                        "description": f"Score changed: {', '.join(modified)}\n```{message.strip()}```",
                    }
                ],
            },
        )


def score_str(score: dict[str, list[str]]):
    s = []
    for component in score.values():
        if "." in component[1]:
            s.append(f'{component[1].split(".")[0]:>2}')
        else:
            s.append(component[1].title())

    return " | ".join(s)


def main():
    sess = SIAKSession(USERNAME, PASSWORD)

    last_run = {}
    if os.path.exists("last.json"):
        with open("last.json", "r") as f:
            last_run: dict = json.load(f)

    last_dt = datetime.min
    while True:
        try:
            if abs(last_dt - datetime.now()) > timedelta(minutes=30):
                sess._client._cookies.clear()
                sess.login()

            con.clear()
            modified = []
            scores = get_scores(sess)
        except Exception:
            con.print_exception()
            con.print("[red]ERROR: Failed to fetch, retrying in 5s[/]")
            time.sleep(5)
            continue

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
            send_webhook(modified, scores)

        with open("last.json", "w") as f:
            json.dump(last_run, f)

        now = datetime.now()
        next_dt = now + timedelta(seconds=SLEEP_DURATION)
        last_dt = now

        con.print(table)
        con.print("[bold blue]Fetch time:[/] " + now.isoformat(" ", timespec="seconds"))
        con.print("[bold red]Next:[/] " + next_dt.isoformat(" ", timespec="seconds"))
        con.print(f"Automatic refresh every {SLEEP_DURATION}s")

        time.sleep(SLEEP_DURATION)


try:
    main()
except KeyboardInterrupt:
    print("Exited by request")
