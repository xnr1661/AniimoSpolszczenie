from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any
import zipfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import UnityPy


APP_NAME = "Aniimo PL Installer"
TARGET_SLOT = "vi_VN"
DISPLAY_TEXT_ID = "1471560215"
DISPLAY_NAME = "POLSKI"
KNOWN_TRANSLATION_ID = "1871651337"

I18N_PREFIX = "xfs/luascripts/Data/I18N/"
MAP_MEMBER = I18N_PREFIX + "NewTextMap_{lang}.json"
POOL_MEMBER = I18N_PREFIX + "Compress_{lang}.bin"
AI_MEMBER = I18N_PREFIX + "AITranslatedItems/AITranslatedItems_{lang}.json"
MAP_RE = re.compile(r"^xfs/luascripts/Data/I18N/NewTextMap_(.+)\.json$")

ARCHIVE_RELATIVE_DIRS = (
    Path(r"Aniimo_Data\StreamingAssets\cvs\res\lua"),
    Path(r"Aniimo_Data\cvs\res\lua"),
)
LOOSE_TARGET_POOL = Path(
    rf"Aniimo_Data\cvs\res\lua\LuaScripts\Data\I18N\Compress_{TARGET_SLOT}.bin"
)

FALLBACK_LANGUAGES = ("en", "zh_CN", "zh_TW", "ja_JP", "ja", "ko_KR", "ko")
RESOURCE_MAP = "NewTextMap_pl.json"
RESOURCE_POOL = "Compress_pl.bin"
RESOURCE_AI = "AITranslatedItems_pl.json"

REMOTE_LANGUAGE_MEMBERS = (
    "xfs/luascripts/Const/ClientConst.lua",
    "xfs/luascripts/SDK/SDKManager.lua",
)
REMOTE_LANGUAGE_VI_PATTERN = b"\x07ja\x07vi\x07ru"
REMOTE_LANGUAGE_EN_PATTERN = b"\x07ja\x07en\x07ru"

FONT_BUNDLE_DIR = Path(
    r"Aniimo_Data\StreamingAssets\cvs\res\uab\win\DefaultPackage"
)
FONT_ASSET_PATTERN = "xpt21_mres_exall_0_*.uab"
FONT_TEXTURE_PATTERN = "xpt21_ar_resx_*_xgui_font_0_*.uab"
FONT_ASSET_NAME = "UI_Font_Chinese"
FONT_TEXTURE_NAME = "UI_Font_Chinese_Atlas"
POLISH_CODEPOINTS = (
    0x0104, 0x0106, 0x0118, 0x0141, 0x0143, 0x00D3, 0x015A, 0x0179, 0x017B,
    0x0105, 0x0107, 0x0119, 0x0142, 0x0144, 0x00F3, 0x015B, 0x017A, 0x017C,
)


def configure_console() -> None:
    if os.name == "nt":
        try:
            os.system("chcp 65001 >nul")
        except OSError:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def resource_dir() -> Path:
    frozen = bundle_dir() / "data"
    if frozen.is_dir():
        return frozen
    return bundle_dir() / "aniimo_pl_installer_data"


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def md5_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def find_font_tree(environment: Any, name: str) -> tuple[Any, dict[str, Any]]:
    for obj in environment.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            tree = obj.read_typetree()
        except Exception:
            continue
        if tree.get("m_Name") == name:
            return obj, tree
    raise ValueError(f"Nie znaleziono fontu {name}.")


def find_font_texture(environment: Any, name: str) -> Any:
    for obj in environment.objects:
        if obj.type.name != "Texture2D":
            continue
        data = obj.read()
        if data.m_Name == name:
            return data
    raise ValueError(f"Nie znaleziono tekstury {name}.")


def listed_bundle_names(game_dir: Path) -> set[str]:
    path = game_dir / "md5list.txt"
    if not path.is_file():
        return set()
    names: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = line.split(",", 2)
        if len(parts) == 3:
            names.add(parts[2].replace("\\", "/").rsplit("/", 1)[-1].casefold())
    return names


def select_font_bundle(
    game_dir: Path,
    pattern: str,
    validator: Any,
    description: str,
) -> Path:
    root = game_dir / FONT_BUNDLE_DIR
    if not root.is_dir():
        raise FileNotFoundError(f"Brakuje katalogu bundli fontów: {root}")
    listed = listed_bundle_names(game_dir)
    candidates = sorted(
        root.glob(pattern),
        key=lambda path: (path.name.casefold() in listed, path.stat().st_mtime_ns),
        reverse=True,
    )
    errors: list[str] = []
    for candidate in candidates:
        try:
            validator(candidate)
            return candidate
        except Exception as exc:
            errors.append(f"{candidate.name}: {exc}")
    details = "; ".join(errors[:3]) or "brak pasujących plików"
    raise RuntimeError(f"Nie znaleziono aktualnego bundla {description}. {details}")


