from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_secret: str = Field(min_length=16)
    business_db: Path
    checkpoint_db: Path
    run_real_model_eval: bool = False
    llm_embedding_model: str = ""

    @classmethod
    def from_env(cls) -> Settings:
        secret = os.getenv("APP_SECRET")
        if not secret:
            raise ValueError("APP_SECRET is required")
        return cls(
            app_secret=secret,
            business_db=Path(os.getenv("BUSINESS_DB", "data/business.db")),
            checkpoint_db=Path(os.getenv("CHECKPOINT_DB", "data/checkpoints.db")),
            run_real_model_eval=os.getenv("RUN_REAL_MODEL_EVAL", "0") == "1",
            llm_embedding_model=os.getenv("LLM_EMBEDDING_MODEL", ""),
        )
