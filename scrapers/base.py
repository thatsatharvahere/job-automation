from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Job:
    id: str
    platform: str
    title: str
    company: str
    location: str
    url: str
    description: str
    posted_at: str  # ISO 8601

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "platform": self.platform,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "url": self.url,
            "description": self.description,
            "posted_at": self.posted_at,
        }