def find_font_bundles(game_dir: Path) -> tuple[Path, Path]:
    def validate_asset(path: Path) -> None:
        find_font_tree(UnityPy.load(str(path)), FONT_ASSET_NAME)

    def validate_texture(path: Path) -> None:
        find_font_texture(UnityPy.load(str(path)), FONT_TEXTURE_NAME)

    asset = select_font_bundle(
        game_dir, FONT_ASSET_PATTERN, validate_asset, "danych UI_Font_Chinese"
    )
    texture = select_font_bundle(
        game_dir, FONT_TEXTURE_PATTERN, validate_texture, "atlasu UI_Font_Chinese"
    )
    return asset, texture


def missing_polish_codepoints(asset_path: Path) -> list[int]:
    _obj, tree = find_font_tree(UnityPy.load(str(asset_path)), FONT_ASSET_NAME)
    available = {int(entry["m_Unicode"]) for entry in tree["m_CharacterTable"]}
    return [codepoint for codepoint in POLISH_CODEPOINTS if codepoint not in available]


def chamfer_distance(target: np.ndarray) -> np.ndarray:
    height, width = target.shape
    distance = np.where(target, 0.0, 1e6).astype(np.float32)
    diagonal = np.float32(1.41421356)
    for y in range(height):
        for x in range(width):
            value = distance[y, x]
            if y:
                value = min(value, distance[y - 1, x] + 1.0)
                if x:
                    value = min(value, distance[y - 1, x - 1] + diagonal)
                if x + 1 < width:
                    value = min(value, distance[y - 1, x + 1] + diagonal)
            if x:
                value = min(value, distance[y, x - 1] + 1.0)
            distance[y, x] = value
    for y in range(height - 1, -1, -1):
        for x in range(width - 1, -1, -1):
            value = distance[y, x]
            if y + 1 < height:
                value = min(value, distance[y + 1, x] + 1.0)
                if x:
                    value = min(value, distance[y + 1, x - 1] + diagonal)
                if x + 1 < width:
                    value = min(value, distance[y + 1, x + 1] + diagonal)
            if x + 1 < width:
                value = min(value, distance[y, x + 1] + 1.0)
            distance[y, x] = value
    return distance


def render_sdf(font: ImageFont.FreeTypeFont, character: str, padding: int = 3) -> tuple[Image.Image, dict[str, float]]:
    left, top, right, bottom = font.getbbox(character, anchor="ls")
    width = max(1, right - left)
    height = max(1, bottom - top)
    mask = Image.new("L", (width + padding * 2, height + padding * 2), 0)
    draw = ImageDraw.Draw(mask)
    draw.text((padding - left, padding - top), character, font=font, fill=255, anchor="ls")
    inside = np.asarray(mask, dtype=np.uint8) >= 128
    signed = chamfer_distance(~inside) - chamfer_distance(inside)
    sdf = np.clip(128.0 + signed * 42.0, 0, 255).astype(np.uint8)
    return Image.fromarray(sdf, mode="L"), {
        "m_Width": float(width),
        "m_Height": float(height),
        "m_HorizontalBearingX": float(left),
        "m_HorizontalBearingY": float(-top),
        "m_HorizontalAdvance": float(font.getlength(character)),
    }


def pack_glyphs(glyphs: list[tuple[int, Image.Image, dict[str, float]]], width: int) -> tuple[list[tuple[int, int]], int]:
    gutter = 6
    positions: list[tuple[int, int]] = []
    x = y = row_height = 0
    for _codepoint, image, _metrics in glyphs:
        if x and x + image.width > width:
            x = 0
            y += row_height + gutter
            row_height = 0
        if image.width > width:
            raise ValueError("Glif jest szerszy niż obszar przeznaczony na poprawkę.")
        positions.append((x, y))
        x += image.width + gutter
        row_height = max(row_height, image.height)
    return positions, y + row_height


def find_free_atlas_region(
    tree: dict[str, Any], glyphs: list[tuple[int, Image.Image, dict[str, float]]]
) -> tuple[int, int, list[tuple[int, int]]]:
    atlas_width = int(tree["m_AtlasWidth"])
    atlas_height = int(tree["m_AtlasHeight"])
    occupied = np.zeros((atlas_height, atlas_width), dtype=np.uint8)
    for rect in tree.get("m_UsedGlyphRects", []):
        x = max(0, int(rect["m_X"]))
        y = max(0, int(rect["m_Y"]))
        right = min(atlas_width, x + max(0, int(rect["m_Width"])))
        top = min(atlas_height, y + max(0, int(rect["m_Height"])))
        occupied[y:top, x:right] = 1

    integral = occupied.cumsum(axis=0, dtype=np.uint32)
    integral.cumsum(axis=1, dtype=np.uint32, out=integral)
    padded = np.pad(integral, ((1, 0), (1, 0)), mode="constant")
    for patch_width in (192, 256, 384, 512, 768, 1024):
        if patch_width >= atlas_width:
            continue
        positions, patch_height = pack_glyphs(glyphs, patch_width)
        if patch_height >= atlas_height:
            continue
        sums = (
            padded[patch_height:, patch_width:]
            - padded[:-patch_height, patch_width:]
            - padded[patch_height:, :-patch_width]
            + padded[:-patch_height, :-patch_width]
        )
        free = sums == 0
        for y in range(free.shape[0] - 1, -1, -1):
            xs = np.flatnonzero(free[y])
            if xs.size:
                return int(xs[-1]), y, positions
    raise ValueError("Brak wolnego miejsca w atlasie UI_Font_Chinese na polskie glify.")


