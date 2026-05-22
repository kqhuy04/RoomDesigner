
from __future__ import annotations

import json
import logging
import math
import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator, model_validator
from shapely.affinity import rotate, translate
from shapely.geometry import box
from werkzeug.utils import secure_filename

import chromadb
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI


def get_dimensions_from_json(json_path: str) -> Dict[str, float]:
    """Load furniture dimensions from a sidecar JSON file."""
    default = {"width": 0.0, "length": 0.0, "height": 0.0}
    if not json_path or not os.path.exists(json_path):
        return default
    try:
        with open(json_path, "r", encoding="utf-8") as fh:
            return json.load(fh).get("dimensions", default)
    except Exception as exc:
        logger.warning("Error reading JSON from %s: %s", json_path, exc)
        return default


def normalize_category(cat: str) -> str:
    """Normalize and map category names to the strict 20 collections."""
    cat = cat.lower().strip().replace(" ", "_").replace("-", "_")
    
    valid_collections = {
        "bed", "bench", "cabinet", "chair", "chest", "curtain", "desk", "lamp", 
        "light", "mirror", "plant", "rack", "rug", "shelf", "sofa", "stair", 
        "stool", "table", "television", "wardrobe"
    }
    
    if cat in valid_collections:
        return cat
        
    if "bed" in cat:
        # Check bedside table/cabinet before bed
        if "table" in cat:
            return "table"
        if "cabinet" in cat or "side" in cat:
            return "cabinet"
        return "bed"
        
    if "table" in cat:
        return "table"
        
    if "chair" in cat or "armchair" in cat:
        return "chair"
        
    if "sofa" in cat:
        return "sofa"
        
    if "stool" in cat:
        return "stool"
        
    if "bench" in cat:
        return "bench"
        
    if "desk" in cat:
        return "desk"
        
    if "wardrobe" in cat or "closet" in cat:
        return "wardrobe"
        
    if "cabinet" in cat or "sideboard" in cat or "buffet" in cat or "dresser" in cat or "chest" in cat:
        if "chest" in cat:
            return "chest"
        return "cabinet"
        
    if "shelf" in cat or "bookcase" in cat:
        return "shelf"
        
    if "rack" in cat:
        return "rack"
        
    if "lamp" in cat:
        return "lamp"
        
    if "light" in cat:
        return "light"
        
    if "rug" in cat or "carpet" in cat:
        return "rug"
        
    if "mirror" in cat:
        return "mirror"
        
    if "plant" in cat or "flower" in cat:
        return "plant"
        
    if "curtain" in cat:
        return "curtain"
        
    if "tv" in cat or "television" in cat:
        return "television"
        
    return cat


# =============================================================================
# CONFIGURATION
# =============================================================================

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
GLBS_ROOT = BASE_DIR / "each_50_models" / "glbs"
CHROMA_DB_PATH = str(BASE_DIR / "chroma_db")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3.5-flash")

HARDCODED_MODELS: Dict[str, str] = {
    "window": "window.glb",
    "nightstand": "nightstand.glb",
    "door": "door.glb",
}

# =============================================================================
# LIFESPAN — initialise shared resources once at startup
# =============================================================================

db_client: chromadb.PersistentClient
llm: ChatGoogleGenerativeAI
_planner_chain: Any
_reranker_chain: Any
_explain_chain: Any


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global db_client, llm, _planner_chain, _reranker_chain, _explain_chain

    db_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

    llm = ChatGoogleGenerativeAI(
        model=LLM_MODEL,
        google_api_key=GEMINI_API_KEY,
        temperature=0.2,
    )

    _planner_chain  = _PLANNER_PROMPT  | llm
    _reranker_chain = _RERANKER_PROMPT | llm
    _explain_chain  = _EXPLAIN_PROMPT  | llm

    logger.info("Server started — ChromaDB and LLM ready.")
    yield
    logger.info("Server shutting down.")



# =============================================================================
# APP
# =============================================================================

app = FastAPI(title="Interior Design Layout API", lifespan=lifespan)

_allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "")
_allowed_origins: list[str] | str = (
    [o.strip() for o in _allowed_origins_env.split(",") if o.strip()]
    if _allowed_origins_env
    else ["*"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================


class FurnitureItem(BaseModel):
    type: str
    uid: str
    position: List[float]   # [x, y, z, rotation_radians]
    size: List[float]        # [width, height, length]
    path: Optional[str] = ""

    @field_validator("size")
    @classmethod
    def validate_dimensions(cls, v: List[float]) -> List[float]:
        if len(v) != 3 or any(dim <= 0 for dim in v):
            raise ValueError("size must be three positive numbers [w, h, l]")
        return v

    @field_validator("position")
    @classmethod
    def normalize_rotation(cls, v: List[float]) -> List[float]:
        if len(v) != 4:
            raise ValueError("position must be [x, y, z, rotation_radians]")
        v[3] = v[3] % (2 * math.pi)
        return v


class SearchModelRequest(BaseModel):
    type: str
    description: Optional[str] = None
    color: Any = []
    appropriate_room: Any = []
    material: Any = []
    style: Optional[str] = ""
    mood: Optional[str] = ""


class GenerateLayoutRequest(BaseModel):
    prompt: str
    room_width: float = 5.0
    room_length: float = 5.0

    @model_validator(mode="after")
    def validate_room_dims(self) -> "GenerateLayoutRequest":
        for val, name in [(self.room_width, "room_width"), (self.room_length, "room_length")]:
            if val <= 0 or val > 100:
                raise ValueError(f"{name} phải trong khoảng (0, 100]")
        return self


class ValidateLayoutRequest(BaseModel):
    room_width: float = 5.0
    room_length: float = 5.0
    furniture: List[Dict[str, Any]]

    @model_validator(mode="after")
    def validate_room_dims(self) -> "ValidateLayoutRequest":
        for val, name in [(self.room_width, "room_width"), (self.room_length, "room_length")]:
            if val <= 0 or val > 100:
                raise ValueError(f"{name} phải trong khoảng (0, 100]")
        if not self.furniture:
            raise ValueError("Mảng 'furniture' không được rỗng")
        return self


# =============================================================================
# GEOMETRY ENGINE
# =============================================================================


class GeometryEngine:
    """
    Validates furniture placement inside a rectangular room.
    Uses Shapely polygons; supports automatic nudging to resolve minor overlaps.
    """

    def __init__(self, room_w: float, room_l: float) -> None:
        self.room_w = room_w
        self.room_l = room_l
        self.room_poly = box(0, 0, room_w, room_l).buffer(1e-6)
        self.valid_items: List[FurnitureItem] = []
        self.errors: List[str] = []
        self.margin: float = 0.15

    def _rotated_bounds(self, w: float, l: float, rot: float) -> tuple:
        new_w = abs(w * math.cos(rot)) + abs(l * math.sin(rot))
        new_l = abs(w * math.sin(rot)) + abs(l * math.cos(rot))
        return new_w, new_l

    def _build_polygon(self, item: FurnitureItem) -> Any:
        x, y, z, rot = item.position
        w, _, l = item.size
        rect = box(-w / 2, -l / 2, w / 2, l / 2)
        return translate(rotate(rect, rot, use_radians=True), x, z)

    def _clamp_strictly(self, item: FurnitureItem) -> None:
        w, _, l = item.size
        x, y, z, rot = item.position
        bw, bl = self._rotated_bounds(w, l, rot)
        x = max(bw / 2, min(self.room_w - bw / 2, x))
        z = max(bl / 2, min(self.room_l - bl / 2, z))
        item.position = [x, y, z, rot]

    def _has_collision(self, item: FurnitureItem, poly: Any) -> bool:
        """Checks if placing 'item' at 'poly' collides with any already placed items."""
        for other_item in self.valid_items:
            # Skip checking against items that are bypassed
            other_bypass = other_item.type in {"rug", "light", "curtain", "mirror"}
            if other_bypass:
                continue

            # Special tucking exception: allow chair/stool and table/desk to overlap
            is_chair_stool = item.type in {"chair", "stool"}
            is_other_table_desk = other_item.type in {"table", "desk"}
            is_other_chair_stool = other_item.type in {"chair", "stool"}
            is_table_desk = item.type in {"table", "desk"}

            if (is_chair_stool and is_other_table_desk) or (is_other_chair_stool and is_table_desk):
                continue

            other_poly = self._build_polygon(other_item)
            if poly.distance(other_poly) < self.margin:
                return True
        return False

    def _nudge_to_fit(self, item: FurnitureItem) -> bool:
        orig_x, y, orig_z, rot = item.position
        offsets = [
            (0.1, 0.0), (-0.1, 0.0), (0.0, 0.1), (0.0, -0.1),
            (0.1, 0.1), (-0.1, 0.1), (0.1, -0.1), (-0.1, -0.1),
        ]
        for dx, dz in offsets:
            item.position[0] = orig_x + dx
            item.position[2] = orig_z + dz
            self._clamp_strictly(item)
            poly = self._build_polygon(item)
            if poly.within(self.room_poly) and not self._has_collision(item, poly):
                return True
        item.position = [orig_x, y, orig_z, rot]
        return False

    def validate_and_add(self, item: FurnitureItem) -> bool:
        logger.info("[GeometryEngine] Validating placement for item '%s' (%s), size=%s, initial position=%s", 
                    item.uid, item.type, item.size, item.position)
        self._clamp_strictly(item)
        logger.info("[GeometryEngine] Clamped position for '%s' to %s", item.uid, item.position)
        
        poly = self._build_polygon(item)
        
        # Non-blocking / multi-layered vertical spatial categories are bypassed from 2D collision checks
        is_bypass = item.type in {"rug", "light", "curtain", "mirror"}
        
        collision = False
        if not is_bypass:
            collision = self._has_collision(item, poly)

        if collision:
            logger.info("[GeometryEngine] Collision detected for '%s'. Attempting to nudge...", item.uid)
            if self._nudge_to_fit(item):
                poly = self._build_polygon(item)
                collision = False
                logger.info("[GeometryEngine] Nudging succeeded! New position for '%s': %s", item.uid, item.position)
            else:
                logger.warning("[GeometryEngine] Nudging failed for '%s'.", item.uid)

        if not poly.within(self.room_poly):
            err_msg = f"OUT_OF_BOUNDS: {item.uid}"
            self.errors.append(err_msg)
            logger.error("[GeometryEngine] Placement failed: Item '%s' is out of bounds! Room limit: %.2fx%.2f, Item bounds: %s", 
                          item.uid, self.room_w, self.room_l, poly.bounds)
            return False
            
        if collision:
            err_msg = f"COLLISION: {item.uid}"
            self.errors.append(err_msg)
            logger.error("[GeometryEngine] Placement failed: Item '%s' has unresolved collision with placed items.", item.uid)
            return False
            
        self.valid_items.append(item)
        logger.info("[GeometryEngine] Placement succeeded: Item '%s' placed at %s (rotation: %.2f rad)", 
                    item.uid, item.position, item.position[2])
        return True

    def result_dict(self) -> Dict[str, Any]:
        return {
            "furniture": [it.model_dump() for it in self.valid_items],
            "errors": self.errors,
        }


# =============================================================================
# HELPERS
# =============================================================================


def _content_to_str(content: Any) -> str:
    """Convert LLM response content to string.
    Newer Gemini models may return content as a list of parts instead of a plain string.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and "text" in part:
                parts.append(part["text"])
        return "".join(parts)
    return str(content)


def safe_json_parse(text: Any) -> Optional[Dict[str, Any]]:
    clean = re.sub(r"```(?:json)?", "", _content_to_str(text)).replace("```", "").strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass
    matches = re.findall(r"\{.*\}", clean, re.DOTALL)
    for match in sorted(matches, key=len, reverse=True):
        try:
            obj, _ = json.JSONDecoder().raw_decode(match)
            return obj  # type: ignore[return-value]
        except json.JSONDecodeError:
            continue
    return None



def _normalise_list(value: Any) -> List[str]:
    import ast
    if isinstance(value, list):
        return [str(v).lower().strip() for v in value]
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                return [str(v).lower().strip() for v in parsed]
        except (ValueError, SyntaxError):
            pass
        return [c.lower().strip() for c in value.split(",") if c.strip()]
    return []


def _score_metadata(
    meta: Dict[str, Any],
    input_colors: List[str],
    input_rooms: List[str],
    input_mats: List[str],
    input_style: str,
    input_mood: str,
) -> float:
    score = 0.0
    target_colors = _normalise_list(meta.get("color", []))
    for c in input_colors:
        if any(c in tc for tc in target_colors):
            score += 1.0
    if input_style and input_style == str(meta.get("style", "")).lower():
        score += 0.5
    target_rooms = _normalise_list(meta.get("appropriate_room", []))
    for r in input_rooms:
        if any(r in tr for tr in target_rooms):
            score += 0.3
    target_mats = _normalise_list(meta.get("material", []))
    for m in input_mats:
        if any(m in tm for tm in target_mats):
            score += 0.2
    if input_mood and input_mood == str(meta.get("mood", "")).lower():
        score += 0.2
    return score


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_furniture_str(final_items: List[Dict[str, Any]]) -> str:
    lines = []
    for it in final_items:
        dims = it.get("dimensions", {})
        lines.append(
            f"- {it['category']} (UID: {it['uid']}): "
            f"size(w={dims.get('width', 1.0)}, h={dims.get('height', 1.0)}, l={dims.get('length', 1.0)})"
        )
    return "\n".join(lines)


# =============================================================================
# PROMPT TEMPLATES  (defined at module level; chains built in lifespan)
# =============================================================================

_PLANNER_PROMPT = PromptTemplate.from_template(
    "You are a world-class AI Interior Designer and Spatial Architect.\n"
    "Your task is to analyze the user's room design request (which may be in Vietnamese or English) and plan a detailed 3D interior layout.\n\n"
    "User Prompt: \"{prompt}\"\n\n"
    "DESIGN AND CATEGORY CONSTRAINTS:\n"
    "1. You MUST ONLY use the following 20 allowed categories in the planned furniture JSON. No other categories are allowed:\n"
    "   - Allowed categories: 'bed', 'bench', 'cabinet', 'chair', 'chest', 'curtain', 'desk', 'lamp', 'light', 'mirror', 'plant', 'rack', 'rug', 'shelf', 'sofa', 'stair', 'stool', 'table', 'television', 'wardrobe'.\n"
    "2. MAP any user-requested item to the closest allowed category. For example:\n"
    "   - 'dining table', 'coffee table', 'nightstand', 'bedside table', 'desk table', 'side table' -> MUST map to 'table'\n"
    "   - 'dining chair', 'armchair', 'office chair', 'bar stool' -> MUST map to 'chair' or 'stool' or 'bench'\n"
    "   - 'sideboard', 'buffet cabinet', 'dresser', 'nightstand cabinet' -> MUST map to 'cabinet' or 'chest'\n"
    "   - 'bookshelf', 'bookcase' -> MUST map to 'shelf' or 'cabinet'\n"
    "   - 'ceiling light', 'chandelier', 'pendant light', 'floor lamp' -> MUST map to 'lamp' or 'light'\n"
    "   - 'carpet' -> MUST map to 'rug'\n"
    "   - 'closet' -> MUST map to 'wardrobe'\n"
    "3. FLEXIBLE LAYOUT PLANNING: Satisfy all user customization requests. If they want a bedroom with a sofa or without a bed, fulfill their request exactly by planning the correct allowed categories.\n"
    "4. ROOM DIMENSIONS:\n"
    "   - If the user explicitly specifies room dimensions in their prompt (e.g., 'phòng 5x6m', 'kích thước 4m x 5m', 'room size 6x6'), you MUST parse and use those exact dimensions for room_width and room_length.\n"
    "   - If room dimensions are NOT specified in the prompt, do NOT default or hardcode them to 5.0 x 5.0. Instead, dynamically determine the most appropriate and realistic room size (width and length typically between 4.0 and 8.0 meters) based on the quantity, size, and layout of the requested furniture items to comfortably accommodate them without overcrowding or overlaps.\n"
    "5. COORDINATE SYSTEM AND SPATIAL RULES:\n"
    "   - Room boundaries are from 0 to room_width (X-axis) and 0 to room_length (Z-axis).\n"
    "   - Furniture position is a 4-element list: `[x, y, z, rotation_radians]`, representing:\n"
    "     - `x`: the 2D center point on the X-axis (from 0 to room_width).\n"
    "     - `y`: the vertical elevation/height from the floor in meters (from 0 to 3.0).\n"
    "     - `z`: the 2D center point on the Z-axis (from 0 to room_length).\n"
    "     - `rotation_radians`: rotation around the Y-axis (from 0 to 2pi).\n"
    "   - Size of each object is `[width, height, length]` in meters.\n\n"
    "6. GENERAL SPATIAL INTELLIGENCE & ERGONOMICS PRINCIPLES:\n"
    "   - Major-Axis Alignment: When placing subordinate items around a primary rectangular piece of furniture (e.g., dining chairs around a dining table, nightstands next to a bed), align them parallel to the primary object's major axis (the longer side) and rotate them to face the primary object. For rectangular dining tables, distribute chairs evenly along the longer sides facing each other rather than cramming them at the short ends.\n"
    "   - Vertical Anchoring & Proportions:\n"
    "     * Floor-standing items (e.g., bed, sofa, table, chair, cabinet, wardrobe, rug): `y` coordinate MUST be exactly `0.0`.\n"
    "     * Tabletop items (e.g., nightstand lamp, desk lamp, small plant placed on a surface): `y` coordinate MUST match the exact top surface height of the supporting furniture below it (typically `0.75` for tables/desks, `0.5` for cabinets/nightstands). They must share identical or near-identical [x, z] horizontal coordinates with the support (within 0.05m) and CANNOT float in thin air without support. If the user requests a tabletop item, you MUST also plan a supporting floor-standing item under it.\n"
    "     * Wall-mounted items (e.g., mirror, curtain, wall light): If placed above a floor item (like a sideboard, console, desk, or sink) of height H, they must be visually anchored just above its surface. The bottom edge of the wall item must sit at a clearance height between H + 0.1m and H + 0.25m, which naturally aligns the center of the wall item with standard human eye level (y center typically at 1.35m - 1.6m). Do not float wall items randomly near the ceiling.\n"
    "     * Ceiling-hung items (e.g., pendant light, chandelier): `y` coordinate MUST represent the suspension center near the ceiling (typically `2.4` to `2.7`m).\n"
    "   - Ergonomic Clearances & Traffic Flow: Maintain a minimum of 0.5m of walking clearance between non-connected furniture to ensure a natural flow and prevent blocking of doors, windows, and drawers.\n\n"
    "OUTPUT FORMAT: Return ONLY a raw JSON string matching the structure below. Do not include any markdown fences or explanations:\n"
    "{{\n"
    "  \"room_type\": \"bedroom | living_room | kitchen | bathroom | dining_room | custom\",\n"
    "  \"room_width\": 6.0,\n"
    "  \"room_length\": 5.5,\n"
    "  \"furniture\": [\n"
    "    {{\n"
    "      \"slot_id\": \"table_1\",\n"
    "      \"category\": \"table\",\n"
    "      \"style_query\": \"modern minimalist rectangular wooden dining table\",\n"
    "      \"position\": [3.0, 0.0, 2.75, 0.0],\n"
    "      \"size\": [1.6, 0.75, 0.9]\n"
    "    }},\n"
    "    {{\n"
    "      \"slot_id\": \"chair_1\",\n"
    "      \"category\": \"chair\",\n"
    "      \"style_query\": \"modern minimalist wooden dining chair with backrest\",\n"
    "      \"position\": [2.5, 0.0, 2.1, 0.0],\n"
    "      \"size\": [0.5, 0.85, 0.5]\n"
    "    }},\n"
    "    {{\n"
    "      \"slot_id\": \"chair_2\",\n"
    "      \"category\": \"chair\",\n"
    "      \"style_query\": \"modern minimalist wooden dining chair with backrest\",\n"
    "      \"position\": [3.5, 0.0, 2.1, 0.0],\n"
    "      \"size\": [0.5, 0.85, 0.5]\n"
    "    }},\n"
    "    {{\n"
    "      \"slot_id\": \"chair_3\",\n"
    "      \"category\": \"chair\",\n"
    "      \"style_query\": \"modern minimalist wooden dining chair with backrest\",\n"
    "      \"position\": [2.5, 0.0, 3.4, 3.14],\n"
    "      \"size\": [0.5, 0.85, 0.5]\n"
    "    }},\n"
    "    {{\n"
    "      \"slot_id\": \"chair_4\",\n"
    "      \"category\": \"chair\",\n"
    "      \"style_query\": \"modern minimalist wooden dining chair with backrest\",\n"
    "      \"position\": [3.5, 0.0, 3.4, 3.14],\n"
    "      \"size\": [0.5, 0.85, 0.5]\n"
    "    }},\n"
    "    {{\n"
    "      \"slot_id\": \"light_1\",\n"
    "      \"category\": \"light\",\n"
    "      \"style_query\": \"modern minimalist dining pendant ceiling light\",\n"
    "      \"position\": [3.0, 2.5, 2.75, 0.0],\n"
    "      \"size\": [0.4, 0.8, 0.4]\n"
    "    }},\n"
    "    {{\n"
    "      \"slot_id\": \"cabinet_1\",\n"
    "      \"category\": \"cabinet\",\n"
    "      \"style_query\": \"modern minimalist wooden dining sideboard cabinet\",\n"
    "      \"position\": [3.0, 0.0, 0.5, 3.14],\n"
    "      \"size\": [1.5, 0.8, 0.45]\n"
    "    }},\n"
    "    {{\n"
    "      \"slot_id\": \"mirror_1\",\n"
    "      \"category\": \"mirror\",\n"
    "      \"style_query\": \"modern round wall hanging mirror\",\n"
    "      \"position\": [3.0, 1.35, 0.05, 3.14],\n"
    "      \"size\": [0.8, 0.8, 0.02]\n"
    "    }}\n"
    "  ]\n"
    "}}"
)

_RERANKER_PROMPT = PromptTemplate.from_template(
    "You are an AI Interior Design Stylist. Your task is to select the most suitable product (model) from a list of candidates for each furniture slot in the room.\n"
    "The goal is to maintain style coherence, material alignment, and a harmonious color palette across the entire room according to the user's design requirements.\n\n"
    "User Design Requirements: \"{prompt}\"\n"
    "Room Type: {room_type}\n\n"
    "For each slot, you are given 5 candidate models from the database:\n"
    "{slots_data}\n\n"
    "Selection Rules:\n"
    "1. Choose EXACTLY one best `uid` for each `slot_id`.\n"
    "2. Ensure all chosen items complement each other (e.g., if a modern light wood theme is chosen, don't mix it with shiny classic black vintage cabinets unless specifically requested).\n"
    "3. Focus on matching style, material, and color descriptions.\n\n"
    "OUTPUT FORMAT: Return ONLY a raw JSON mapping from slot_id to selected uid. Do not include any markdown fences or explanations:\n"
    "{{\n"
    "  \"selections\": {{\n"
    "    \"slot_id_1\": \"selected_uid_1\",\n"
    "    \"slot_id_2\": \"selected_uid_2\"\n"
    "  }}\n"
    "}}"
)


_EXPLAIN_PROMPT = PromptTemplate.from_template(
    "Provide a brief, elegant design explanation in English (maximum 3 sentences) describing why the selected items were chosen for this {room_type} based on the style query '{style}':\n"
    "{items}\n"
    "Focus on style harmony, material consistency, and color palette coordination."
)


# =============================================================================
# ROUTES — STATIC PAGES
# =============================================================================


@app.get("/")
async def index(request: Request) -> Any:
    return templates.TemplateResponse("room_viewer.html", {"request": request})


@app.get("/test_load.html")
async def test_load(request: Request) -> Any:
    return templates.TemplateResponse("test_load.html", {"request": request})


# =============================================================================
# ROUTES — MODEL SEARCH
# =============================================================================


@app.post("/search_model")
async def search_model(body: SearchModelRequest) -> JSONResponse:
    if not body.type:
        raise HTTPException(status_code=400, detail="Thiếu trường 'type'")

    try:
        collection = db_client.get_collection(name=body.type)
    except Exception:
        raise HTTPException(
            status_code=404, detail=f"Collection '{body.type}' không tồn tại"
        )

    try:
        total_items = collection.count()
        if total_items == 0:
            return JSONResponse({"found": False, "message": "Collection rỗng"})

        search_desc = body.description or f"A {body.type}"
        # Cap at 50 to avoid loading the entire collection into memory
        n_results = min(total_items, 50)
        results = collection.query(query_texts=[search_desc], n_results=n_results)

        best_model: Optional[Dict[str, Any]] = None
        highest_score = -1.0

        input_colors = _normalise_list(body.color)
        input_rooms  = _normalise_list(body.appropriate_room)
        input_mats   = _normalise_list(body.material)
        input_style  = str(body.style or "").lower()
        input_mood   = str(body.mood or "").lower()

        for i in range(len(results["ids"][0])):
            meta = results["metadatas"][0][i]
            semantic_score = 1.0 / (1.0 + results["distances"][0][i])
            meta_score = _score_metadata(
                meta, input_colors, input_rooms, input_mats, input_style, input_mood
            )
            total = semantic_score + meta_score
            if total > highest_score:
                highest_score = total
                best_model = {
                    "uid": results["ids"][0][i],
                    "path": f"{results['ids'][0][i]}.glb",
                    "total_score": total,
                    "meta": meta,
                }

        if best_model:
            full_path = GLBS_ROOT / best_model["path"]
            if not full_path.exists():
                raise HTTPException(status_code=404, detail="File GLB bị thiếu")
            return JSONResponse({
                "found": True,
                "uid": best_model["uid"],
                "path": best_model["path"],
                "total_score": round(best_model["total_score"], 4),
                "style_info": best_model["meta"].get("style", ""),
            })

        return JSONResponse({"found": False, "message": "Không tìm thấy model phù hợp"})

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("search_model error")
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# LAYOUT PIPELINE — SSE generator
# =============================================================================


async def _run_layout_pipeline(
    user_prompt: str,
    room_w: float,
    room_l: float,
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields SSE messages using the 5-stage RAG pipeline:
      event: progress  → step updates
      event: result    → final layout JSON
      event: error     → fatal error
    """
    # ── Stage 1: Layout Planning (Gemini #1) ──────────────────────────────────
    yield _sse("progress", {"step": 1, "message": "Đang thiết lập bố cục không gian sơ bộ (AI Stage 1)…"})
    logger.info("[Pipeline] Stage 1 starting. User prompt: '%s'", user_prompt)
    try:
        planner_res = _content_to_str((await _planner_chain.ainvoke({"prompt": user_prompt})).content)
        logger.info("[Pipeline] Stage 1 Raw LLM Response:\n%s", planner_res)
        planner_data = safe_json_parse(planner_res) or {}
        logger.info("[Pipeline] Stage 1 Parsed JSON data:\n%s", json.dumps(planner_data, indent=2, ensure_ascii=False))
    except Exception as exc:
        logger.exception("[Pipeline] Planner agent failed")
        yield _sse("error", {"message": f"Lỗi lập kế hoạch không gian: {exc}"})
        return

    room_type = planner_data.get("room_type", "bedroom")
    room_width = float(planner_data.get("room_width", room_w))
    room_length = float(planner_data.get("room_length", room_l))
    planned_slots = planner_data.get("furniture", [])

    logger.info("[Pipeline] Layout details - Room Type: %s, Dimensions: %.2fx%.2f, Planned Slots Count: %d",
                room_type, room_width, room_length, len(planned_slots))

    if not planned_slots:
        logger.error("[Pipeline] Stage 1 failed: No furniture slots planned by the LLM.")
        yield _sse("error", {"message": "Không thể lên bố cục cho phòng. Vui lòng thử lại với prompt cụ thể hơn."})
        return

    # ── Stage 2: ChromaDB Semantic Retrieval ─────────────────────────────────
    yield _sse("progress", {"step": 2, "message": "Đang tìm các sản phẩm phù hợp từ thư viện (ChromaDB)…"})
    logger.info("[Pipeline] Stage 2 starting. Searching models in ChromaDB...")
    
    candidates_map: Dict[str, List[Dict[str, Any]]] = {}
    
    for slot in planned_slots:
        slot_id = slot.get("slot_id")
        raw_cat = slot.get("category", "")
        cat = normalize_category(raw_cat)
        query = slot.get("style_query", user_prompt)
        
        logger.info("[Pipeline] Querying ChromaDB for slot '%s' (Raw Category: '%s', Mapped: '%s') using query: '%s'", 
                    slot_id, raw_cat, cat, query)
        candidates_map[slot_id] = []
        try:
            col = db_client.get_collection(name=cat)
            res = col.query(query_texts=[query], n_results=5)
            if res["ids"] and res["ids"][0]:
                for idx in range(len(res["ids"][0])):
                    uid = res["ids"][0][idx]
                    meta = res["metadatas"][0][idx]
                    path = f"{uid}.glb"
                    
                    # Resolve real size from sidecar JSON
                    json_path = BASE_DIR / "json" / cat / f"{uid}.json"
                    dims = get_dimensions_from_json(str(json_path))
                    
                    cand_data = {
                        "uid": uid,
                        "meta": meta,
                        "path": path,
                        "dimensions": dims
                    }
                    candidates_map[slot_id].append(cand_data)
                    logger.info("[Pipeline] Found candidate for '%s': uid=%s, path=%s", 
                                slot_id, uid, path)
            else:
                logger.warning("[Pipeline] ChromaDB query returned 0 results for category '%s'", cat)
        except Exception as exc:
            logger.exception("[Pipeline] ChromaDB query error on category '%s' for slot '%s'", cat, slot_id)

        # Fallback if no candidates found in database
        if not candidates_map[slot_id]:
            fallback_uid = f"fallback_{cat}"
            fallback_path = HARDCODED_MODELS.get(cat, f"{cat}.glb")
            fallback_size = [
                slot.get("size", [1.0])[0], 
                1.0, 
                slot.get("size", [1.0, 1.0, 1.0])[2]
            ]
            
            logger.warning("[Pipeline] Triggering fallback model for slot '%s' (Category: '%s') -> uid=%s, path=%s", 
                           slot_id, cat, fallback_uid, fallback_path)
            
            candidates_map[slot_id].append({
                "uid": fallback_uid,
                "meta": {"object": f"A default {cat}", "color": "white", "style": "modern"},
                "path": fallback_path,
                "dimensions": {"width": fallback_size[0], "height": 1.0, "length": fallback_size[2]}
            })

    # ── Stage 3: Style Reranking (Gemini #2) ─────────────────────────────────
    yield _sse("progress", {"step": 3, "message": "Đang đồng bộ phong cách và phối màu toàn căn phòng (AI Stage 2)…"})
    logger.info("[Pipeline] Stage 3 starting. Style reranking across all slots...")
    
    slots_data_list = []
    for slot in planned_slots:
        slot_id = slot["slot_id"]
        raw_cat = slot["category"]
        cat = normalize_category(raw_cat)
        cands = candidates_map[slot_id]
        
        cand_strs = []
        for idx, cand in enumerate(cands):
            cand_strs.append(
                f"    Candidate {idx+1}:\n"
                f"      - UID: {cand['uid']}\n"
                f"      - Description: {cand['meta'].get('object', cand['meta'].get('description', ''))[:120]}...\n"
                f"      - Color: {cand['meta'].get('color', '')}\n"
                f"      - Style: {cand['meta'].get('style', '')}\n"
                f"      - Material: {cand['meta'].get('material', '')}"
            )
        
        slots_data_list.append(
            f"Slot: {slot_id} (Category: {cat}, Proposed Size: {slot.get('size')})\n"
            + "\n".join(cand_strs)
        )
    
    slots_data_str = "\n\n".join(slots_data_list)
    logger.info("[Pipeline] Reranker input prompt data prepared:\n%s", slots_data_str)
    
    try:
        reranker_res = _content_to_str((await _reranker_chain.ainvoke({
            "prompt": user_prompt,
            "room_type": room_type,
            "slots_data": slots_data_str
        })).content)
        logger.info("[Pipeline] Stage 3 Raw LLM Reranker Response:\n%s", reranker_res)
        reranker_data = safe_json_parse(reranker_res) or {}
        selections = reranker_data.get("selections", {})
        logger.info("[Pipeline] Stage 3 Parsed selections:\n%s", json.dumps(selections, indent=2))
    except Exception as exc:
        logger.exception("[Pipeline] Reranker agent failed. Falling back to top candidate for each slot.")
        # Fallback: pick top-1 candidate for each slot
        selections = {s["slot_id"]: candidates_map[s["slot_id"]][0]["uid"] for s in planned_slots}

    # Resolve final items
    final_items = []
    for slot in planned_slots:
        slot_id = slot["slot_id"]
        raw_cat = slot["category"]
        cat = normalize_category(raw_cat)
        pos = slot["position"]
        
        sel_uid = selections.get(slot_id)
        cand = next((c for c in candidates_map[slot_id] if c["uid"] == sel_uid), None)
        if not cand and candidates_map[slot_id]:
            cand = candidates_map[slot_id][0]
            logger.warning("[Pipeline] Selected UID '%s' not found in candidates for slot '%s'. Falling back to first candidate '%s'.", 
                           sel_uid, slot_id, cand["uid"])
            
        if cand:
            final_item = {
                "slot_id": slot_id,
                "category": cat,
                "uid": cand["uid"],
                "meta": cand["meta"],
                "path": cand["path"],
                "position": pos,
                "size": slot["size"]  # Scale directly to the LLM's planned size!
            }
            final_items.append(final_item)
            logger.info("[Pipeline] Resolved final selection for '%s': uid=%s, model_path=%s, size=%s", 
                        slot_id, cand["uid"], cand["path"], final_item["size"])

    # ── Stage 4: Geometry Engine Validation & Nudging ───────────────────────
    yield _sse("progress", {"step": 4, "message": "Đang kiểm định khoảng cách và tối ưu hóa vị trí hình học…"})
    logger.info("[Pipeline] Stage 4 starting. Validating layout geometry on room size %.2fx%.2f...", 
                room_width, room_length)
    
    engine = GeometryEngine(room_width, room_length)
    items_to_place: List[FurnitureItem] = []
    for it in final_items:
        items_to_place.append(
            FurnitureItem(
                type=it["category"],
                uid=it["uid"],
                position=it["position"],
                size=it["size"],
                path=it["path"]
            )
        )
        
    # Place larger objects first to ensure stability
    items_to_place.sort(key=lambda x: x.size[0] * x.size[2], reverse=True)
    logger.info("[Pipeline] Sorted items for geometric placement (largest first): %s", 
                [f"{it.type} ({it.uid})" for it in items_to_place])
    
    for it in items_to_place:
        engine.validate_and_add(it)

    logger.info("[Pipeline] Geometry validation finished. Valid items: %d, Failures: %d, Errors: %s", 
                len(engine.valid_items), len(engine.errors), engine.errors)

    # ── Stage 5: Explain Layout & Send ──────────────────────────────────────
    yield _sse("progress", {"step": 5, "message": "Đang hoàn thiện giải pháp thiết kế…"})
    logger.info("[Pipeline] Stage 5 starting. Generating final design explanation...")
    
    furn_str = "\n".join([f"- {it.type} ({it.uid})" for it in engine.valid_items])
    try:
        explanation = _content_to_str((await _explain_chain.ainvoke({
            "room_type": room_type,
            "style":     user_prompt,
            "items":     furn_str,
        })).content).strip()
        logger.info("[Pipeline] Generated design explanation:\n%s", explanation)
    except Exception as exc:
        logger.exception("[Pipeline] Explanation generation failed.")
        explanation = "Bố cục phòng được tối ưu hóa thành công dựa trên quy tắc thiết kế không gian."

    result_payload = {
        "metadata": {
            "room_width":  room_width,
            "room_length": room_length,
            "style":       user_prompt,
            "room_type":   room_type,
            "explanation": explanation,
        },
        "furniture": [it.model_dump() for it in engine.valid_items],
    }
    logger.info("[Pipeline] Stage 5 complete. Sending final SSE result:\n%s", json.dumps(result_payload, indent=2, ensure_ascii=False))
    yield _sse("result", result_payload)



# =============================================================================
# ROUTES — LAYOUT ENGINE
# =============================================================================


@app.post("/generate_layout")
async def generate_layout_api(
    body: GenerateLayoutRequest,
) -> StreamingResponse:
    """
    Streaming layout generation (Server-Sent Events).

    Client should handle:
      event: progress  → show progress indicator
      event: result    → render furniture layout
      event: error     → display error message
    """
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt trống")

    return StreamingResponse(
        _run_layout_pipeline(body.prompt.strip(), body.room_width, body.room_length),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# =============================================================================
# ROUTES — STANDALONE VALIDATION
# =============================================================================


@app.post("/validate_layout")
async def validate_layout(body: ValidateLayoutRequest) -> JSONResponse:
    """
    Validate a furniture layout without running the full generation pipeline.
    Useful for client-side drag-and-drop editors.
    """
    engine = GeometryEngine(body.room_width, body.room_length)
    parse_errors: List[str] = []
    parsed: List[FurnitureItem] = []

    for f in body.furniture:
        try:
            size = f.get("size", [1, 1, 1])
            if len(size) != 3:
                size = [1, 1, 1]
            pos = f.get("position", [body.room_width / 2, 0.0, body.room_length / 2, 0])
            if len(pos) == 3:
                pos = [pos[0], 0.0, pos[1], pos[2]]
            parsed.append(
                FurnitureItem(
                    type=f.get("type", ""),
                    uid=f.get("uid", str(uuid.uuid4())),
                    position=pos,
                    size=size,
                    path=f.get("path", ""),
                )
            )
        except Exception as exc:
            parse_errors.append(f"Parse error for uid={f.get('uid', '?')}: {exc}")

    parsed.sort(key=lambda x: x.size[0] * x.size[2], reverse=True)
    for it in parsed:
        engine.validate_and_add(it)

    result = engine.result_dict()
    result["parse_errors"] = parse_errors
    result["valid_count"] = len(engine.valid_items)
    return JSONResponse(result)


# =============================================================================
# ROUTES — STATIC MODEL SERVING
# =============================================================================


@app.get("/models/{filename:path}")
async def serve_model(filename: str) -> FileResponse:
    safe_name = secure_filename(filename)
    model_path = GLBS_ROOT / safe_name
    if not model_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(model_path))


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=os.getenv("FASTAPI_RELOAD", "false").lower() == "true",
        log_level="info",
    )