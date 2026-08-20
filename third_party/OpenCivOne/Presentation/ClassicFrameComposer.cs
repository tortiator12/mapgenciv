using OpenCivOne.Graphics;

namespace OpenCivOne.Presentation;

/// <summary>
/// Converts the reconstructed indexed screens and their active palettes into
/// one platform-neutral BGRA8888 frame without scaling or filtering.
/// </summary>
public static class ClassicFrameComposer
{
	public static ClassicFrame Compose(
		IReadOnlyList<GBitmap> screens,
		int columns,
		int rows,
		int screenWidth = 320,
		int screenHeight = 200)
	{
		ArgumentNullException.ThrowIfNull(screens);
		ArgumentOutOfRangeException.ThrowIfNegativeOrZero(columns);
		ArgumentOutOfRangeException.ThrowIfNegativeOrZero(rows);
		ArgumentOutOfRangeException.ThrowIfNegativeOrZero(screenWidth);
		ArgumentOutOfRangeException.ThrowIfNegativeOrZero(screenHeight);

		if (screens.Count > columns * rows)
		{
			throw new ArgumentException(
				"The requested frame layout cannot contain all visible screens.",
				nameof(screens));
		}

		int frameWidth = checked(columns * screenWidth);
		int frameHeight = checked(rows * screenHeight);
		int[] pixels = new int[checked(frameWidth * frameHeight)];
		Array.Fill(pixels, unchecked((int)0xff000000));

		for (int screenIndex = 0; screenIndex < screens.Count; screenIndex++)
		{
			GBitmap screen = screens[screenIndex];
			int column = screenIndex % columns;
			int row = screenIndex / columns;
			int copyWidth = Math.Min(screenWidth, screen.Width);
			int copyHeight = Math.Min(screenHeight, screen.Height);

			for (int y = 0; y < copyHeight; y++)
			{
				int destinationOffset =
					((row * screenHeight + y) * frameWidth) +
					(column * screenWidth);

				for (int x = 0; x < copyWidth; x++)
				{
					byte colorIndex = screen.GetPixel(x, y);
					pixels[destinationOffset + x] =
						ToOpaqueArgb(screen.Palette[colorIndex].ToUInt32());
				}
			}
		}

		return new ClassicFrame(frameWidth, frameHeight, pixels);
	}

	private static int ToOpaqueArgb(uint color) =>
		unchecked((int)(color | 0xff000000));
}