def find_system_font() -> Path:
    windows = Path(os.environ.get("WINDIR", r"C:\Windows"))
    for name in ("arialbd.ttf", "arial.ttf", "segoeuib.ttf", "segoeui.ttf"):
        candidate = windows / "Fonts" / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("Nie znaleziono systemowego fontu Arial ani Segoe UI.")


def build_dynamic_font_patch(
    asset_path: Path, texture_path: Path, output_dir: Path
) -> tuple[Path, Path]:
    asset_env = UnityPy.load(str(asset_path))
    texture_env = UnityPy.load(str(texture_path))
    font_obj, tree = find_font_tree(asset_env, FONT_ASSET_NAME)
    texture = find_font_texture(texture_env, FONT_TEXTURE_NAME)
    atlas = texture.image.convert("RGBA")
    atlas_width = int(tree["m_AtlasWidth"])
    atlas_height = int(tree["m_AtlasHeight"])
    if atlas.size != (atlas_width, atlas_height):
        raise ValueError(
            f"Niezgodny rozmiar atlasu fontu: {atlas.size} zamiast {(atlas_width, atlas_height)}"
        )

    existing = {int(entry["m_Unicode"]) for entry in tree["m_CharacterTable"]}
    missing = [codepoint for codepoint in POLISH_CODEPOINTS if codepoint not in existing]
    if not missing:
        raise ValueError("Font zawiera już wszystkie polskie glify.")

    font = ImageFont.truetype(
        str(find_system_font()), size=int(tree["m_FaceInfo"]["m_PointSize"])
    )
    glyphs = [(codepoint, *render_sdf(font, chr(codepoint))) for codepoint in missing]
    origin_x, origin_y, positions = find_free_atlas_region(tree, glyphs)
    next_index = max(int(entry["m_Index"]) for entry in tree["m_GlyphTable"]) + 1
    new_rects: list[dict[str, int]] = []

    for (codepoint, glyph_image, metrics), (local_x, local_y) in zip(glyphs, positions):
        x = origin_x + local_x
        y = origin_y + local_y
        rgba = Image.new("RGBA", glyph_image.size, (0, 0, 0, 0))
        rgba.putalpha(glyph_image)
        atlas.paste(rgba, (x, atlas_height - y - glyph_image.height))
        rect = {
            "m_X": x,
            "m_Y": y,
            "m_Width": glyph_image.width,
            "m_Height": glyph_image.height,
        }
        tree["m_GlyphTable"].append(
            {
                "m_Index": next_index,
                "m_Metrics": metrics,
                "m_GlyphRect": rect,
                "m_Scale": 1.0,
                "m_AtlasIndex": 0,
                "m_ClassDefinitionType": 0,
            }
        )
        tree["m_CharacterTable"].append(
            {
                "m_ElementType": 1,
                "m_Unicode": codepoint,
                "m_GlyphIndex": next_index,
                "m_Scale": 1.0,
            }
        )
        new_rects.append(rect)
        next_index += 1

    tree["m_UsedGlyphRects"].extend(new_rects)
    tree["m_FreeGlyphRects"] = []
    font_obj.save_typetree(tree)
    texture.set_image(atlas, target_format=1, mipmap_count=1)
    texture.save()

    output_dir.mkdir(parents=True, exist_ok=True)
    output_asset = output_dir / asset_path.name
    output_texture = output_dir / texture_path.name
    output_asset.write_bytes(asset_env.file.save(packer="original"))
    output_texture.write_bytes(texture_env.file.save(packer="original"))
    if missing_polish_codepoints(output_asset):
        raise ValueError("Nie wszystkie polskie glify zapisano w wygenerowanym foncie.")
    find_font_texture(UnityPy.load(str(output_texture)), FONT_TEXTURE_NAME)
    return output_asset, output_texture


def load_json_bytes(data: bytes) -> Any:
    return json.loads(data.decode("utf-8-sig"))


def dump_json_bytes(value: Any, *, indent: int = 4) -> bytes:
    text = json.dumps(value, ensure_ascii=False, indent=indent).replace("\n", "\r\n")
    return text.encode("utf-8")


def decode_text(mapping: dict[str, Any], pool: bytes, text_id: str) -> str:
    span = mapping.get(text_id)
    if not isinstance(span, list) or len(span) != 2:
        return ""
    offset, length = int(span[0]), int(span[1])
    if offset < 0 or length < 0 or offset + length > len(pool):
        raise ValueError(f"Nieprawidłowy zakres tekstu {text_id}: {offset}+{length}/{len(pool)}")
    return pool[offset : offset + length].decode("utf-8", errors="strict")


