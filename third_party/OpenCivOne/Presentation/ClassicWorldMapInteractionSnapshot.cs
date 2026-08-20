using OpenCivOne.Graphics;
using OpenCivOne.Runtime;

namespace OpenCivOne.Presentation;

public enum ClassicWorldMapCursorKind
{
	Hidden,
	Pointer,
	Targeting,
}

public readonly record struct ClassicWorldMapCursorSnapshot(
	ClassicWorldMapCursorKind Kind,
	int LogicalX,
	int LogicalY,
	bool IsOverMap,
	int Column,
	int Row)
{
	public static ClassicWorldMapCursorSnapshot Hidden { get; } =
		new(
			ClassicWorldMapCursorKind.Hidden,
			LogicalX: 0,
			LogicalY: 0,
			IsOverMap: false,
			Column: -1,
			Row: -1);

	internal static ClassicWorldMapCursorSnapshot Create(
		ClassicWorldMapCursorKind kind,
		int logicalX,
		int logicalY)
	{
		if (kind == ClassicWorldMapCursorKind.Hidden)
		{
			return Hidden;
		}

		int clampedX = Math.Clamp(logicalX, 0, 319);
		int clampedY = Math.Clamp(logicalY, 0, 199);
		bool isOverMap =
			clampedX >= 80 &&
			clampedY >= 8;
		return new ClassicWorldMapCursorSnapshot(
			kind,
			clampedX,
			clampedY,
			isOverMap,
			isOverMap ? (clampedX - 80) / 16 : -1,
			isOverMap ? (clampedY - 8) / 16 : -1);
	}
}

public readonly record struct ClassicWorldMapSelectionSnapshot(
	int UnitID,
	int MapX,
	int MapY,
	bool IsInViewport,
	int Column,
	int Row);

public readonly record struct ClassicWorldMapPathMarkerSnapshot(
	int Step,
	int MapX,
	int MapY,
	int Column,
	int Row,
	bool IsDestination,
	bool IsPreview);

public enum ClassicWorldMapSettlementSiteKind
{
	Promising,
	Recommended,
}

public readonly record struct ClassicWorldMapSettlementSiteSnapshot(
	int MapX,
	int MapY,
	int Column,
	int Row,
	int Score,
	ClassicWorldMapSettlementSiteKind Kind);

/// <summary>
/// Immutable interaction layer for the human world-map view. All map
/// positions have already passed the human visibility filter.
/// </summary>
public sealed class ClassicWorldMapInteractionSnapshot
{
	private readonly IReadOnlyList<ClassicWorldMapPathMarkerSnapshot>
		pathMarkers;
	private readonly IReadOnlyList<
		ClassicWorldMapSettlementSiteSnapshot> settlementSites;

	internal ClassicWorldMapInteractionSnapshot(
		ClassicWorldMapCursorSnapshot cursor,
		ClassicWorldMapSelectionSnapshot? selection,
		IEnumerable<ClassicWorldMapPathMarkerSnapshot> pathMarkers,
		IEnumerable<ClassicWorldMapSettlementSiteSnapshot>
			settlementSites)
	{
		ArgumentNullException.ThrowIfNull(pathMarkers);
		ArgumentNullException.ThrowIfNull(settlementSites);
		Cursor = cursor;
		Selection = selection;
		this.pathMarkers = Array.AsReadOnly([.. pathMarkers]);
		this.settlementSites =
			Array.AsReadOnly([.. settlementSites]);
	}

	public ClassicWorldMapCursorSnapshot Cursor { get; }

	public ClassicWorldMapSelectionSnapshot? Selection { get; }

	public IReadOnlyList<ClassicWorldMapPathMarkerSnapshot> PathMarkers =>
		this.pathMarkers;

	public IReadOnlyList<ClassicWorldMapSettlementSiteSnapshot>
		SettlementSites => this.settlementSites;
}

