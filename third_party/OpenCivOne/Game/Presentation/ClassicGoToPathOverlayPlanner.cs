using OpenCivOne.Graphics;
using OpenCivOne.Runtime;

namespace OpenCivOne;

/// <summary>A visible map marker for the selected human Go To route.</summary>
public readonly record struct ClassicGoToPathCellMarker(
	GPoint Position,
	bool IsDestination);

/// <summary>
/// Builds the 1991+ Go To overlay without mutating game state. Only waypoints
/// of the selected human unit are considered and every returned cell must
/// already be visible to the human player.
/// </summary>
public static class ClassicGoToPathOverlayPlanner
{
	private const int MapHeight = 50;

	public static IReadOnlyList<ClassicGoToPathCellMarker> Build(
		GameData gameData,
		int playerID,
		int selectedUnitID)
	{
		ArgumentNullException.ThrowIfNull(gameData);

		if (!ClassicAiRuntimeProfiles.UsesSmartEnhancements(
				gameData.AiProfile) ||
			!gameData.GameSettingFlags.ShowGoToPaths ||
			playerID != gameData.HumanPlayerID ||
			playerID < 0 ||
			playerID >= gameData.Players.Length ||
			selectedUnitID < 0 ||
			selectedUnitID >= gameData.Players[playerID].Units.Length)
		{
			return Array.Empty<ClassicGoToPathCellMarker>();
		}

		Unit unit = gameData.Players[playerID].Units[selectedUnitID];
		if (unit.UnitType == UnitTypeEnum.None ||
			unit.PlayerID != playerID ||
			unit.GoToDestination == OpenCivOneGame.InvalidPosition ||
			unit.GoToPath.Count == 0)
		{
			return Array.Empty<ClassicGoToPathCellMarker>();
		}

		return BuildVisibleMarkers(
			gameData,
			playerID,
			unit.Position,
			unit.GoToDestination,
			unit.GoToPath);
	}

	public static IReadOnlyList<ClassicGoToPathCellMarker> BuildPreview(
		GameData gameData,
		int playerID,
		int selectedUnitID,
		GPoint destination,
		IReadOnlyList<GPoint> path)
	{
		ArgumentNullException.ThrowIfNull(gameData);
		ArgumentNullException.ThrowIfNull(path);

		if (!ClassicAiRuntimeProfiles.UsesSmartEnhancements(
				gameData.AiProfile) ||
			!gameData.GameSettingFlags.ShowGoToPaths ||
			playerID != gameData.HumanPlayerID ||
			playerID < 0 ||
			playerID >= gameData.Players.Length ||
			selectedUnitID < 0 ||
			selectedUnitID >= gameData.Players[playerID].Units.Length)
		{
			return Array.Empty<ClassicGoToPathCellMarker>();
		}

		Unit unit = gameData.Players[playerID].Units[selectedUnitID];
		if (unit.UnitType == UnitTypeEnum.None ||
			unit.PlayerID != playerID ||
			destination == OpenCivOneGame.InvalidPosition ||
			path.Count == 0)
		{
			return Array.Empty<ClassicGoToPathCellMarker>();
		}

		return BuildVisibleMarkers(
			gameData,
			playerID,
			unit.Position,
			destination,
			path);
	}

	private static IReadOnlyList<ClassicGoToPathCellMarker>
		BuildVisibleMarkers(
			GameData gameData,
			int playerID,
			GPoint start,
			GPoint destination,
			IEnumerable<GPoint> path)
	{
		List<ClassicGoToPathCellMarker> markers = [];
		HashSet<GPoint> emittedPositions = [];
		foreach (GPoint waypoint in path)
		{
			if (waypoint == start ||
				!IsVisible(gameData, playerID, waypoint) ||
				!emittedPositions.Add(waypoint))
			{
				continue;
			}

			markers.Add(
				new ClassicGoToPathCellMarker(
					waypoint,
					waypoint == destination));
		}

		return markers;
	}

	private static bool IsVisible(
		GameData gameData,
		int playerID,
		GPoint point)
	{
		if (point.Y < 0 || point.Y >= MapHeight)
		{
			return false;
		}

		int x = NormalizeX(point.X);
		return (gameData.MapVisibility[x, point.Y] &
				(1 << playerID)) != 0;
	}

	private static int NormalizeX(int x)
	{
		int normalized = x % MapManagement.Size.Width;
		return normalized < 0
			? normalized + MapManagement.Size.Width
			: normalized;
	}
}