def load_language(archive: zipfile.ZipFile, lang: str) -> tuple[dict[str, Any], bytes]:
    mapping = load_json_bytes(archive.read(MAP_MEMBER.format(lang=lang)))
    if not isinstance(mapping, dict):
        raise ValueError(f"Mapa języka {lang} nie jest obiektem JSON.")
    pool = archive.read(POOL_MEMBER.format(lang=lang))
    return mapping, pool


def list_languages(archive: zipfile.ZipFile) -> list[str]:
    result: list[str] = []
    names = set(archive.namelist())
    for name in names:
        match = MAP_RE.match(name)
        if not match:
            continue
        lang = match.group(1)
        if POOL_MEMBER.format(lang=lang) in names:
            result.append(lang)
    return sorted(set(result))


def load_embedded_polish() -> tuple[dict[str, str], list[Any]]:
    data = resource_dir()
    mapping = load_json_bytes((data / RESOURCE_MAP).read_bytes())
    pool = (data / RESOURCE_POOL).read_bytes()
    translations: dict[str, str] = {}
    for text_id in mapping:
        if text_id.startswith("_"):
            continue
        translations[text_id] = decode_text(mapping, pool, text_id)

    ai_values = load_json_bytes((data / RESOURCE_AI).read_bytes())
    if not isinstance(ai_values, list):
        raise ValueError("Wbudowany AITranslatedItems_pl.json jest nieprawidłowy.")
    return translations, ai_values


def build_polish_target(
    archive: zipfile.ZipFile,
    embedded: dict[str, str],
) -> tuple[bytes, bytes, dict[str, int]]:
    available = set(list_languages(archive))
    source_data: dict[str, tuple[dict[str, Any], bytes]] = {}
    for lang in FALLBACK_LANGUAGES:
        if lang in available:
            source_data[lang] = load_language(archive, lang)

    if "en" not in source_data:
        raise ValueError("Archiwum nie zawiera wymaganej mapy języka English.")

    current_ids = set(embedded)
    for mapping, _pool in source_data.values():
        current_ids.update(key for key in mapping if not key.startswith("_"))

    version = source_data["en"][0].get("_version", 0)
    blob = bytearray()
    offsets: dict[str, list[int]] = {}
    reused: dict[str, list[int]] = {}
    stats = {"polish": 0, "fallback": 0, "empty": 0, "ids": len(current_ids)}

    for text_id in sorted(current_ids, key=lambda value: int(value)):
        if text_id == DISPLAY_TEXT_ID:
            text = DISPLAY_NAME
            stats["polish"] += 1
        elif text_id in embedded and embedded[text_id]:
            text = embedded[text_id]
            stats["polish"] += 1
        else:
            text = ""
            for lang in FALLBACK_LANGUAGES:
                if lang not in source_data:
                    continue
                mapping, pool = source_data[lang]
                text = decode_text(mapping, pool, text_id)
                if text:
                    break
            if text:
                stats["fallback"] += 1
            else:
                stats["empty"] += 1

        span = reused.get(text)
        if span is None:
            encoded = text.encode("utf-8")
            span = [len(blob), len(encoded)]
            blob.extend(encoded)
            reused[text] = span
        offsets[text_id] = span

    output_map: dict[str, Any] = {"_count": len(current_ids), "_version": version}
    output_map.update(offsets)
    return dump_json_bytes(output_map), bytes(blob), stats


def patch_display_name(
    mapping: dict[str, Any],
    pool: bytes,
) -> tuple[bytes, bytes, bool]:
    if decode_text(mapping, pool, DISPLAY_TEXT_ID) == DISPLAY_NAME:
        return dump_json_bytes(mapping), pool, False

    encoded = DISPLAY_NAME.encode("utf-8")
    new_pool = pool + encoded
    existed = DISPLAY_TEXT_ID in mapping
    mapping = dict(mapping)
    mapping[DISPLAY_TEXT_ID] = [len(pool), len(encoded)]
    if not existed:
        mapping["_count"] = int(mapping.get("_count", 0)) + 1
    return dump_json_bytes(mapping), new_pool, True


def patch_remote_language(member: str, data: bytes) -> tuple[bytes, bool]:
    vi_count = data.count(REMOTE_LANGUAGE_VI_PATTERN)
    en_count = data.count(REMOTE_LANGUAGE_EN_PATTERN)
    if vi_count == 1 and en_count == 0:
        return data.replace(REMOTE_LANGUAGE_VI_PATTERN, REMOTE_LANGUAGE_EN_PATTERN, 1), True
    if vi_count == 0 and en_count == 1:
        return data, False
    raise ValueError(
        f"Nie można bezpiecznie przełączyć treści internetowych na English w {member} "
        f"(vi={vi_count}, en={en_count}). Gra mogła zostać zaktualizowana."
    )


