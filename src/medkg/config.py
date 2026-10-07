"""Instance-time configuration; secrets never enter reports or traces."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(os.getenv('MEDKG_HOME',str(Path(__file__).resolve().parents[2]))).resolve()
load_dotenv(ROOT / '.env')
load_dotenv(ROOT.parent / '.env')


def env(key: str, default: str = '') -> str:
    return os.getenv(key, default).strip()


@dataclass
class Settings:
    neo4j_uri: str = field(default_factory=lambda: env('NEO4J_URI', 'bolt://127.0.0.1:7687'))
    neo4j_user: str = field(default_factory=lambda: env('NEO4J_USER', 'neo4j'))
    neo4j_password: str = field(default_factory=lambda: env('NEO4J_PASSWORD'))
    neo4j_database: str = field(default_factory=lambda: env('NEO4J_DATABASE', 'neo4j'))
    llm_base_url: str = field(default_factory=lambda: env('LLM_BASE_URL'))
    llm_api_key: str = field(default_factory=lambda: env('LLM_API_KEY'))
    llm_model: str = field(default_factory=lambda: env('LLM_MODEL'))
    judge_model: str = field(default_factory=lambda: env('JUDGE_MODEL') or env('LLM_MODEL'))
    llm_timeout: float = field(default_factory=lambda: float(env('LLM_TIMEOUT', '30')))
    # Optional cumulative cap over the usage ledger (evaluation runs set it); unset = no cap.
    token_budget: int | None = field(default_factory=lambda: int(env('TOKEN_BUDGET')) if env('TOKEN_BUDGET') else None)
    # Pause after each provider call; the free GLM endpoint returns HTTP 429 without it.
    llm_cooldown: float = field(default_factory=lambda: float(env('LLM_COOLDOWN_S', '1')))
    query_timeout: float = field(default_factory=lambda: float(env('QUERY_TIMEOUT_S', '10')))
    max_limit: int = field(default_factory=lambda: min(200, int(env('MAX_LIMIT', '200'))))
    max_hops: int = field(default_factory=lambda: min(2, int(env('MAX_PATH_HOPS', '2'))))
    safety_region: str = field(default_factory=lambda: env('SAFETY_REGION', 'US').upper())
    phase: int = field(default_factory=lambda: int(env('MEDKG_PHASE', '3')))
    cache: bool = field(default_factory=lambda: env('CACHE', 'false').lower() == 'true')
    cache_ttl: float = field(default_factory=lambda: float(env('CACHE_TTL_S', '3600')))

    def require(self, llm: bool = False) -> None:
        if not self.neo4j_password:
            raise RuntimeError('Missing NEO4J_PASSWORD')
        if llm and not all((self.llm_api_key, self.llm_model, self.llm_base_url)):
            raise RuntimeError('Missing LLM configuration')
