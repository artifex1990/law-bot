"""Движок алгоритмов - парсинг и выполнение шагов"""

from typing import Any

from loguru import logger


class Step:
    """Шаг алгоритма"""

    def __init__(self, step_dict: dict):
        self.id: str | None = step_dict.get("id")
        self.type = step_dict.get("type", "text")
        self.title = step_dict.get("title")
        self.content = step_dict.get("content", "")
        self.buttons = step_dict.get("buttons", [])
        self.fields = step_dict.get("fields", [])
        self.next_step = step_dict.get("next_step")
        self.final_step = step_dict.get("final_step", False)
        self._raw = step_dict

    def get(self, key: str, default=None) -> Any:
        return self._raw.get(key, default)

    def __repr__(self):
        return f"Step({self.id}:{self.type})"


class Algorithm:
    """Алгоритм консультации"""

    def __init__(self, algorithm_dict: dict):
        self.name = algorithm_dict.get("name")
        self.direction = algorithm_dict.get("direction")
        self.version = algorithm_dict.get("version")
        self.is_paid = algorithm_dict.get("is_paid", False)
        self.price = algorithm_dict.get("price")

        self.steps: dict[str, Step] = {}
        for step_dict in algorithm_dict.get("steps", []):
            step = Step(step_dict)
            if step.id and isinstance(step.id, str):
                self.steps[step.id] = step

        logger.debug(f"Algorithm loaded: {self.name} ({len(self.steps)} steps)")

    def get_step(self, step_id: str) -> Step | None:
        return self.steps.get(step_id)

    def get_first_step(self) -> Step | None:
        if self.steps:
            return next(iter(self.steps.values()))
        return None


class AlgorithmEngine:
    """Движок для работы с алгоритмами"""

    def __init__(self):
        self.loaded_algorithms: dict[str, Algorithm] = {}