internal static class ClassicWorldMapInteractionCapture
{
	private const int MinimumSettlementCityDistance = 4;
	private const int MaximumSettlementRouteSteps = 24;

	private static readonly GPoint[] SettlementMoveDirections =
	[
		new(0, -1),
		new(1, -1),
		new(1, 0),
		new(1, 1),
		new(0, 1),
		new(-1, 1),
		new(-1, 0),
		new(-1, -1),
	];

	public static ClassicWorldMapInteractionSnapshot Capture(
		OpenCivOneGame game,
		ClassicRuntimePresentationSnapshot presentation,
		ClassicWorldMapCursorSnapshot cursor,
		int viewOriginX,
		int viewOriginY)
	{
		ArgumentNullException.ThrowIfNull(game);
		ClassicWorldMapSelectionSnapshot? selection =
			CaptureSelection(
				game,
				presentation,
				viewOriginX,
				viewOriginY);
		bool isPreview =
			game.ActiveHumanGoToPreviewUnitID >= 0;
		IReadOnlyList<ClassicGoToPathCellMarker> sourceMarkers =
			isPreview
				? ClassicGoToPathOverlayPlanner.BuildPreview(
					game.GameData,
					presentation.PlayerID,
					game.ActiveHumanGoToPreviewUnitID,
					game.ActiveHumanGoToPreviewDestination,
					game.ActiveHumanGoToPreviewPath)
				: ClassicGoToPathOverlayPlanner.Build(
					game.GameData,
					presentation.PlayerID,
					game.ActiveHumanGoToPathUnitID);
		List<ClassicWorldMapPathMarkerSnapshot> markers = [];
		int step = 0;
		foreach (ClassicGoToPathCellMarker marker in sourceMarkers)
		{
			int mapX = game.MapManagement.AdjustXPosition(
				marker.Position.X);
			if (!TryMapToViewport(
					game,
					mapX,
					marker.Position.Y,
					viewOriginX,
					viewOriginY,
					out int column,
					out int row))
			{
				step++;
				continue;
			}

			markers.Add(
				new ClassicWorldMapPathMarkerSnapshot(
					step++,
					mapX,
					marker.Position.Y,
					column,
					row,
					marker.IsDestination,
					isPreview));
		}

		return new ClassicWorldMapInteractionSnapshot(
			cursor,
			selection,
			markers,
			CaptureSettlementSites(
				game,
				presentation,
				viewOriginX,
				viewOriginY));
	}

