import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from database.models import WebUser
from web.utils.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

_DATA_DIR = Path(__file__).resolve().parent.parent.parent

_regions: list[Any] = []
_branches: list[Any] = []


def _load_json(filename: str) -> list:
    path = _DATA_DIR / filename
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {path}: {e}")
        return []


def _ensure_loaded():
    global _regions, _branches
    if not _regions:
        _regions = _load_json("regions_data.json")
    if not _branches:
        _branches = _load_json("branches_data.json")


@router.get("/regions")
async def get_regions(current_user: WebUser = Depends(get_current_user)):
    _ensure_loaded()
    return _regions


@router.get("/industries")
async def get_industries(current_user: WebUser = Depends(get_current_user)):
    _ensure_loaded()
    return _branches
