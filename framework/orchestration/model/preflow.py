from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import uuid4


"""
PreFlow: Manual processing workflow for engineer review.
Contains human-readable business process steps in markdown format.
Used as input for LLM to generate PSOP.
"""

class PreFlow(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()),
                    description="Unique workflow identifier (auto-generated if not provided)")
    name: str = Field(..., description="Workflow name", examples=['energy_saving_process', 'fault_diagnosis_process'])
    description: Optional[str] = Field(None, description="Brief workflow description, empty by default")

    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")

    steps_md: str = Field(...,
                          description="Markdown formatted business process, human-readable and for LLM generate PSOP")

    tags: Optional[List[str]] = Field(default_factory=list, description="Tags for quick filtering")