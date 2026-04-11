"""Tests: Algorithm engine + YAML loader."""

from pathlib import Path

from src.algorithms.loader import AlgorithmLoader
from src.core.algorithm_engine import (
    Algorithm,
    MediaAttachment,
    Step,
)


def test_step_creation():
    step = Step(
        {
            "id": "greeting",
            "type": "text",
            "content": "Hello",
        }
    )
    assert step.id == "greeting"
    assert step.type == "text"
    assert step.content == "Hello"


def test_step_defaults():
    step = Step({})
    assert step.id is None
    assert step.type == "text"
    assert step.buttons == []
    assert step.media == []


def test_step_photo_field():
    step = Step(
        {
            "id": "welcome",
            "type": "photo",
            "photo": "path/to/img.jpg",
        }
    )
    assert step.photo == "path/to/img.jpg"
    assert step.type == "photo"


def test_step_photo_default_none():
    step = Step({"id": "greeting", "type": "text"})
    assert step.photo is None


def test_step_media_list():
    step = Step(
        {
            "id": "greeting",
            "type": "text",
            "content": "Hello",
            "media": [
                {
                    "type": "photo",
                    "file": "src/scenarios/media/test.jpg",
                    "caption": "Test photo",
                },
                {
                    "type": "video_note",
                    "file": "src/scenarios/media/circle.mp4",
                },
                {
                    "type": "animation",
                    "file": "src/scenarios/media/welcome.gif",
                },
            ],
        }
    )
    assert len(step.media) == 3
    assert step.media[0].type == "photo"
    assert step.media[0].caption == "Test photo"
    assert step.media[1].type == "video_note"
    assert step.media[1].caption is None
    assert step.media[2].type == "animation"


def test_step_media_empty_default():
    step = Step({"id": "s1", "type": "text"})
    assert step.media == []


def test_media_attachment_repr():
    m = MediaAttachment(
        {
            "type": "video_note",
            "file": "circle.mp4",
        }
    )
    assert "video_note" in repr(m)
    assert "circle.mp4" in repr(m)


def test_algorithm_creation():
    data = {
        "name": "Test",
        "direction": "test",
        "steps": [
            {"id": "s1", "type": "text", "content": "Step 1"},
            {"id": "s2", "type": "question", "content": "Step 2"},
        ],
    }
    algo = Algorithm(data)
    assert algo.name == "Test"
    assert len(algo.steps) == 2
    assert algo.get_step("s1") is not None
    assert algo.get_step("nonexistent") is None


def test_algorithm_is_paid():
    data = {
        "name": "Paid",
        "direction": "paid",
        "is_paid": True,
        "price": 5000,
        "steps": [],
    }
    algo = Algorithm(data)
    assert algo.is_paid is True
    assert algo.price == 5000


def test_algorithm_get_first_step():
    data = {
        "name": "Test",
        "steps": [{"id": "first", "content": "First step"}],
    }
    algo = Algorithm(data)
    first = algo.get_first_step()
    assert first is not None
    assert first.id == "first"


def test_algorithm_empty_steps():
    algo = Algorithm({"name": "Empty", "steps": []})
    assert algo.get_first_step() is None


def test_loader_loads_main():
    loader = AlgorithmLoader()
    yaml_dir = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "scenarios"
        / "algorithms"
    )
    if (yaml_dir / "main.yaml").exists():
        algo = loader.load_main_algorithm()
        assert algo is not None
        assert algo.get_step("welcome") is not None
        assert algo.get_step("consent") is not None
        assert algo.get_step("direction_selection") is not None


def test_loader_loads_bankruptcy():
    loader = AlgorithmLoader()
    yaml_dir = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "scenarios"
        / "algorithms"
    )
    if (yaml_dir / "bankruptcy.yaml").exists():
        algo = loader.load_algorithm("bankruptcy")
        assert algo.is_paid is False
        assert algo.get_step("problem_quiz") is not None
        assert algo.get_step("readiness_quiz") is not None
        assert algo.get_step("significance_quiz") is not None


def test_loader_loads_paid_direction():
    loader = AlgorithmLoader()
    yaml_dir = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "scenarios"
        / "algorithms"
    )
    if (yaml_dir / "family.yaml").exists():
        algo = loader.load_algorithm("family")
        assert algo.is_paid is True
        assert algo.get_step("problem_quiz") is not None
        assert algo.get_step("contact_collection") is not None


def test_loader_caches():
    loader = AlgorithmLoader()
    yaml_dir = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "scenarios"
        / "algorithms"
    )
    if (yaml_dir / "main.yaml").exists():
        a1 = loader.load_algorithm("main")
        a2 = loader.load_algorithm("main")
        assert a1 is a2


def test_loader_missing_uses_template():
    loader = AlgorithmLoader()
    algo = loader.load_algorithm("nonexistent_direction_xyz")
    assert algo is not None
    assert algo.direction == "nonexistent_direction_xyz"


def test_loader_rejects_unsafe_direction():
    loader = AlgorithmLoader()
    algo = loader.load_algorithm("../../../etc")
    assert algo is not None
    assert algo.direction == "main"


def test_all_directions_loadable():
    """Ensure all 16 direction YAML files load."""
    loader = AlgorithmLoader()
    directions = [
        "bankruptcy",
        "military",
        "family",
        "medical",
        "pension",
        "labor",
        "consumer",
        "inheritance",
        "ip",
        "real_estate",
        "land",
        "auto",
        "criminal",
        "tax",
        "business",
        "arbitration",
    ]
    yaml_dir = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "scenarios"
        / "algorithms"
    )
    for d in directions:
        if (yaml_dir / f"{d}.yaml").exists():
            algo = loader.load_algorithm(d)
            assert algo is not None, f"Failed to load {d}"
            assert algo.get_step("greeting") is not None, (
                f"Missing greeting in {d}"
            )
            assert algo.get_step("contact_collection") is not None, (
                f"Missing contact_collection in {d}"
            )
