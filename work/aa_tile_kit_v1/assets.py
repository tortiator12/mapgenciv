"""Safe asset loading with alpha trimming that preserves visual anchors."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .contract import Manifest, MaterialSpec, RiverStampSpec, SpriteSpec


class MissingAssetError(FileNotFoundError):
    """A declared production asset is absent; no prototype fallback is used."""


class AssetFormatError(ValueError):
    """An asset violates dimensions, alpha, or color-mode requirements."""


@dataclass(frozen=True)
class LoadedSprite:
    image: Image.Image
    anchor_px: tuple[float, float]
    source_size: tuple[int, int]
    trim_box: tuple[int, int, int, int]

    @property
    def size(self) -> tuple[int, int]:
        return self.image.size


class AssetLoader:
    """Loads only paths rooted beneath the manifest directory."""

    def __init__(self, manifest: Manifest):
        self.manifest = manifest
        self._root = manifest.root.resolve()
        self._images: dict[tuple[str, bool], Image.Image | LoadedSprite] = {}

    def _resolve(self, relative: str) -> Path:
        path = (self._root / relative).resolve()
        try:
            path.relative_to(self._root)
        except ValueError as exc:
            raise AssetFormatError(f"asset escapes tile-kit root: {relative}") from exc
        return path

    def _open_rgba(self, relative: str, *, required: bool) -> Image.Image | None:
        path = self._resolve(relative)
        if not path.is_file():
            if required:
                raise MissingAssetError(f"missing production asset: {path}")
            return None
        try:
            with Image.open(path) as source:
                source.load()
                return source.convert("RGBA")
        except OSError as exc:
            raise AssetFormatError(f"cannot decode asset {path}: {exc}") from exc

    @staticmethod
    def alpha_trim(
        image: Image.Image,
        anchor: tuple[float, float] = (0.5, 1.0),
        *,
        threshold: int = 1,
    ) -> LoadedSprite:
        """Trim transparent padding while retaining the original anchor position."""

        if not 0 <= threshold <= 255:
            raise ValueError("threshold must be between 0 and 255")
        rgba = image.convert("RGBA")
        source_size = rgba.size
        alpha = rgba.getchannel("A")
        if threshold > 1:
            alpha = alpha.point(lambda value: 255 if value >= threshold else 0)
        bbox = alpha.getbbox()
        if bbox is None:
            raise AssetFormatError("sprite contains no visible alpha")
        left, top, right, bottom = bbox
        trimmed = rgba.crop(bbox)
        anchor_source_x = anchor[0] * source_size[0]
        anchor_source_y = anchor[1] * source_size[1]
        return LoadedSprite(
            image=trimmed,
            anchor_px=(anchor_source_x - left, anchor_source_y - top),
            source_size=source_size,
            trim_box=bbox,
        )

    def load_material(self, key: str) -> Image.Image:
        spec: MaterialSpec
        try:
            spec = self.manifest.materials[key]
        except KeyError as exc:
            raise KeyError(f"unknown material: {key}") from exc
        cache_key = (f"material:{key}", False)
        cached = self._images.get(cache_key)
        if isinstance(cached, Image.Image):
            return cached.copy()
        image = self._open_rgba(spec.file, required=spec.required)
        if image is None:
            raise MissingAssetError(f"optional material {key!r} is not available")
        if image.width < self.manifest.tile.width or image.height < self.manifest.tile.height:
            raise AssetFormatError(
                f"material {key!r} is {image.size}; minimum is {self.manifest.tile.size}"
            )
        self._images[cache_key] = image
        return image.copy()

    def load_sprite(self, key: str, *, trim: bool = True) -> LoadedSprite:
        spec: SpriteSpec
        try:
            spec = self.manifest.sprites[key]
        except KeyError as exc:
            raise KeyError(f"unknown sprite: {key}") from exc
        cache_key = (f"sprite:{key}", trim)
        cached = self._images.get(cache_key)
        if isinstance(cached, LoadedSprite):
            return LoadedSprite(
                cached.image.copy(), cached.anchor_px, cached.source_size, cached.trim_box
            )
        image = self._open_rgba(spec.file, required=spec.required)
        if image is None:
            raise MissingAssetError(f"optional sprite {key!r} is not available")
        if trim:
            loaded = self.alpha_trim(image, spec.anchor)
        else:
            loaded = LoadedSprite(
                image=image,
                anchor_px=(spec.anchor[0] * image.width, spec.anchor[1] * image.height),
                source_size=image.size,
                trim_box=(0, 0, image.width, image.height),
            )
        self._images[cache_key] = loaded
        return LoadedSprite(
            loaded.image.copy(), loaded.anchor_px, loaded.source_size, loaded.trim_box
        )

    def load_river_stamp(self, mask: int) -> Image.Image:
        spec: RiverStampSpec
        try:
            spec = self.manifest.river_stamps[mask]
        except KeyError as exc:
            raise KeyError(f"unknown river mask: {mask}") from exc
        cache_key = (f"river:{mask}", False)
        cached = self._images.get(cache_key)
        if isinstance(cached, Image.Image):
            return cached.copy()
        image = self._open_rgba(spec.file, required=spec.required)
        if image is None:
            raise MissingAssetError(f"optional river stamp {mask} is not available")
        if image.size != self.manifest.tile.size:
            raise AssetFormatError(
                f"river stamp {mask} must be exactly {self.manifest.tile.size}, got {image.size}"
            )
        self._images[cache_key] = image
        return image.copy()

    def validate_required_files(self) -> list[str]:
        """Return every missing required path without stopping at the first one."""

        missing: list[str] = []
        specs = [*self.manifest.materials.values(), *self.manifest.sprites.values()]
        specs.extend(self.manifest.river_stamps.values())
        for spec in specs:
            if spec.required and not self._resolve(spec.file).is_file():
                missing.append(spec.file)
        return sorted(missing)
