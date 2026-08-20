"""Runtime contracts for the Project 1991 AA tile kit.

The package intentionally contains no fallback art.  Missing production assets are
reported as errors so a technically valid proof cannot silently regress to a
prototype-looking presentation.
"""

from .assets import AssetLoader, LoadedSprite, MissingAssetError
from .coast import CoastMaskFactory, CoastMasks
from .compositor import OrthographicCompositor, draw_grid_overlay
from .contract import Manifest, ManifestError, load_manifest
from .materials import WorldMaterialSampler
from .rivers import Direction, RiverMask, RiverStampRegistry

__all__ = [
    "AssetLoader",
    "CoastMaskFactory",
    "CoastMasks",
    "Direction",
    "LoadedSprite",
    "Manifest",
    "ManifestError",
    "MissingAssetError",
    "OrthographicCompositor",
    "RiverMask",
    "RiverStampRegistry",
    "WorldMaterialSampler",
    "draw_grid_overlay",
    "load_manifest",
]
