"""Pydantic models for IP broadcast module structured LLM outputs"""

from pydantic import BaseModel


class HotTopicsResult(BaseModel):
    topics: list[str]


class TopicScriptResult(BaseModel):
    script: str


class MarketingCopyResult(BaseModel):
    copies: list[str]


class SocialMetaResult(BaseModel):
    title: str
    description: str
    hashtags: list[str]
