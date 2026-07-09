"""Program data access.

All grant facts come from the seed JSON file. Code elsewhere talks to the
ProgramRepository interface only, so a real database can replace
JsonFileProgramRepository later without touching the matching or API layers.
"""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional


class ProgramRepository(ABC):
    @abstractmethod
    def list_programs(self) -> List[Dict]:
        ...

    @abstractmethod
    def get_program(self, program_id: str) -> Optional[Dict]:
        ...

    @abstractmethod
    def dataset_meta(self) -> Dict:
        ...

    @abstractmethod
    def update_program(self, program_id: str, updates: Dict) -> None:
        ...

    @abstractmethod
    def save(self) -> None:
        ...


class JsonFileProgramRepository(ProgramRepository):
    def __init__(self, json_path: Path):
        self._path = json_path
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._meta: Dict = data.get("dataset_meta", {})
        self._programs: List[Dict] = data.get("programs", [])
        self._by_id: Dict[str, Dict] = {p["id"]: p for p in self._programs}

    def list_programs(self) -> List[Dict]:
        return list(self._programs)

    def get_program(self, program_id: str) -> Optional[Dict]:
        return self._by_id.get(program_id)

    def dataset_meta(self) -> Dict:
        return dict(self._meta)

    def update_program(self, program_id: str, updates: Dict) -> None:
        program = self._by_id.get(program_id)
        if program is None:
            raise KeyError(program_id)
        program.update(updates)

    def save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(
                {"dataset_meta": self._meta, "programs": self._programs},
                f,
                indent=2,
                ensure_ascii=False,
            )
            f.write("\n")
