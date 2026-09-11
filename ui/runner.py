"""Runs the agent in a background thread so the UI stays responsive (browse matches while it works)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import streamlit as st

from jobpilot.agent.orchestrator import JobPilotAgent
from jobpilot.schemas import AgentEvent, CandidateProfile, MatchResult, RunConfig, RunReport, SearchPreferences
from jobpilot.storage.db import Database


@dataclass
class RunHandle:
    thread: threading.Thread
    stop: threading.Event
    events: list[AgentEvent] = field(default_factory=list)
    agent: Optional[JobPilotAgent] = None
    report: Optional[RunReport] = None
    matches: list[MatchResult] = field(default_factory=list)
    error: str = ""
    started: float = field(default_factory=time.time)
    finished: Optional[float] = None

    @property
    def running(self) -> bool:
        return self.thread.is_alive()

    @property
    def live_report(self) -> Optional[RunReport]:
        if self.report is not None:
            return self.report
        return self.agent.report if self.agent else None


@st.cache_resource(show_spinner=False)
def _registry() -> dict[str, RunHandle]:
    return {}


def current() -> Optional[RunHandle]:
    return _registry().get("current")


def start(db: Database, *, api_key: str, model: str, embed_model: str, profile: CandidateProfile,
          prefs: SearchPreferences, config: RunConfig) -> RunHandle:
    existing = current()
    if existing and existing.running:
        return existing
    stop = threading.Event()
    handle = RunHandle(thread=threading.Thread(), stop=stop)

    def _on_event(ev: AgentEvent) -> None:
        handle.events.append(ev)
        if len(handle.events) > 600:
            del handle.events[:100]

    def _target() -> None:
        try:
            agent = JobPilotAgent(db, api_key=api_key, model=model, embed_model=embed_model, config=config.model_copy(),
                                  on_event=_on_event, should_stop=stop.is_set)
            handle.agent = agent
            handle.report, handle.matches = agent.run(profile.model_copy(deep=True), prefs.model_copy(deep=True))
        except Exception as exc:  # surfaced in the UI
            handle.error = f"{type(exc).__name__}: {exc}"
        finally:
            handle.finished = time.time()

    handle.thread = threading.Thread(target=_target, name="jobpilot-run", daemon=True)
    _registry()["current"] = handle
    handle.thread.start()
    return handle