def build_replacements(
    source_xdf: Path,
    embedded: dict[str, str],
    embedded_ai: list[Any],
) -> tuple[dict[str, bytes], dict[str, Any]]:
    replacements: dict[str, bytes] = {}
    with zipfile.ZipFile(source_xdf, "r") as archive:
        target_map, target_pool, stats = build_polish_target(archive, embedded)
        replacements[MAP_MEMBER.format(lang=TARGET_SLOT)] = target_map
        replacements[POOL_MEMBER.format(lang=TARGET_SLOT)] = target_pool

        patched_labels: list[str] = []
        for lang in list_languages(archive):
            if lang in {TARGET_SLOT, "pl", "pl_PL"}:
                continue
            mapping, pool = load_language(archive, lang)
            map_bytes, pool_bytes, changed = patch_display_name(mapping, pool)
            if changed:
                replacements[MAP_MEMBER.format(lang=lang)] = map_bytes
                replacements[POOL_MEMBER.format(lang=lang)] = pool_bytes
                patched_labels.append(lang)

        ai_values: dict[int, Any] = {}

        def add_ai(value: Any) -> None:
            if isinstance(value, int):
                ai_values[value] = value
            elif isinstance(value, dict) and isinstance(value.get("id"), int):
                ai_values[value["id"]] = value

        for value in embedded_ai:
            add_ai(value)
        for lang in (TARGET_SLOT, "en"):
            member = AI_MEMBER.format(lang=lang)
            try:
                current = load_json_bytes(archive.read(member))
            except KeyError:
                continue
            if isinstance(current, list):
                for value in current:
                    add_ai(value)
        replacements[AI_MEMBER.format(lang=TARGET_SLOT)] = dump_json_bytes(
            [ai_values[key] for key in sorted(ai_values)], indent=2
        )

        remote_language_patched: list[str] = []
        for member in REMOTE_LANGUAGE_MEMBERS:
            patched_data, changed = patch_remote_language(member, archive.read(member))
            replacements[member] = patched_data
            if changed:
                remote_language_patched.append(member)

    return replacements, {
        **stats,
        "labels_patched": patched_labels,
        "ai_count": len(ai_values),
        "remote_language": "en",
        "remote_language_patched": remote_language_patched,
    }


def zip_data_offset(path: Path, info: zipfile.ZipInfo) -> int:
    with path.open("rb") as handle:
        handle.seek(info.header_offset + 26)
        name_len = int.from_bytes(handle.read(2), "little")
        extra_len = int.from_bytes(handle.read(2), "little")
    return info.header_offset + 30 + name_len + extra_len


def rebuild_xdt(source_xdt: Path, xdf: Path, output: Path) -> None:
    manifest = json.loads(source_xdt.read_text(encoding="utf-8-sig"))
    by_name = {entry.get("CEName"): entry for entry in manifest.get("CMList", [])}
    entries: list[dict[str, Any]] = []
    with zipfile.ZipFile(xdf, "r") as archive:
        for index, info in enumerate(archive.infolist()):
            data = archive.read(info.filename)
            entry = dict(by_name.get(info.filename, {"CEName": info.filename}))
            entry.update(
                {
                    "CEName": info.filename,
                    "CEMD5": md5_bytes(data),
                    "CESize": info.file_size,
                    "CEIndex": index,
                    "CEOffset": zip_data_offset(xdf, info),
                    "CECSize": info.compress_size,
                    "CEContainer": entry.get("CEContainer", 0),
                }
            )
            entries.append(entry)

    manifest["CMDataLen"] = xdf.stat().st_size
    manifest["CMDataMD5"] = md5_file(xdf)
    manifest["CMEntryNum"] = len(entries)
    manifest["CMList"] = entries
    output.write_bytes(dump_json_bytes(manifest))


def repack_archive_pair(
    source_xdf: Path,
    source_xdt: Path,
    output_xdf: Path,
    output_xdt: Path,
    embedded: dict[str, str],
    embedded_ai: list[Any],
) -> dict[str, Any]:
    replacements, stats = build_replacements(source_xdf, embedded, embedded_ai)
    output_xdf.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(source_xdf, "r") as source, zipfile.ZipFile(
        output_xdf, "w", allowZip64=True
    ) as target:
        target.comment = source.comment
        existing: set[str] = set()
        for info in source.infolist():
            existing.add(info.filename)
            data = replacements.get(info.filename, source.read(info.filename))
            new_info = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            new_info.compress_type = info.compress_type
            new_info.comment = info.comment
            new_info.extra = info.extra
            new_info.internal_attr = info.internal_attr
            new_info.external_attr = info.external_attr
            new_info.create_system = info.create_system
            target.writestr(new_info, data)

        for name, data in replacements.items():
            if name in existing:
                continue
            new_info = zipfile.ZipInfo(name, date_time=datetime.now().timetuple()[:6])
            new_info.compress_type = zipfile.ZIP_DEFLATED
            new_info.external_attr = 0o644 << 16
            target.writestr(new_info, data)

    rebuild_xdt(source_xdt, output_xdf, output_xdt)
    verify_archive_pair(output_xdf, output_xdt)
    stats["xdf_size"] = output_xdf.stat().st_size
    stats["xdf_md5"] = md5_file(output_xdf)
    return stats