	private static IReadOnlyList<
		ClassicWorldMapSettlementSiteSnapshot> CaptureSettlementSites(
		OpenCivOneGame game,
		ClassicRuntimePresentationSnapshot presentation,
		int viewOriginX,
		int viewOriginY)
	{
		if (!ClassicAiRuntimeProfiles.UsesSmartEnhancements(
				game.GameData.AiProfile) ||
			presentation.IsEndOfTurnPrompt ||
			presentation.ActiveUnitID < 0 ||
			presentation.PlayerID < 0 ||
			presentation.PlayerID >=
				game.GameData.Players.Length)
		{
			return [];
		}

		Player player =
			game.GameData.Players[presentation.PlayerID];
		if (presentation.ActiveUnitID >= player.Units.Length)
		{
			return [];
		}

		Unit unit = player.Units[presentation.ActiveUnitID];
		if (unit.UnitType != UnitTypeEnum.Settler ||
			unit.PlayerID != presentation.PlayerID)
		{
			return [];
		}

		int visibilityMask = 1 << presentation.PlayerID;
		int[,] knownLandDistances = BuildKnownLandDistances(
			game,
			presentation.PlayerID,
			unit.Position);
		List<(
			int MapX,
			int MapY,
			int Column,
			int Row,
			int Score,
			int RouteSteps,
			int NearestCityDistance,
			int StrategicScore)> candidates = [];
		for (int row = 0;
			row < ClassicWorldMapViewportSnapshot.RowCount;
			row++)
		{
			int mapY = viewOriginY + row;
			if (mapY < 2 || mapY >= 48)
			{
				continue;
			}

			for (int column = 0;
				column < ClassicWorldMapViewportSnapshot.ColumnCount;
				column++)
			{
				int mapX = game.MapManagement.AdjustXPosition(
					viewOriginX + column);
				if ((game.GameData.MapVisibility[mapX, mapY] &
						visibilityMask) == 0 ||
					game.MapManagement.GetTerrainType(mapX, mapY) ==
						TerrainTypeEnum.Water ||
					knownLandDistances[mapX, mapY] < 0 ||
					knownLandDistances[mapX, mapY] >
						MaximumSettlementRouteSteps ||
					game.MapManagement
						.F0_2aea_1585_GetVisibleTerrainImprovements(
							mapX,
							mapY)
						.HasFlag(
							TerrainImprovementFlagsEnum.City))
				{
					continue;
				}

				int buildScore =
					game.MapManagement
						.GetBuildLocationScore(mapX, mapY);
				int nearestCityDistance =
					GetNearestKnownCityDistance(
						game,
						presentation.PlayerID,
						new GPoint(mapX, mapY));
				if (buildScore < 8 ||
					nearestCityDistance <
						MinimumSettlementCityDistance)
				{
					continue;
				}

				int routeSteps =
					knownLandDistances[mapX, mapY];
				int strategicScore =
					(buildScore * 100) +
					(Math.Min(nearestCityDistance, 8) * 75) -
					(routeSteps * 5);
				candidates.Add(
					(
						mapX,
						mapY,
						column,
						row,
						buildScore,
						routeSteps,
						nearestCityDistance,
						strategicScore));
			}
		}

		if (candidates.Count == 0)
		{
			return [];
		}

		var ordered = candidates
			.OrderByDescending(candidate => candidate.StrategicScore)
			.ThenByDescending(candidate => candidate.Score)
			.ThenByDescending(candidate =>
				candidate.NearestCityDistance)
			.ThenBy(candidate => candidate.RouteSteps)
			.ThenBy(candidate => candidate.Row)
			.ThenBy(candidate => candidate.Column)
			.ToArray();
		var best = ordered[0];
		List<ClassicWorldMapSettlementSiteSnapshot> markers =
		[
			new(
				best.MapX,
				best.MapY,
				best.Column,
				best.Row,
				best.Score,
				ClassicWorldMapSettlementSiteKind.Recommended),
		];
		foreach (var candidate in ordered
			.Skip(1)
			.Where(candidate =>
				candidate.StrategicScore >=
					best.StrategicScore - 150)
			.Take(4))
		{
			markers.Add(
				new ClassicWorldMapSettlementSiteSnapshot(
					candidate.MapX,
					candidate.MapY,
					candidate.Column,
					candidate.Row,
					candidate.Score,
					ClassicWorldMapSettlementSiteKind.Promising));
		}

		return markers;
	}

	private static int[,] BuildKnownLandDistances(
		OpenCivOneGame game,
		int playerID,
		GPoint start)
	{
		int width = game.GameData.MapVisibility.GetLength(0);
		int height = game.GameData.MapVisibility.GetLength(1);
		int[,] distances = new int[width, height];
		for (int y = 0; y < height; y++)
		{
			for (int x = 0; x < width; x++)
			{
				distances[x, y] = -1;
			}
		}

		int startX =
			game.MapManagement.AdjustXPosition(start.X);
		if (start.Y < 0 ||
			start.Y >= height ||
			(game.GameData.MapVisibility[startX, start.Y] &
				(1 << playerID)) == 0 ||
			game.MapManagement.GetTerrainType(startX, start.Y) ==
				TerrainTypeEnum.Water)
		{
			return distances;
		}

		Queue<GPoint> frontier = new();
		distances[startX, start.Y] = 0;
		frontier.Enqueue(new GPoint(startX, start.Y));
		while (frontier.Count > 0)
		{
			GPoint position = frontier.Dequeue();
			int nextDistance =
				distances[position.X, position.Y] + 1;
			if (nextDistance > MaximumSettlementRouteSteps)
			{
				continue;
			}

			foreach (GPoint direction in
				SettlementMoveDirections)
			{
				int nextX =
					game.MapManagement.AdjustXPosition(
						position.X + direction.X);
				int nextY = position.Y + direction.Y;
				if (nextY < 0 ||
					nextY >= height ||
					distances[nextX, nextY] >= 0 ||
					(game.GameData.MapVisibility[nextX, nextY] &
						(1 << playerID)) == 0 ||
					game.MapManagement.GetTerrainType(nextX, nextY) ==
						TerrainTypeEnum.Water)
				{
					continue;
				}

				distances[nextX, nextY] = nextDistance;
				frontier.Enqueue(new GPoint(nextX, nextY));
			}
		}

		return distances;
	}

