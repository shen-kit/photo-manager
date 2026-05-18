from __future__ import annotations

from sqlmodel import Session, select

from app.models import AIModel, AIModelDefault

AI_MODEL_TASK_CLIP_EMBEDDING = "clip_embedding"
AI_MODEL_TASK_FACE_RECOGNITION = "face_recognition"
AI_MODEL_TASK_UNKNOWN = "unknown"


class AIModelConfigurationError(RuntimeError):
    pass


class AIModelRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_default_model_for_task(self, task: str) -> AIModel:
        statement = (
            select(AIModel)
            .join(AIModelDefault, AIModelDefault.model_id == AIModel.id)
            .where(
                AIModelDefault.task == task,
                AIModel.task == task,
            )
        )
        model = self.session.exec(statement).first()
        if model is None:
            raise AIModelConfigurationError(f"Missing default ai model for task {task}")
        if model.is_deprecated:
            raise AIModelConfigurationError(
                f"Default ai model for task {task} is deprecated"
            )
        return model
