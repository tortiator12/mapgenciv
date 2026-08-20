"""World-coordinate material sampling without per-tile texture resets.

The Civ 1 world wraps horizontally.  A source texture's own width is unrelated
to that world circumference, so merely repeating the PNG is not sufficient:
the phase would usually jump at the 79 -> 0 tile seam.  ``world_period_x`` maps
an integer number of texture repetitions onto the exact world circumference.
"""

from __future__ import annotations

import numpy as np
from PIL import Image


class WorldMaterialSampler:
    """Sample a texture in world pixel coordinates.

    Adjacent calls share the same phase.  Rendering tile ``(x, y)`` therefore uses
    ``world_x=x*tile_width`` and ``world_y=y*tile_height`` instead of restarting a
    texture at each tile boundary.

    With no keyword arguments the historical behaviour is preserved: the PNG
    repeats at its native width.  Supplying ``world_period_x`` makes the result
    exactly periodic at that many world pixels, independently of the PNG width.
    ``repeats`` controls how often the source art appears inside that period.  If
    omitted, the closest positive repeat count to native 1:1 texel density is
    selected.  Horizontal resampling is linear and circular, including between
    the PNG's final and first columns. ``seamless_edge_feather`` opt-in blends
    only an outer source band toward a content-selected adjacent cut on both
    axes, removing non-tileable PNG edge jumps while leaving the central
    artwork unchanged.
    """

    def __init__(
        self,
        texture: Image.Image,
        *,
        world_period_x: int | None = None,
        repeats: int | None = None,
        seamless_edge_feather: int = 0,
    ):
        if texture.width <= 0 or texture.height <= 0:
            raise ValueError("texture dimensions must be positive")
        self.texture = texture.convert("RGBA")
        if world_period_x is not None and (
            isinstance(world_period_x, bool)
            or not isinstance(world_period_x, int)
            or world_period_x <= 0
        ):
            raise ValueError("world_period_x must be a positive integer")
        if repeats is not None and (
            isinstance(repeats, bool)
            or not isinstance(repeats, int)
            or repeats <= 0
        ):
            raise ValueError("repeats must be a positive integer")
        if world_period_x is None and repeats is not None:
            raise ValueError("repeats requires world_period_x")
        if (
            isinstance(seamless_edge_feather, bool)
            or not isinstance(seamless_edge_feather, int)
            or seamless_edge_feather < 0
        ):
            raise ValueError("seamless_edge_feather must be a non-negative integer")
        if seamless_edge_feather > 0 and (
            seamless_edge_feather * 2 >= self.texture.width
            or seamless_edge_feather * 2 >= self.texture.height
        ):
            raise ValueError("seamless_edge_feather must be smaller than half the texture")

        self.seamless_edge_feather = seamless_edge_feather
        self.seamless_edge_anchors: tuple[int, int] | None = None
        if seamless_edge_feather:
            self.texture, self.seamless_edge_anchors = self._feather_toroidal_edges(
                self.texture, seamless_edge_feather
            )

        self.world_period_x = world_period_x
        if world_period_x is None:
            self.repeats = 1
        elif repeats is None:
            # Nearest integer number of source-width repetitions.  Integer
            # arithmetic avoids Python's banker rounding at exact half steps.
            self.repeats = max(
                1,
                (world_period_x + self.texture.width // 2) // self.texture.width,
            )
        else:
            self.repeats = repeats

        self._pixels: np.ndarray | None = None

    @staticmethod
    def _feather_toroidal_edges(
        texture: Image.Image, feather: int
    ) -> tuple[Image.Image, tuple[int, int]]:
        """Remove source-PNG wrap jumps without changing its central artwork.

        Inside a narrow outer band, the original is eased into a shifted copy.
        Its cut is the lowest RGB neighbour-gradient in the source's central
        half, so the first and last output samples become a natural adjacent
        source pair. The same construction is applied on both axes, making
        native repeats toroidal while preserving the unmodified centre and
        avoiding mirrored motifs. Fixed-point weights and integer cut scoring
        keep separate renderer processes byte-identical.
        """

        pixels = np.asarray(texture.convert("RGBA"), dtype=np.uint8)
        weight_scale = 65535
        source_rgb = pixels[..., :3].astype(np.int16)
        anchors: dict[int, int] = {}
        for axis, length in ((1, texture.width), (0, texture.height)):
            if axis == 1:
                gradients = np.abs(
                    source_rgb[:, 1:, :] - source_rgb[:, :-1, :]
                ).sum(
                    axis=(0, 2)
                )
            else:
                gradients = np.abs(
                    source_rgb[1:, :, :] - source_rgb[:-1, :, :]
                ).sum(
                    axis=(1, 2)
                )
            first_cut = max(1, length // 4)
            last_cut = min(length - 1, length - length // 4)
            anchors[axis] = first_cut + int(
                np.argmin(gradients[first_cut - 1 : last_cut - 1])
            )

        for axis, length in ((1, texture.width), (0, texture.height)):
            anchor = anchors[axis]
            coordinate = np.arange(length, dtype=np.int64)
            distance = np.minimum(coordinate, length - 1 - coordinate)
            t = np.clip((feather - distance) / float(feather), 0.0, 1.0)
            smooth = t * t * (3.0 - 2.0 * t)
            weights = np.rint(smooth * weight_scale).astype(np.int64)
            shape = [1, 1, 1]
            shape[axis] = length
            weights = weights.reshape(shape)
            shifted = np.roll(pixels, -anchor, axis=axis)
            mixed = (
                pixels.astype(np.int64) * (weight_scale - weights)
                + shifted.astype(np.int64) * weights
                + weight_scale // 2
            ) // weight_scale
            pixels = mixed.astype(np.uint8)
        return Image.fromarray(pixels, "RGBA"), (anchors[1], anchors[0])

    def _sample_native(
        self,
        world_x: int,
        world_y: int,
        width: int,
        height: int,
    ) -> Image.Image:
        """Original integer-copy sampler retained for full compatibility."""

        result = Image.new("RGBA", (width, height))
        texture_w, texture_h = self.texture.size
        dest_y = 0
        source_y = world_y % texture_h
        while dest_y < height:
            chunk_h = min(texture_h - source_y, height - dest_y)
            dest_x = 0
            source_x = world_x % texture_w
            while dest_x < width:
                chunk_w = min(texture_w - source_x, width - dest_x)
                crop = self.texture.crop(
                    (source_x, source_y, source_x + chunk_w, source_y + chunk_h)
                )
                result.paste(crop, (dest_x, dest_y))
                dest_x += chunk_w
                source_x = 0
            dest_y += chunk_h
            source_y = 0
        return result

    def _sample_at_world_period(
        self,
        world_x: int,
        world_y: int,
        width: int,
        height: int,
    ) -> Image.Image:
        """Circular-linear horizontal sample at the declared world period."""

        period = self.world_period_x
        assert period is not None
        texture_w, texture_h = self.texture.size

        # Reduce the Python integer before entering fixed-width NumPy arithmetic;
        # this also makes x and x + N*period take the exact same code path.
        world_phase = world_x % period
        wrapped_x = (world_phase + np.arange(width, dtype=np.int64)) % period
        phase_numerator = wrapped_x * (texture_w * self.repeats)
        source_base = phase_numerator // period
        right_weight = phase_numerator % period
        left_weight = period - right_weight
        source_x0 = source_base % texture_w
        source_x1 = (source_x0 + 1) % texture_w

        source_y = (
            world_y % texture_h + np.arange(height, dtype=np.int64)
        ) % texture_h
        if self._pixels is None:
            self._pixels = np.asarray(self.texture, dtype=np.uint8)
        rows = self._pixels[source_y]
        # All interpolation terms are non-negative and tightly bounded:
        # 255 * period * 2 + period/2 is below four million for the locked
        # 7680-pixel Civ world.  uint32 is therefore exact here and halves the
        # three large temporary arrays compared with int64.  This matters when
        # several world chunks render concurrently on a 16-GB machine.
        left = rows[:, source_x0, :].astype(np.uint32)
        right = rows[:, source_x1, :].astype(np.uint32)
        left_weight = left_weight.astype(np.uint32, copy=False)
        right_weight = right_weight.astype(np.uint32, copy=False)

        # Fixed-point interpolation makes separately rendered crops byte-for-byte
        # identical to one large render.  The half-period term rounds to nearest.
        mixed = (
            left * left_weight[None, :, None]
            + right * right_weight[None, :, None]
            + np.uint32(period // 2)
        ) // np.uint32(period)
        return Image.fromarray(mixed.astype(np.uint8), "RGBA")

    def sample(
        self,
        world_x: int,
        world_y: int,
        width: int,
        height: int,
    ) -> Image.Image:
        if width <= 0 or height <= 0:
            raise ValueError("sample dimensions must be positive")
        if self.world_period_x is None:
            return self._sample_native(world_x, world_y, width, height)
        return self._sample_at_world_period(world_x, world_y, width, height)

    def sample_tile(
        self,
        tile_x: int,
        tile_y: int,
        tile_size: tuple[int, int] = (96, 96),
    ) -> Image.Image:
        width, height = tile_size
        return self.sample(tile_x * width, tile_y * height, width, height)


def compose_samples_horizontally(samples: list[Image.Image]) -> Image.Image:
    """Small test/proof helper; requires equal-height RGBA samples."""

    if not samples:
        raise ValueError("samples cannot be empty")
    height = samples[0].height
    if any(sample.height != height for sample in samples):
        raise ValueError("all samples must have equal heights")
    result = Image.new("RGBA", (sum(sample.width for sample in samples), height))
    cursor = 0
    for sample in samples:
        result.alpha_composite(sample.convert("RGBA"), (cursor, 0))
        cursor += sample.width
    return result
