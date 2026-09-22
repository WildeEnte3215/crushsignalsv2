from typing import List, Literal
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(Strict):
    url: str
    title: str
    primary: bool


class Claim(Strict):
    id: str
    statement: str
    source_urls: List[str]


class Research(Strict):
    summary: str
    sources: List[Source] = Field(min_length=2)
    claims: List[Claim] = Field(min_length=2)
    uncertainties: List[str]


class Edit(Strict):
    motion: Literal[
        "zoom_in",
        "zoom_out",
        "pan_left",
        "pan_right",
        "punch",
        "freeze",
        "none",
    ]
    transition: Literal[
        "cut",
        "fade",
        "dip_black",
    ]
    overlay: Literal[
        "none",
        "label",
        "arrow",
        "circle",
    ]
    label: str = Field(max_length=32)
    target: str
    sfx: Literal[
        "none",
        "whoosh",
        "click",
        "pop",
        "impact",
        "riser",
    ]


class Scene(Strict):
    id: str = Field(
        pattern=r"^[a-z][a-z0-9_]{0,30}$"
    )
    narration: str
    claim_ids: List[str]
    visual_goal: str
    search_queries: List[str] = Field(
        min_length=1,
        max_length=3,
    )
    diagram_nodes: List[str] = Field(
        min_length=2,
        max_length=3,
    )
    prefer_diagram: bool
    edit: Edit


class Plan(Strict):
    topic: str
    hook: str
    title: str = Field(max_length=90)
    description: str
    scenes: List[Scene] = Field(
        min_length=4,
        max_length=9,
    )


class Verdict(Strict):
    passed: bool
    checked_scene_ids: List[str]
    issues: List[str]
    evidence_urls: List[str]


class Assessment(Strict):
    relevance: float = Field(
        ge=0,
        le=1,
    )
    visibility: float = Field(
        ge=0,
        le=1,
    )
    vertical: float = Field(
        ge=0,
        le=1,
    )
    quality: float = Field(
        ge=0,
        le=1,
    )
    reject: bool
    reason: str
    crop: Literal[
        "focus",
        "contain",
    ]
    focus_x: float = Field(
        ge=0,
        le=1,
    )
    focus_y: float = Field(
        ge=0,
        le=1,
    )
    target_visible: bool
    target_confidence: float = Field(
        ge=0,
        le=1,
    )
    target_x: float = Field(
        ge=0,
        le=1,
    )
    target_y: float = Field(
        ge=0,
        le=1,
    )
    target_radius: float = Field(
        ge=0.01,
        le=0.25,
    )


class Queries(Strict):
    queries: List[str] = Field(
        min_length=1,
        max_length=2,
    )


class Topic(Strict):
    topic: str


class Review(Strict):
    passed: bool
    issues: List[str]


class ScamShort(Strict):
    youtube_title: str = Field(
        min_length=10,
        max_length=90,
    )

    category_label: str = Field(
        min_length=3,
        max_length=30,
    )

    hook: str = Field(
        min_length=8,
        max_length=90,
    )

    points: List[str] = Field(
        min_length=3,
        max_length=5,
    )

    cta: str = Field(
        max_length=80,
    )

    background_search_query: str = Field(
        min_length=3,
        max_length=80,
    )

    estimated_duration_seconds: float = Field(
        ge=8,
        le=18,
    )


class RelationshipShort(Strict):
    youtube_title: str = Field(
        min_length=10,
        max_length=90,
    )

    category_label: Literal[
        "FOR GIRLS",
        "FOR BOYS",
        "CRUSH FACT",
        "DATING FACT",
        "RELATIONSHIP FACT",
    ]

    hook: str = Field(
        min_length=8,
        max_length=90,
    )

    points: List[str] = Field(
        min_length=3,
        max_length=5,
    )

    cta: str = Field(
        max_length=80,
    )

    background_search_query: str = Field(
        min_length=3,
        max_length=80,
    )

    estimated_duration_seconds: float = Field(
        ge=8,
        le=18,
    )