"""Загрузчик алгоритмов из YAML файлов"""

import re
from pathlib import Path

import yaml
from loguru import logger

from src.config.settings import settings
from src.core.algorithm_engine import Algorithm

_ALGO_DIR = Path(settings.BASE_DIR) / "src" / "scenarios" / "algorithms"
# Имя файла направления: только безопасные символы (защита от path traversal)
_SAFE_DIRECTION_RE = re.compile(r"^[a-z0-9_]{1,64}$")


class AlgorithmLoader:
    """Загрузчик алгоритмов из YAML файлов"""

    def __init__(self):
        self.algorithms_path = _ALGO_DIR
        self.loaded_algorithms: dict[str, Algorithm] = {}

    def load_algorithm(self, direction: str) -> Algorithm:
        """Загрузить алгоритм по направлению"""
        if not _SAFE_DIRECTION_RE.match(direction):
            logger.warning(
                f"Rejected unsafe algorithm direction: {direction!r}"
            )
            return self._load_template_algorithm("main")

        if direction in self.loaded_algorithms:
            return self.loaded_algorithms[direction]

        algo_file = (self.algorithms_path / f"{direction}.yaml").resolve()
        base = self.algorithms_path.resolve()
        try:
            algo_file.relative_to(base)
        except ValueError:
            logger.warning(f"Algorithm path outside allowed dir: {direction!r}")
            return self._load_template_algorithm("main")

        if not algo_file.exists():
            logger.warning(f"Algorithm {direction} not found, using template")
            return self._load_template_algorithm(direction)

        try:
            with open(algo_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data or "algorithm" not in data:
                raise ValueError(f"Invalid algorithm file: {algo_file}")

            algorithm = Algorithm(data["algorithm"])
            self.loaded_algorithms[direction] = algorithm
            logger.info(f"Algorithm loaded: {direction}")
            return algorithm

        except yaml.YAMLError as e:
            logger.error(f"YAML error in {algo_file}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error loading algorithm {direction}: {e}")
            raise

    def _load_template_algorithm(self, direction: str) -> Algorithm:
        """Загрузить шаблонный алгоритм"""
        tpl = self.algorithms_path / "_template.yaml"
        if tpl.exists():
            with open(tpl, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data and "algorithm" in data:
                data["algorithm"]["direction"] = direction
                name = f"Консультация: {direction}"
                data["algorithm"]["name"] = name
                return Algorithm(data["algorithm"])

        raise FileNotFoundError(
            f"Algorithm for direction '{direction}' not found"
        )

    def load_main_algorithm(self) -> Algorithm:
        """Загрузить основной алгоритм"""
        return self.load_algorithm("main")

    def reload_algorithm(self, direction: str) -> Algorithm:
        """Перезагрузить алгоритм"""
        self.loaded_algorithms.pop(direction, None)
        return self.load_algorithm(direction)

    def get_available_directions(self) -> list:
        """Получить список доступных направлений"""
        return [
            f.stem
            for f in self.algorithms_path.glob("*.yaml")
            if not f.stem.startswith("_")
        ]
