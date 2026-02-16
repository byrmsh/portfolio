from __future__ import annotations

from datetime import date, datetime
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

StatSource: TypeAlias = Literal[
    "github",
    "anki",
    "ytmusic",
    "obsidian",
    "writing",
    "cluster",
]
ActivitySource: TypeAlias = Literal["github", "anki"]
ServiceStatus: TypeAlias = Literal["up", "degraded", "down"]


class BaseSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActivityCell(BaseSchema):
    date: date
    level: int = Field(ge=0, le=4)
    count: int = Field(ge=0)


class ActivitySeries(BaseSchema):
    source: ActivitySource
    label: str
    cells: list[ActivityCell]
    streak: int | None = Field(default=None, ge=0)
    updatedAt: datetime


class ActivityMonitorData(BaseSchema):
    github: ActivitySeries
    anki: ActivitySeries


class SavedLyricNote(BaseSchema):
    id: str
    source: Literal["ytmusic"]
    title: str
    artist: str
    noteUrl: str
    albumArtUrl: str | None = None
    savedAt: datetime


class YtMusicBackgroundNote(BaseSchema):
    title: str
    body: str


class YtMusicBackground(BaseSchema):
    tldr: str
    notes: list[YtMusicBackgroundNote]


class YtMusicVocabularyItem(BaseSchema):
    id: str
    term: str
    exampleDe: str
    literalEn: str
    meaningEn: str
    exampleEn: str
    memoryHint: str | None = None
    cefr: str | None = None
    usage: list[str] | None = None


class YtMusicAnalysis(BaseSchema):
    id: str
    source: Literal["ytmusic"]
    title: str
    artist: str
    album: str | None = None
    albumArtUrl: str | None = None
    trackUrl: str | None = None
    lyricsUrl: str | None = None
    background: YtMusicBackground
    vocabulary: list[YtMusicVocabularyItem]
    updatedAt: datetime


class WritingPost(BaseSchema):
    id: str
    source: Literal["writing"]
    title: str
    description: str
    href: str
    tags: list[str]
    publishedAt: datetime


class KnowledgeGraphSnapshot(BaseSchema):
    source: Literal["obsidian"]
    nodes: int = Field(ge=0)
    edges: int = Field(ge=0)
    summary: str
    updatedAt: datetime


class JobLead(BaseSchema):
    id: str
    source: Literal["public"]
    title: str
    summary: str
    tags: list[str]
    publishedAt: datetime
    capturedAt: datetime
    href: str | None = None
    companyName: str | None = None
    location: str | None = None
    remote: bool | None = None
    jobTypes: list[str] | None = None


class JobRedisRecord(JobLead):
    description: str


class ServiceHealth(BaseSchema):
    id: str
    name: str
    detail: str
    status: ServiceStatus
    pulse: bool
    updatedAt: datetime


class SystemHealthSnapshot(BaseSchema):
    source: Literal["cluster"]
    namespace: str
    uptimeRatio30d: float = Field(ge=0.0, le=1.0)
    services: list[ServiceHealth]
    updatedAt: datetime


class DashboardSnapshot(BaseSchema):
    activityMonitor: ActivityMonitorData
    savedLyric: SavedLyricNote | None
    writing: list[WritingPost]
    knowledgeGraph: KnowledgeGraphSnapshot
    latestJob: JobLead | None
    systemHealth: SystemHealthSnapshot
    updatedAt: datetime


StatRedisRecord = (
    ActivitySeries
    | SavedLyricNote
    | YtMusicAnalysis
    | WritingPost
    | KnowledgeGraphSnapshot
    | SystemHealthSnapshot
)

DashboardSnapshotValidator = TypeAdapter(DashboardSnapshot)
JobRedisRecordValidator = TypeAdapter(JobRedisRecord)
StatRedisRecordValidator = TypeAdapter(StatRedisRecord)


def validate_dashboard_snapshot(payload: object) -> DashboardSnapshot:
    return DashboardSnapshotValidator.validate_python(payload)


def validate_job_redis_record(payload: object) -> JobRedisRecord:
    return JobRedisRecordValidator.validate_python(payload)


def validate_stat_redis_record(payload: object) -> StatRedisRecord:
    return StatRedisRecordValidator.validate_python(payload)


class RedisKeys:
    INDEX_WRITING_RECENT = "index:writing:recent"
    INDEX_LYRICS_RECENT = "index:ytmusic:saved"
    INDEX_LYRICS_ANALYSIS_PENDING = "index:ytmusic:analysis:pending"

    @staticmethod
    def stat(source: StatSource, item_id: str | int) -> str:
        return f"stat:{source}:{item_id}"

    @staticmethod
    def stat_field(source: StatSource, item_id: str | int, field: str) -> str:
        return f"stat:{source}:{item_id}:{field}"
