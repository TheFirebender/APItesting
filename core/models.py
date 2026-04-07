"""core/models.py — модели данных."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Request:
    id: str
    name: str
    method: str = "GET"
    url: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    params: Dict[str, str] = field(default_factory=dict)
    body_format: str = "none"   # none | json | text | xml | form
    body: Optional[str] = None
    pre_script: Optional[str] = None
    test_script: Optional[str] = None
    description: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "Request":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Folder:
    id: str
    name: str
    requests: List[Request] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name,
                "requests": [r.to_dict() for r in self.requests]}

    @classmethod
    def from_dict(cls, d: dict) -> "Folder":
        return cls(id=d["id"], name=d["name"],
                   requests=[Request.from_dict(r) for r in d.get("requests", [])])


@dataclass
class Collection:
    id: str
    name: str
    description: str = ""
    variables: Dict[str, str] = field(default_factory=dict)
    folders: List[Folder] = field(default_factory=list)
    requests: List[Request] = field(default_factory=list)

    def all_requests(self) -> List[Request]:
        result = list(self.requests)
        for f in self.folders:
            result.extend(f.requests)
        return result

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "variables": self.variables,
            "folders": [f.to_dict() for f in self.folders],
            "requests": [r.to_dict() for r in self.requests],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Collection":
        return cls(
            id=d.get("id", ""), name=d.get("name", ""),
            description=d.get("description", ""),
            variables=d.get("variables", {}),
            folders=[Folder.from_dict(f) for f in d.get("folders", [])],
            requests=[Request.from_dict(r) for r in d.get("requests", [])],
        )


@dataclass
class Environment:
    id: str
    name: str
    variables: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "variables": self.variables}

    @classmethod
    def from_dict(cls, d: dict) -> "Environment":
        return cls(id=d["id"], name=d["name"], variables=d.get("variables", {}))


@dataclass
class Response:
    status_code: int
    status_text: str
    headers: Dict[str, str]
    body: str
    elapsed_ms: float
    body_size: int
    url: str
    method: str

    @property
    def color(self) -> str:
        if 200 <= self.status_code < 300: return "green"
        if 300 <= self.status_code < 400: return "blue"
        if 400 <= self.status_code < 500: return "yellow"
        return "red"

    @property
    def is_json(self) -> bool:
        ct = self.headers.get("content-type", "")
        return "json" in ct or self.body.strip().startswith(("{", "["))

    def to_dict(self) -> dict:
        return {**self.__dict__, "color": self.color, "is_json": self.is_json}


@dataclass
class Assertion:
    name: str
    passed: bool
    message: Optional[str] = None

    def to_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "message": self.message}


@dataclass
class Result:
    request_id: str
    request_name: str
    method: str
    url: str
    response: Optional[Response]
    assertions: List[Assertion] = field(default_factory=list)
    error: Optional[str] = None
    pre_error: Optional[str] = None
    test_error: Optional[str] = None

    @property
    def passed(self) -> bool:
        return not self.error and all(a.passed for a in self.assertions)

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "request_name": self.request_name,
            "method": self.method,
            "url": self.url,
            "response": self.response.to_dict() if self.response else None,
            "assertions": [a.to_dict() for a in self.assertions],
            "error": self.error,
            "passed": self.passed,
        }