	private static int GetNearestKnownCityDistance(
		OpenCivOneGame game,
		int playerID,
		GPoint position)
	{
		int nearestDistance = int.MaxValue;
		foreach (City city in game.GameData.Cities)
		{
			bool isActive =
				city.StatusFlag != byte.MaxValue &&
				city.ActualSize > 0;
			bool isKnown =
				city.PlayerID == playerID ||
				(city.PlayerID > 0 &&
				 city.PlayerID < game.GameData.Players.Length &&
				 city.Position.Y >= 0 &&
				 city.Position.Y <
					game.GameData.MapVisibility.GetLength(1) &&
				 city.VisibleSize > 0 &&
				 (game.GameData.MapVisibility[
					game.MapManagement.AdjustXPosition(
						city.Position.X),
					city.Position.Y] &
				  (1 << playerID)) != 0);
			if (!isActive || !isKnown)
			{
				continue;
			}

			nearestDistance = Math.Min(
				nearestDistance,
				game.Tools.F0_2dc4_0289_GetShortestDistance(
					position,
					city.Position));
		}

		return nearestDistance;
	}

	private static ClassicWorldMapSelectionSnapshot? CaptureSelection(
		OpenCivOneGame game,
		ClassicRuntimePresentationSnapshot presentation,
		int viewOriginX,
		int viewOriginY)
	{
		if (presentation.ActiveUnitID < 0 ||
			presentation.PlayerID < 0 ||
			presentation.PlayerID >= game.GameData.Players.Length)
		{
			return null;
		}

		Player player = game.GameData.Players[presentation.PlayerID];
		if (presentation.ActiveUnitID >= player.Units.Length)
		{
			return null;
		}

		Unit unit = player.Units[presentation.ActiveUnitID];
		if (unit.UnitType == UnitTypeEnum.None ||
			unit.PlayerID != presentation.PlayerID)
		{
			return null;
		}

		int mapX = game.MapManagement.AdjustXPosition(unit.Position.X);
		bool isInViewport = TryMapToViewport(
			game,
			mapX,
			unit.Position.Y,
			viewOriginX,
			viewOriginY,
			out int column,
			out int row);
		return new ClassicWorldMapSelectionSnapshot(
			presentation.ActiveUnitID,
			mapX,
			unit.Position.Y,
			isInViewport,
			isInViewport ? column : -1,
			isInViewport ? row : -1);
	}

	private static bool TryMapToViewport(
		OpenCivOneGame game,
		int mapX,
		int mapY,
		int viewOriginX,
		int viewOriginY,
		out int column,
		out int row)
	{
		row = mapY - viewOriginY;
		if (row < 0 ||
			row >= ClassicWorldMapViewportSnapshot.RowCount)
		{
			column = -1;
			row = -1;
			return false;
		}

		for (column = 0;
			column < ClassicWorldMapViewportSnapshot.ColumnCount;
			column++)
		{
			if (game.MapManagement.AdjustXPosition(
					viewOriginX + column) == mapX)
			{
				return true;
			}
		}

		column = -1;
		row = -1;
		return false;
	}
}
