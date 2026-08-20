using OpenCivOne.Graphics;

namespace OpenCivOne.Presentation;

/// <summary>
/// Composes an indexed Classic cursor over a copy of an already composed
/// frame. Palette index zero remains transparent and non-zero indices resolve
/// through the active target-screen palette, matching indexed
/// <see cref="GBitmap.DrawBitmap(int, int, GBitmap, bool)"/> semantics.
/// </summary>
public static class ClassicCursorComposer
{
	public static ClassicFrame Compose(
		ClassicFrame frame,
		GBitmap cursor,
		GBitmapPalette targetPalette,
		int pointerX,
		int pointerY,
		int hotspotX = 0,
		int hotspotY = 0)
	{
		ArgumentNullException.ThrowIfNull(frame);
		ArgumentNullException.ThrowIfNull(cursor);
		ArgumentNullException.ThrowIfNull(targetPalette);

		int[] pixels = (int[])frame.Pixels.Clone();
		ComposePixels(
			frame,
			pixels,
			cursor,
			targetPalette,
			pointerX,
			pointerY,
			hotspotX,
			hotspotY);
		return new ClassicFrame(frame.Width, frame.Height, pixels);
	}

	/// <summary>
	/// Composes into a frame buffer owned by the caller. The Classic runtime
	/// uses this after <see cref="ClassicFrameComposer"/> has produced a fresh
	/// frame, avoiding another full-frame allocation at display refresh rate.
	/// </summary>
	public static void ComposeInPlace(
		ClassicFrame frame,
		GBitmap cursor,
		GBitmapPalette targetPalette,
		int pointerX,
		int pointerY,
		int hotspotX = 0,
		int hotspotY = 0)
	{
		ArgumentNullException.ThrowIfNull(frame);
		ArgumentNullException.ThrowIfNull(cursor);
		ArgumentNullException.ThrowIfNull(targetPalette);
		ComposePixels(
			frame,
			frame.Pixels,
			cursor,
			targetPalette,
			pointerX,
			pointerY,
			hotspotX,
			hotspotY);
	}

	private static void ComposePixels(
		ClassicFrame frame,
		int[] pixels,
		GBitmap cursor,
		GBitmapPalette targetPalette,
		int pointerX,
		int pointerY,
		int hotspotX,
		int hotspotY)
	{
		int expectedPixelCount = checked(frame.Width * frame.Height);
		if (frame.Width <= 0 ||
			frame.Height <= 0 ||
			frame.Pixels.Length != expectedPixelCount ||
			pixels.Length != expectedPixelCount)
		{
			throw new ArgumentException(
				"The Classic frame dimensions do not match its pixel buffer.",
				nameof(frame));
		}

		for (int i = 0; i < pixels.Length; i++)
		{
			pixels[i] = ToOpaqueArgb(unchecked((uint)pixels[i]));
		}

		int destinationX = pointerX - hotspotX;
		int destinationY = pointerY - hotspotY;
		int sourceLeft = Math.Max(0, -destinationX);
		int sourceTop = Math.Max(0, -destinationY);
		int sourceRight = Math.Min(cursor.Width, frame.Width - destinationX);
		int sourceBottom = Math.Min(cursor.Height, frame.Height - destinationY);

		for (int sourceY = sourceTop; sourceY < sourceBottom; sourceY++)
		{
			int frameOffset = (destinationY + sourceY) * frame.Width;

			for (int sourceX = sourceLeft; sourceX < sourceRight; sourceX++)
			{
				byte colorIndex = cursor.GetPixel(sourceX, sourceY);
				if (colorIndex != 0)
				{
					pixels[frameOffset + destinationX + sourceX] =
						ToOpaqueArgb(targetPalette[colorIndex].ToUInt32());
				}
			}
		}

	}

	private static int ToOpaqueArgb(uint color) =>
		unchecked((int)(color | 0xff000000));
}
