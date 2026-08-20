namespace OpenCivOne.Presentation;

public enum ClassicWorldMapMinimapCellKind : byte
{
	Unknown,
	Water,
	Land,
}

public readonly record struct ClassicWorldMapMinimapCityMarker(
	int PlayerID,
	int DisplayX,
	int DisplayY);

/// <summary>
/// Immutable semantic copy of the source-faithful 80-by-50 minimap display.
/// Cell values come from Classic's human-visible minimap plane; city markers
/// follow the same last-known-size rule as the original renderer.
/// </summary>
public sealed class ClassicWorldMapMinimapSnapshot
{
	public const int Width = 80;
	public const int Height = 50;
	public const int ViewportOutlineWidth = 17;
	public const int ViewportOutlineHeight = 10;

	private readonly IReadOnlyList<ClassicWorldMapMinimapCellKind> cells;
	private readonly IReadOnlyList<ClassicWorldMapMinimapCityMarker>
		cityMarkers;

	internal ClassicWorldMapMinimapSnapshot(
		int sourceMapX,
		int sourceMapY,
		int topPadding,
		int viewportOutlineLeft,
		int viewportOutlineTop,
		IEnumerable<ClassicWorldMapMinimapCellKind> cells,
		IEnumerable<ClassicWorldMapMinimapCityMarker> cityMarkers)
	{
		ArgumentNullException.ThrowIfNull(cells);
		ArgumentNullException.ThrowIfNull(cityMarkers);
		ClassicWorldMapMinimapCellKind[] capturedCells = [.. cells];
		if (capturedCells.Length != Width * Height)
		{
			throw new ArgumentException(
				$"A minimap needs exactly {Width * Height} cells.",
				nameof(cells));
		}

		SourceMapX = sourceMapX;
		SourceMapY = sourceMapY;
		TopPadding = topPadding;
		ViewportOutlineLeft = viewportOutlineLeft;
		ViewportOutlineTop = viewportOutlineTop;
		this.cells = Array.AsReadOnly(capturedCells);
		this.cityMarkers = Array.AsReadOnly(
			cityMarkers.ToArray());
	}

	public int SourceMapX { get; }

	public int SourceMapY { get; }

	public int TopPadding { get; }

	public int ViewportOutlineLeft { get; }

	public int ViewportOutlineTop { get; }

	public IReadOnlyList<ClassicWorldMapMinimapCellKind> Cells =>
		this.cells;

	public IReadOnlyList<ClassicWorldMapMinimapCityMarker> CityMarkers =>
		this.cityMarkers;

	public ClassicWorldMapMinimapCellKind GetCell(
		int displayX,
		int displayY)
	{
		if (displayX < 0 || displayX >= Width)
		{
			throw new ArgumentOutOfRangeException(nameof(displayX));
		}

		if (displayY < 0 || displayY >= Height)
		{
			throw new ArgumentOutOfRangeException(nameof(displayY));
		}

		return this.cells[(displayY * Width) + displayX];
	}
}

internal static class ClassicWorldMapMinimapCapture
{
	public static ClassicWorldMapMinimapSnapshot Capture(
		OpenCivOneGame game)
	{
		ArgumentNullException.ThrowIfNull(game);
		int sourceMapX = game.MapManagement.AdjustXPosition(
			game.Var_6ed6_MiniMapX);
		int sourceMapY = Math.Max(game.Var_70ea_MiniMapY, 0);
		int topPadding = sourceMapY - game.Var_70ea_MiniMapY;
		List<ClassicWorldMapMinimapCellKind> cells =
			new(ClassicWorldMapMinimapSnapshot.Width *
				ClassicWorldMapMinimapSnapshot.Height);

		for (int displayY = 0;
			displayY < ClassicWorldMapMinimapSnapshot.Height;
			displayY++)
		{
			int mapY = sourceMapY + displayY - topPadding;
			for (int displayX = 0;
				displayX < ClassicWorldMapMinimapSnapshot.Width;
				displayX++)
			{
				if (mapY < 0 || mapY >= 50)
				{
					cells.Add(
						ClassicWorldMapMinimapCellKind.Unknown);
					continue;
				}

				int mapX = game.MapManagement.AdjustXPosition(
					sourceMapX + displayX);
				cells.Add(
					game.MapManagement.GetMiniMapCell(mapX, mapY)
						switch
						{
							1 => ClassicWorldMapMinimapCellKind.Water,
							2 => ClassicWorldMapMinimapCellKind.Land,
							_ => ClassicWorldMapMinimapCellKind.Unknown,
						});
			}
		}

		List<ClassicWorldMapMinimapCityMarker> cityMarkers = [];
		foreach (City city in game.GameData.Cities)
		{
			if (city.StatusFlag == byte.MaxValue ||
				(city.VisibleSize == 0 &&
					city.PlayerID != game.GameData.HumanPlayerID) ||
				city.PlayerID < 0 ||
				city.PlayerID >= game.GameData.Players.Length)
			{
				continue;
			}

			int displayY =
				city.Position.Y - sourceMapY + topPadding;
			if (displayY < 0 ||
				displayY >= ClassicWorldMapMinimapSnapshot.Height)
			{
				continue;
			}

			cityMarkers.Add(
				new ClassicWorldMapMinimapCityMarker(
					city.PlayerID,
					game.MapManagement.AdjustXPosition(
						city.Position.X - sourceMapX),
					displayY));
		}

		int viewportOutlineLeft =
			game.MapManagement.AdjustXPosition(
				game.Var_d4cc_MapViewX - sourceMapX) -
			1;
		int viewportOutlineTop =
			game.Var_d75e_MapViewY -
			sourceMapY +
			topPadding -
			1;
		return new ClassicWorldMapMinimapSnapshot(
			sourceMapX,
			sourceMapY,
			topPadding,
			viewportOutlineLeft,
			viewportOutlineTop,
			cells,
			cityMarkers);
	}
}