def verify_archive_pair(xdf: Path, xdt: Path) -> None:
    manifest = json.loads(xdt.read_text(encoding="utf-8-sig"))
    if int(manifest.get("CMDataLen", -1)) != xdf.stat().st_size:
        raise ValueError("CMDataLen nie zgadza się z rozmiarem XDF.")
    if str(manifest.get("CMDataMD5", "")).casefold() != md5_file(xdf):
        raise ValueError("CMDataMD5 nie zgadza się z sumą XDF.")

    with zipfile.ZipFile(xdf, "r") as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"Uszkodzony wpis ZIP: {bad}")
        if int(manifest.get("CMEntryNum", -1)) != len(archive.infolist()):
            raise ValueError("CMEntryNum nie zgadza się z liczbą wpisów XDF.")
        mapping, pool = load_language(archive, TARGET_SLOT)
        if decode_text(mapping, pool, DISPLAY_TEXT_ID) != DISPLAY_NAME:
            raise ValueError("Slot docelowy nie zawiera nazwy POLSKI.")
        known = decode_text(mapping, pool, KNOWN_TRANSLATION_ID)
        if "Susuta" not in known or "Energi" not in known:
            raise ValueError("Kontrolny tekst polski nie został poprawnie powiązany.")
        english_map, english_pool = load_language(archive, "en")
        if decode_text(english_map, english_pool, DISPLAY_TEXT_ID) != DISPLAY_NAME:
            raise ValueError("Menu English nie pokazuje nazwy POLSKI.")
        for member in REMOTE_LANGUAGE_MEMBERS:
            data = archive.read(member)
            if data.count(REMOTE_LANGUAGE_VI_PATTERN) != 0:
                raise ValueError(f"{member} nadal wskazuje język internetowy Vietnamese.")
            if data.count(REMOTE_LANGUAGE_EN_PATTERN) != 1:
                raise ValueError(f"{member} nie wskazuje jednoznacznie języka internetowego English.")


def archive_pairs(game_dir: Path) -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    for relative in ARCHIVE_RELATIVE_DIRS:
        folder = game_dir / relative
        xdf, xdt = folder / "LuaScripts.xdf", folder / "LuaScripts.xdt"
        if xdf.is_file() and xdt.is_file():
            pairs.append((xdf, xdt))
    if not pairs:
        raise FileNotFoundError("Nie znaleziono LuaScripts.xdf i LuaScripts.xdt w instalacji Aniimo.")
    return pairs


def valid_game_dir(path: Path) -> bool:
    return (path / "Aniimo_Data").is_dir() and (path / "Aniimo.exe").is_file()


def steam_candidates() -> list[Path]:
    candidates: list[Path] = []
    if os.name != "nt":
        return candidates
    try:
        import winreg

        for root, key in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        ):
            try:
                with winreg.OpenKey(root, key) as handle:
                    candidates.append(Path(winreg.QueryValueEx(handle, "SteamPath")[0]))
            except OSError:
                try:
                    with winreg.OpenKey(root, key) as handle:
                        candidates.append(Path(winreg.QueryValueEx(handle, "InstallPath")[0]))
                except OSError:
                    pass
    except ImportError:
        pass

    libraries: list[Path] = []
    for steam in candidates:
        libraries.append(steam)
        vdf = steam / "steamapps" / "libraryfolders.vdf"
        if not vdf.is_file():
            continue
        text = vdf.read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            libraries.append(Path(match.group(1).replace(r"\\", "\\")))
    return [library / "steamapps" / "common" / "Aniimo" for library in libraries]


def find_game_dir(explicit: Path | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(explicit)
    env_path = os.environ.get("ANIIMO_GAME_DIR")
    if env_path:
        candidates.append(Path(env_path))

    executable_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()
    candidates.extend([executable_dir, executable_dir.parent])
    candidates.append(Path(r"D:\Apps\Steam\steamapps\common\Aniimo"))
    candidates.extend(steam_candidates())

    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        key = str(resolved).casefold()
        if key in seen:
            continue
        seen.add(key)
        if valid_game_dir(resolved):
            return resolved
    raise FileNotFoundError(
        "Nie znaleziono instalacji Aniimo. Uruchom EXE z parametrem --game \"D:\\...\\Aniimo\"."
    )


def game_is_running() -> bool:
    if os.name != "nt":
        return False
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Aniimo.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        errors="ignore",
        creationflags=flags,
        check=False,
    )
    return "aniimo.exe" in result.stdout.casefold()


def user_work_dir() -> Path:
    override = os.environ.get("ANIIMO_PL_WORK_DIR")
    if override:
        return Path(override).expanduser().resolve()
    documents = Path.home() / "Documents"
    return documents / "AniimoPolishTranslation"


