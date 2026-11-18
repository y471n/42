"""Structured model outputs and graph state."""

import operator
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field


class Topic(BaseModel):
    topic: Literal["career", "relationships", "identity", "change", "meaning", "ethics",
                   "free_will", "knowledge", "reality", "consciousness", "death", "politics",
                   "religion", "general"]


class PathPlan(BaseModel):
    kind: Literal["decision", "general", "clarification"]
    option_a: str
    option_b: str
    question: str


class LocalAssessment(BaseModel):
    relevant_source_ids: list[str]
    reason: str


class Citation(BaseModel):
    source_id: str
    quote: str


class Letter(BaseModel):
    text: str = Field(description="A fictional letter from one possible future")
    citations: list[Citation] = Field(description="Exact excerpts copied from provided source passages, or an empty list")


class Critic(BaseModel):
    needs_revision: bool
    issues: list[str] = Field(description="Unsupported claims, invented facts, unbalanced assumptions, or other issues")


class Perspective(BaseModel):
    text: str = Field(description="An AI-generated philosophical interpretation, not a quotation")
    citations: list[Citation] = Field(description="Exact excerpts copied from provided source passages")


class Moderator(BaseModel):
    ready: bool = Field(description="True when key agreements and unresolved tensions have been distilled")
    summary: str


class Reflection(BaseModel):
    shared_values: list[str]
    questions: list[str]
    experiment: str = Field(description="A small optional experiment, not a prescribed decision")


class Source(TypedDict):
    id: str
    title: str
    url: str
    content: str


class ResearchState(TypedDict, total=False):
    dilemma: str
    option_a: str
    option_b: str
    topic: str
    research_round: int
    found: Annotated[list[dict], operator.add]
    trace_queries: Annotated[list[str], operator.add]
    local_candidates: list[Source]
    local_authors: dict[str, list[str]]
    local_evidence: list[Source]
    local_reason: str
    local_sufficient: bool
    evidence: list[Source]
    thinkers: list[str]
    warnings: list[str]


class MuseumState(TypedDict, total=False):
    dilemma: str
    option_a: str
    option_b: str
    clarification: str
    clarification_question: str
    paths_clear: bool
    question_kind: str
    entry_action: str
    review_action: str
    follow_up_question: str
    follow_up_needs_research: bool
    follow_up_return_to_review: bool
    messages: Annotated[list[dict], operator.add]
    previous_turns: list[dict]
    original_question: str
    topic: str
    research_round: int
    found: Annotated[list[dict], operator.add]
    trace_queries: Annotated[list[str], operator.add]
    local_candidates: list[Source]
    local_authors: dict[str, list[str]]
    local_evidence: list[Source]
    local_reason: str
    local_sufficient: bool
    evidence: list[Source]
    thinkers: list[str]
    warnings: list[str]
    discussion_round: int
    discussion_index: int
    discussion_turns: Annotated[list[dict], operator.add]
    discussion_ready: bool
    discussion_limit_reached: bool
    distillation: str
    future_a: dict
    future_b: dict
    critique: dict
    automatic_revision: bool
    revision_round: int
    review_notes: str
    reflection: dict
    exhibit: str
    approved: bool


class FutureState(TypedDict, total=False):
    dilemma: str
    option: str
    other_option: str
    evidence: list[Source]
    review_notes: str
    passages: list[dict]
    distillation: str
    letter: dict
