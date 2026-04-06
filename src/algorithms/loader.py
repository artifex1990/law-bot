"""Загрузчик алгоритмов из YAML файлов"""
import yaml
from pathlib import Path
from typing import Dict, Optional

from loguru import logger

from src.core.algorithm_engine import Algorithm  # noqa: avoid circular import
from src.config.settings import settings


class AlgorithmLoader:
    """Загрузчик алгоритмов из YAML файлов"""
    
    def __init__(self):
        self.algorithms_path = (
            Path(settings.BASE_DIR) / "src" / "scenarios" / "algorithms"
        )
        self.loaded_algorithms: Dict[str, Algorithm] = {}
    
    def load_algorithm(self, direction: str) -> Algorithm:
        """Загрузить алгоритм по направлению"""
        if direction in self.loaded_algorithms:
            return self.loaded_algorithms[direction]
        
        algorithm_file = self.algorithms_path / f"{direction}.yaml"
        
        if not algorithm_file.exists():
            logger.warning(f"Algorithm {direction} not found, using template")
            return self._load_template_algorithm(direction)
        
        try:
            with open(algorithm_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if not data or 'algorithm' not in data:
                raise ValueError(f"Invalid algorithm file: {algorithm_file}")
            
            algorithm = Algorithm(data['algorithm'])
            self.loaded_algorithms[direction] = algorithm
            logger.info(f"Algorithm loaded: {direction}")
            return algorithm
            
        except yaml.YAMLError as e:
            logger.error(f"YAML error in {algorithm_file}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error loading algorithm {direction}: {e}")
            raise
    
    def _load_template_algorithm(self, direction: str) -> Algorithm:
        """Загрузить шаблонный алгоритм для неизвестного направления"""
        template_file = self.algorithms_path / "_template.yaml"
        if template_file.exists():
            with open(template_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if data and 'algorithm' in data:
                data['algorithm']['direction'] = direction
                data['algorithm']['name'] = f"Консультация: {direction}"
                return Algorithm(data['algorithm'])
        
        raise FileNotFoundError(f"Algorithm for direction '{direction}' not found")
    
    def load_main_algorithm(self) -> Algorithm:
        """Загрузить основной алгоритм (выбор направления)"""
        return self.load_algorithm("main")
    
    def reload_algorithm(self, direction: str) -> Algorithm:
        """Перезагрузить алгоритм"""
        self.loaded_algorithms.pop(direction, None)
        return self.load_algorithm(direction)
    
    def get_available_directions(self) -> list:
        """Получить список доступных направлений"""
        return [
            f.stem for f in self.algorithms_path.glob("*.yaml")
            if not f.stem.startswith("_")
        ]