def make_backup(
    game_dir: Path,
    pairs: list[tuple[Path, Path]],
    extra_files: list[Path] | None = None,
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = user_work_dir() / "backups" / timestamp
    manifest: dict[str, Any] = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "game_dir": str(game_dir),
        "files": [],
    }
    files = [item for pair in pairs for item in pair]
    files.extend(extra_files or [])
    for path in dict.fromkeys(files):
        relative = path.relative_to(game_dir)
        destination = backup / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        manifest["files"].append(
            {"relative": str(relative), "md5": md5_file(path), "size": path.stat().st_size}
        )

    loose = game_dir / LOOSE_TARGET_POOL
    manifest["loose_target_existed"] = loose.is_file()
    if loose.is_file():
        destination = backup / LOOSE_TARGET_POOL
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(loose, destination)
        manifest["files"].append(
            {"relative": str(LOOSE_TARGET_POOL), "md5": md5_file(loose), "size": loose.stat().st_size}
        )

    (backup / "backup_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return backup


def restore_backup(game_dir: Path, backup: Path) -> None:
    manifest_path = backup / "backup_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    game_root = game_dir.resolve()
    backup_game_dir = Path(str(manifest.get("game_dir", ""))).resolve()
    if backup_game_dir != game_root:
        raise ValueError(
            f"Backup pochodzi z innej instalacji gry: {backup_game_dir}"
        )

    for item in manifest.get("files", []):
        relative = Path(item["relative"])
        source = backup / relative
        target = (game_dir / relative).resolve()
        if game_root != target and game_root not in target.parents:
            raise ValueError(f"Nieprawidłowa ścieżka w backupie: {relative}")
        if not source.is_file():
            raise FileNotFoundError(f"W backupie brakuje pliku: {relative}")
        expected_md5 = str(item.get("md5", "")).casefold()
        if expected_md5 and md5_file(source) != expected_md5:
            raise ValueError(f"Plik backupu ma nieprawidłową sumę MD5: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_copy(source, target)
        if expected_md5 and md5_file(target) != expected_md5:
            raise ValueError(f"Nie udało się poprawnie przywrócić pliku: {relative}")

    if not manifest.get("loose_target_existed", False):
        loose = (game_dir / LOOSE_TARGET_POOL).resolve()
        if game_root != loose and game_root not in loose.parents:
            raise ValueError("Nieprawidłowa ścieżka luźnego pliku językowego.")
        loose.unlink(missing_ok=True)


def latest_backup() -> Path:
    root = user_work_dir() / "backups"
    backups = sorted((path for path in root.iterdir() if path.is_dir()), reverse=True) if root.is_dir() else []
    if not backups:
        raise FileNotFoundError("Nie znaleziono backupu spolszczenia Aniimo.")
    return backups[0]


def atomic_copy(source: Path, target: Path) -> None:
    pending = target.with_name(target.name + ".pltmp")
    try:
        shutil.copy2(source, pending)
        os.replace(pending, target)
    finally:
        pending.unlink(missing_ok=True)


def install(game_dir: Path) -> dict[str, Any]:
    if game_is_running():
        raise RuntimeError("Aniimo jest uruchomione. Zamknij grę i uruchom instalator ponownie.")

    pairs = archive_pairs(game_dir)
    embedded, embedded_ai = load_embedded_polish()
    backup: Path | None = None
    summaries: list[dict[str, Any]] = []
    font_asset, font_texture = find_font_bundles(game_dir)
    font_targets = [font_asset, font_texture]
    font_missing = missing_polish_codepoints(font_asset)

    with tempfile.TemporaryDirectory(prefix="aniimo-pl-") as temp_name:
        temp = Path(temp_name)
        font_files: list[tuple[Path, Path, str]] = []
        if font_missing:
            print("Przygotowywanie poprawki polskich znaków dla bieżącej wersji gry...")
            staged_asset, staged_texture = build_dynamic_font_patch(
                font_asset, font_texture, temp / "font"
            )
            font_files.extend(
                [
                    (staged_asset, font_asset, md5_file(staged_asset)),
                    (staged_texture, font_texture, md5_file(staged_texture)),
                ]
            )
        staged: list[tuple[Path, Path, Path, Path]] = []
        first_target_pool: bytes | None = None
        for index, (source_xdf, source_xdt) in enumerate(pairs):
            output_dir = temp / str(index)
            output_xdf = output_dir / "LuaScripts.xdf"
            output_xdt = output_dir / "LuaScripts.xdt"
            summary = repack_archive_pair(
                source_xdf,
                source_xdt,
                output_xdf,
                output_xdt,
                embedded,
                embedded_ai,
            )
            summary["target"] = str(source_xdf.parent.relative_to(game_dir))
            summaries.append(summary)
            staged.append((output_xdf, output_xdt, source_xdf, source_xdt))
            if first_target_pool is None:
                with zipfile.ZipFile(output_xdf, "r") as archive:
                    first_target_pool = archive.read(POOL_MEMBER.format(lang=TARGET_SLOT))

        identical = all(
            md5_file(output_xdf) == md5_file(target_xdf)
            and md5_file(output_xdt) == md5_file(target_xdt)
            for output_xdf, output_xdt, target_xdf, target_xdt in staged
        )
        loose = game_dir / LOOSE_TARGET_POOL
        if loose.is_file() and first_target_pool is not None:
            identical = identical and md5_file(loose) == md5_bytes(first_target_pool)
        identical = identical and all(
            md5_file(target) == patched_md5
            for _source, target, patched_md5 in font_files
        )

        if not identical:
            backup = make_backup(
                game_dir, pairs, [target for _source, target, _md5 in font_files]
            )
        try:
            if not identical:
                for output_xdf, output_xdt, target_xdf, target_xdt in staged:
                    atomic_copy(output_xdf, target_xdf)
                    atomic_copy(output_xdt, target_xdt)
                    verify_archive_pair(target_xdf, target_xdt)

                if loose.parent.is_dir() and first_target_pool is not None:
                    pending = loose.with_name(loose.name + ".pltmp")
                    pending.write_bytes(first_target_pool)
                    os.replace(pending, loose)

                for source, target, patched_md5 in font_files:
                    atomic_copy(source, target)
                    if md5_file(target) != patched_md5:
                        raise ValueError(f"Nie udało się poprawnie zainstalować fontu: {target.name}")
        except Exception:
            if backup is not None:
                restore_backup(game_dir, backup)
            raise

    if backup is None:
        previous_manifest = user_work_dir() / "last_install.json"
        if previous_manifest.is_file():
            try:
                previous = json.loads(previous_manifest.read_text(encoding="utf-8"))
                previous_backup = previous.get("backup")
                if previous_backup and Path(previous_backup).is_dir():
                    backup = Path(previous_backup)
            except (OSError, ValueError, TypeError):
                pass

    result = {
        "installed_at": datetime.now().isoformat(timespec="seconds"),
        "game_dir": str(game_dir),
        "backup": str(backup) if backup else "",
        "changed": not identical,
        "target_slot": TARGET_SLOT,
        "display_name": DISPLAY_NAME,
        "font_patch": [str(target.relative_to(game_dir)) for target in font_targets],
        "font_generated": bool(font_files),
        "archives": summaries,
    }
    work = user_work_dir()
    work.mkdir(parents=True, exist_ok=True)
    (work / "last_install.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def check_install(game_dir: Path) -> bool:
    ok = True
    for xdf, xdt in archive_pairs(game_dir):
        try:
            verify_archive_pair(xdf, xdt)
            print(f"[OK] {xdf}")
        except Exception as exc:
            ok = False
            print(f"[BRAK] {xdf}: {exc}")
    try:
        asset, texture = find_font_bundles(game_dir)
        missing = missing_polish_codepoints(asset)
        if missing:
            ok = False
            print(f"[BRAK] Poprawka polskich znaków: {asset}")
        else:
            print(f"[OK] {asset}")
            print(f"[OK] {texture}")
    except Exception as exc:
        ok = False
        print(f"[BRAK] Poprawka polskich znaków: {exc}")
    return ok


def pause_if_needed(no_pause: bool) -> None:
    if no_pause or not getattr(sys, "frozen", False):
        return
    try:
        input("\nNaciśnij Enter, aby zamknąć...")
    except EOFError:
        pass


def main() -> int:
    configure_console()
    parser = argparse.ArgumentParser(description="Instalator polskiego języka do Aniimo.")
    parser.add_argument("--game", type=Path, help="Katalog zawierający Aniimo.exe")
    parser.add_argument("--check", action="store_true", help="Tylko sprawdź stan instalacji")
    parser.add_argument("--restore-latest", action="store_true", help="Przywróć najnowszy backup")
    parser.add_argument("--no-pause", action="store_true", help="Nie czekaj na Enter")
    args = parser.parse_args()

    print(f"{APP_NAME}\n")
    try:
        game_dir = find_game_dir(args.game)
        print(f"Gra: {game_dir}")

        if args.check:
            success = check_install(game_dir)
            pause_if_needed(args.no_pause)
            return 0 if success else 2

        if args.restore_latest:
            if game_is_running():
                raise RuntimeError("Aniimo jest uruchomione. Zamknij grę przed przywracaniem.")
            backup = latest_backup()
            restore_backup(game_dir, backup)
            print(f"\nPrzywrócono backup: {backup}")
            pause_if_needed(args.no_pause)
            return 0

        print("Instalowanie języka POLSKI. English pozostaje bez zmian...")
        result = install(game_dir)
        if result["changed"]:
            print("\n[OK] Spolszczenie zostało zainstalowane i zweryfikowane.")
        else:
            print("\n[OK] Spolszczenie jest już aktualne; pliki nie wymagały zmian.")
        if result["backup"]:
            print(f"Backup: {result['backup']}")
        print("W grze wybierz pozycję POLSKI w ustawieniach języka.")
        print("Technicznie używany jest slot vi_VN; język wietnamski zostaje zastąpiony.")
        pause_if_needed(args.no_pause)
        return 0
    except Exception as exc:
        print(f"\n[BŁĄD] {exc}", file=sys.stderr)
        print("Pliki nie zostały pozostawione w stanie częściowo zmodyfikowanym.", file=sys.stderr)
        pause_if_needed(args.no_pause)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
