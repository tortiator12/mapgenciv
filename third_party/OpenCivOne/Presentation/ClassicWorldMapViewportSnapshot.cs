namespace OpenCivOne.Presentation;

[Flags]
public enum ClassicWorldMapKnownNeighborMask : byte
{
	None = 0,
	NorthWest = 1 << 0,
	North = 1 << 1,
	NorthEast = 1 << 2,
	East = 1 << 3,
	SouthEast = 1 << 4,
	South = 1 << 5,
	SouthWest = 1 << 6,
	West = 1 << 7,
}

public readonly record struct ClassicWorldMapCitySnapshot(
	int CityID,
	int PlayerID,
	string Name,
	int Size,
	bool IsInDisorder,
	bool HasWalls,
	bool HasDefenders);

public readonly record struct ClassicWorldMapUnitSnapshot(
	int UnitID,
	int PlayerID,
	UnitTypeEnum UnitType,
	UnitStatusEnum Status,
	int RemainingMoves,
	bool HasStack,
	bool IsActive,
	bool HasGoToDestination);

/// <summary>
/// Visibility-filtered terrain connections used only by alternative
/// presentation layers. Every mask uses the directions from
/// <see cref="ClassicWorldMapKnownNeighborMask"/>. Unknown neighbours never
/// contribute, so the remaster cannot infer terrain through fog of war.
/// </summary>
public readonly record struct ClassicWorldMapTerrainTopologySnapshot(
	ClassicWorldMapKnownNeighborMask LandNeighbors,
	ClassicWorldMapKnownNeighborMask MatchingTerrainNeighbors,
	ClassicWorldMapKnownNeighborMask WaterOrRiverNeighbors,
	ClassicWorldMapKnownNeighborMask RiverNeighbors);

public readonly record struct ClassicWorldMapCellSnapshot(
	int Column,
	int Row,
	int MapX,
	int MapY,
	bool IsKnown,
	TerrainTypeEnum TerrainType,
	TerrainImprovementFlagsEnum Improvements,
	bool HasSpecialResource,
	bool HasMinorTribeHut,
	ClassicWorldMapKnownNeighborMask KnownNeighbors,
	ClassicWorldMapCitySnapshot? City,
	ClassicWorldMapUnitSnapshot? Unit,
	ClassicWorldMapTerrainTopologySnapshot TerrainTopology = default);

/// <summary>
/// Immutable, human-visibility-filtered semantic capture of the original
/// 15-by-12 world-map viewport. It deliberately excludes the left rail,
/// minimap, left rail and stable interaction overlays. Transient dialogs and
/// animations remain unsupported and force the complete Original fallback.
/// </summary>
public sealed class ClassicWorldMapViewportSnapshot
{
	public const int ColumnCount = 15;
	public const int RowCount = 12;

	private readonly IReadOnlyList<ClassicWorldMapCellSnapshot> cells;

	internal ClassicWorldMapViewportSnapshot(
		long revision,
		int humanPlayerID,
		int activeUnitID,
		int viewOriginX,
		int viewOriginY,
		int turnCount,
		int year,
		bool animationsEnabled,
		ClassicWorldMapMinimapSnapshot minimap,
		ClassicWorldMapLeftRailSnapshot leftRail,
		ClassicWorldMapInteractionSnapshot interaction,
		IEnumerable<ClassicWorldMapCellSnapshot> cells,
		int worldWidth,
		int worldHeight,
		string worldTerrainFingerprint,
		ClassicRuntimePresentationKind presentationKind =
			ClassicRuntimePresentationKind.InteractiveWorldMap)
	{
		ArgumentOutOfRangeException.ThrowIfNegative(revision);
		ArgumentNullException.ThrowIfNull(minimap);
		ArgumentNullException.ThrowIfNull(leftRail);
		ArgumentNullException.ThrowIfNull(interaction);
		ArgumentNullException.ThrowIfNull(cells);
		ArgumentOutOfRangeException.ThrowIfNegativeOrZero(worldWidth);
		ArgumentOutOfRangeException.ThrowIfNegativeOrZero(worldHeight);
		ArgumentException.ThrowIfNullOrWhiteSpace(worldTerrainFingerprint);
		ClassicWorldMapCellSnapshot[] capturedCells = [.. cells];
		if (capturedCells.Length != ColumnCount * RowCount)
		{
			throw new ArgumentException(
				$"A world-map viewport needs exactly " +
					$"{ColumnCount * RowCount} cells.",
				nameof(cells));
		}

		Revision = revision;
		HumanPlayerID = humanPlayerID;
		ActiveUnitID = activeUnitID;
		ViewOriginX = viewOriginX;
		ViewOriginY = viewOriginY;
		TurnCount = turnCount;
		Year = year;
		AnimationsEnabled = animationsEnabled;
		Minimap = minimap;
		LeftRail = leftRail;
		Interaction = interaction;
		WorldWidth = worldWidth;
		WorldHeight = worldHeight;
		WorldTerrainFingerprint = worldTerrainFingerprint;
		PresentationKind = presentationKind;
		this.cells = Array.AsReadOnly(capturedCells);
	}

	public long Revision { get; }

	public int HumanPlayerID { get; }

	public int ActiveUnitID { get; }

	public int ViewOriginX { get; }

	public int ViewOriginY { get; }

	public int TurnCount { get; }

	public int Year { get; }

	public bool AnimationsEnabled { get; }

	public ClassicWorldMapMinimapSnapshot Minimap { get; }

	public ClassicWorldMapLeftRailSnapshot LeftRail { get; }

	public ClassicWorldMapInteractionSnapshot Interaction { get; }

	public int WorldWidth { get; }

	public int WorldHeight { get; }

	/// <summary>
	/// Opaque static-terrain identity. It is not save state and does not expose
	/// hidden cell contents to presentation adapters.
	/// </summary>
	public string WorldTerrainFingerprint { get; }

	public ClassicRuntimePresentationKind PresentationKind { get; }

	public IReadOnlyList<ClassicWorldMapCellSnapshot> Cells =>
		this.cells;

	public ClassicWorldMapCellSnapshot GetCell(int column, int row)
	{
		if (column < 0 || column >= ColumnCount)
		{
			throw new ArgumentOutOfRangeException(nameof(column));
		}

		if (row < 0 || row >= RowCount)
		{
			throw new ArgumentOutOfRangeException(nameof(row));
		}

		return this.cells[(row * ColumnCount) + column];
	}
}

internal static class ClassicWorldMapViewportCapture
{
	private const UnitStatusEnum PublicUnitStatusMask =
		UnitStatusEnum.Sentry |
		UnitStatusEnum.SettlerBuildRoadOrRail |
		UnitStatusEnum.Fortifying |
		UnitStatusEnum.Fortified |
		UnitStatusEnum.SettlerBuildIrrigation |
		UnitStatusEnum.SettlerBuildMineOrForest;

	private static readonly (
		int X,
		int Y,
		ClassicWorldMapKnownNeighborMask Mask)[] NeighborOffsets =
	[
		(-1, -1, ClassicWorldMapKnownNeighborMask.NorthWest),
		(0, -1, ClassicWorldMapKnownNeighborMask.North),
		(1, -1, ClassicWorldMapKnownNeighborMask.NorthEast),
		(1, 0, ClassicWorldMapKnownNeighborMask.East),
		(1, 1, ClassicWorldMapKnownNeighborMask.SouthEast),
		(0, 1, ClassicWorldMapKnownNeighborMask.South),
		(-1, 1, ClassicWorldMapKnownNeighborMask.SouthWest),
		(-1, 0, ClassicWorldMapKnownNeighborMask.West),
	];

	public static ClassicWorldMapViewportSnapshot? TryCapture(
		OpenCivOneGame game,
		ClassicRuntimePresentationSnapshot presentation,
		ClassicWorldMapCursorSnapshot cursor = default)
	{
		ArgumentNullException.ThrowIfNull(game);
		GameData gameData = game.GameData;
		if (presentation.Kind is not
				(ClassicRuntimePresentationKind.InteractiveWorldMap or
					ClassicRuntimePresentationKind.WorldMapModalOverlay) ||
			presentation.PlayerID != gameData.HumanPlayerID ||
			presentation.PlayerID < 0 ||
			presentation.PlayerID >= gameData.Players.Length)
		{
			return null;
		}

		int humanPlayerID = presentation.PlayerID;
		int visibilityMask = 1 << humanPlayerID;
		List<ClassicWorldMapCellSnapshot> cells =
			new(ClassicWorldMapViewportSnapshot.ColumnCount *
				ClassicWorldMapViewportSnapshot.RowCount);

		for (int row = 0;
			row < ClassicWorldMapViewportSnapshot.RowCount;
			row++)
		{
			int mapY = game.Var_d75e_MapViewY + row;
			for (int column = 0;
				column < ClassicWorldMapViewportSnapshot.ColumnCount;
				column++)
			{
				int mapX = game.MapManagement.AdjustXPosition(
					game.Var_d4cc_MapViewX + column);
				cells.Add(CaptureCell(
					game,
					presentation,
					column,
					row,
					mapX,
					mapY,
					visibilityMask));
			}
		}

		int viewOriginX =
			game.MapManagement.AdjustXPosition(game.Var_d4cc_MapViewX);
		int viewOriginY = game.Var_d75e_MapViewY;
		int worldWidth = gameData.MapVisibility.GetLength(0);
		int worldHeight = gameData.MapVisibility.GetLength(1);
		string worldTerrainFingerprint =
			ClassicWorldTerrainFingerprint.Compute(
				worldWidth,
				worldHeight,
				game.MapManagement.GetTerrainType);
		return new ClassicWorldMapViewportSnapshot(
			presentation.Revision,
			humanPlayerID,
			presentation.ActiveUnitID,
			viewOriginX,
			viewOriginY,
			gameData.TurnCount,
			gameData.Year,
			gameData.GameSettingFlags.Animations,
			ClassicWorldMapMinimapCapture.Capture(game),
			ClassicWorldMapLeftRailCapture.Capture(
				game,
				presentation),
			ClassicWorldMapInteractionCapture.Capture(
				game,
				presentation,
				cursor,
				viewOriginX,
				viewOriginY),
			cells,
			worldWidth,
			worldHeight,
			worldTerrainFingerprint,
			presentation.Kind);
	}

	private static ClassicWorldMapCellSnapshot CaptureCell(
		OpenCivOneGame game,
		ClassicRuntimePresentationSnapshot presentation,
		int column,
		int row,
		int mapX,
		int mapY,
		int visibilityMask)
	{
		GameData gameData = game.GameData;
		bool isKnown =
			mapY >= 0 &&
			mapY < gameData.MapVisibility.GetLength(1) &&
			(game.Var_d806_DebugFlag ||
				(gameData.MapVisibility[mapX, mapY] &
					visibilityMask) != 0);
		if (!isKnown)
		{
			return new ClassicWorldMapCellSnapshot(
				column,
				row,
				mapX,
				mapY,
				IsKnown: false,
				TerrainTypeEnum.Invalid,
				TerrainImprovementFlagsEnum.None,
				HasSpecialResource: false,
				HasMinorTribeHut: false,
				ClassicWorldMapKnownNeighborMask.None,
				City: null,
				Unit: null);
		}

		TerrainTypeEnum terrainType =
			game.MapManagement.GetTerrainType(mapX, mapY);
		TerrainImprovementFlagsEnum improvements =
			game.MapManagement
				.F0_2aea_15c1_GetTerrainImprovements(mapX, mapY);
		ClassicWorldMapUnitSnapshot? unit =
			CaptureVisibleUnit(
				game,
				presentation,
				mapX,
				mapY,
				terrainType,
				visibilityMask);
		bool hasDefenders = TryFindActiveUnit(
			game,
			mapX,
			mapY,
			out _,
			out _,
			out _);
		ClassicWorldMapCitySnapshot? city =
			CaptureVisibleCity(
				game,
				mapX,
				mapY,
				improvements,
				hasDefenders);
		if (city.HasValue &&
			(!unit.HasValue || !unit.Value.IsActive))
		{
			unit = null;
		}

		return new ClassicWorldMapCellSnapshot(
			column,
			row,
			mapX,
			mapY,
			IsKnown: true,
			terrainType,
			improvements,
			game.MapManagement
				.F0_2aea_1836_CellHasSpecialResource(mapX, mapY),
			game.MapManagement.F0_2aea_1894_CellHasMinorTribeHut(
				mapX,
				mapY,
				terrainType),
			CaptureKnownNeighbors(
				game,
				mapX,
				mapY,
				visibilityMask),
			city,
			unit,
			CaptureTerrainTopology(
				game,
				mapX,
				mapY,
				terrainType,
				visibilityMask));
	}

	private static ClassicWorldMapTerrainTopologySnapshot
		CaptureTerrainTopology(
			OpenCivOneGame game,
			int mapX,
			int mapY,
			TerrainTypeEnum terrainType,
			int visibilityMask)
	{
		ClassicWorldMapKnownNeighborMask land =
			ClassicWorldMapKnownNeighborMask.None;
		ClassicWorldMapKnownNeighborMask matching =
			ClassicWorldMapKnownNeighborMask.None;
		ClassicWorldMapKnownNeighborMask waterOrRiver =
			ClassicWorldMapKnownNeighborMask.None;
		ClassicWorldMapKnownNeighborMask river =
			ClassicWorldMapKnownNeighborMask.None;
		GameData gameData = game.GameData;
		foreach ((int offsetX, int offsetY,
			ClassicWorldMapKnownNeighborMask mask) in NeighborOffsets)
		{
			int neighborY = mapY + offsetY;
			if (neighborY < 0 ||
				neighborY >= gameData.MapVisibility.GetLength(1))
			{
				continue;
			}

			int neighborX = game.MapManagement.AdjustXPosition(
				mapX + offsetX);
			if (!game.Var_d806_DebugFlag &&
				(gameData.MapVisibility[neighborX, neighborY] &
					visibilityMask) == 0)
			{
				continue;
			}

			TerrainTypeEnum neighborTerrain =
				game.MapManagement.GetTerrainType(neighborX, neighborY);
			if (!IsWaterTerrain(neighborTerrain))
			{
				land |= mask;
			}
			if (GetTerrainFamily(neighborTerrain) ==
				GetTerrainFamily(terrainType))
			{
				matching |= mask;
			}
			if (IsWaterTerrain(neighborTerrain) ||
				IsRiverTerrain(neighborTerrain))
			{
				waterOrRiver |= mask;
			}
			if (IsRiverTerrain(neighborTerrain))
			{
				river |= mask;
			}
		}

		return new ClassicWorldMapTerrainTopologySnapshot(
			land,
			matching,
			waterOrRiver,
			river);
	}

	private static int GetTerrainFamily(TerrainTypeEnum terrain) =>
		terrain switch
		{
			TerrainTypeEnum.Desert or
			TerrainTypeEnum.ResourceOasis => 0,
			TerrainTypeEnum.Plains or
			TerrainTypeEnum.ResourceHorses => 1,
			TerrainTypeEnum.Grassland or
			TerrainTypeEnum.ResourceGrassland => 2,
			TerrainTypeEnum.Forest or
			TerrainTypeEnum.ResourceGame => 3,
			TerrainTypeEnum.Hills or
			TerrainTypeEnum.ResourceCoal => 4,
			TerrainTypeEnum.Mountains or
			TerrainTypeEnum.ResourceGold => 5,
			TerrainTypeEnum.Tundra or
			TerrainTypeEnum.ResourceGame2 => 6,
			TerrainTypeEnum.Arctic or
			TerrainTypeEnum.ResourceSeals => 7,
			TerrainTypeEnum.Swamp or
			TerrainTypeEnum.ResourceOil => 8,
			TerrainTypeEnum.Jungle or
			TerrainTypeEnum.ResourceGems => 9,
			TerrainTypeEnum.Water or
			TerrainTypeEnum.ResourceFish => 10,
			TerrainTypeEnum.River or
			TerrainTypeEnum.ResourceRiver => 11,
			_ => -1,
		};

	private static bool IsWaterTerrain(TerrainTypeEnum terrain) =>
		terrain is TerrainTypeEnum.Water or
			TerrainTypeEnum.ResourceFish;

	private static bool IsRiverTerrain(TerrainTypeEnum terrain) =>
		terrain is TerrainTypeEnum.River or
			TerrainTypeEnum.ResourceRiver;

	private static ClassicWorldMapKnownNeighborMask CaptureKnownNeighbors(
		OpenCivOneGame game,
		int mapX,
		int mapY,
		int visibilityMask)
	{
		ClassicWorldMapKnownNeighborMask known =
			ClassicWorldMapKnownNeighborMask.None;
		GameData gameData = game.GameData;
		foreach ((int offsetX, int offsetY,
			ClassicWorldMapKnownNeighborMask mask) in NeighborOffsets)
		{
			int neighborY = mapY + offsetY;
			if (neighborY < 0 ||
				neighborY >= gameData.MapVisibility.GetLength(1))
			{
				continue;
			}

			int neighborX = game.MapManagement.AdjustXPosition(
				mapX + offsetX);
			if (game.Var_d806_DebugFlag ||
				(gameData.MapVisibility[neighborX, neighborY] &
					visibilityMask) != 0)
			{
				known |= mask;
			}
		}

		return known;
	}

	private static ClassicWorldMapCitySnapshot? CaptureVisibleCity(
		OpenCivOneGame game,
		int mapX,
		int mapY,
		TerrainImprovementFlagsEnum improvements,
		bool hasDefenders)
	{
		if (!improvements.HasFlag(TerrainImprovementFlagsEnum.City))
		{
			return null;
		}

		GameData gameData = game.GameData;
		for (int cityID = 0; cityID < gameData.Cities.Length; cityID++)
		{
			City city = gameData.Cities[cityID];
			if (city.StatusFlag == byte.MaxValue ||
				city.Position.X != mapX ||
				city.Position.Y != mapY ||
				city.PlayerID < 0 ||
				city.PlayerID >= gameData.Players.Length)
			{
				continue;
			}

			bool isHumanCity =
				city.PlayerID == gameData.HumanPlayerID;
			if (!isHumanCity && city.VisibleSize <= 0)
			{
				return null;
			}

			string name =
				city.NameID < gameData.CityNames.Length
					? gameData.CityNames[city.NameID]
						.TrimEnd('\0', ' ')
					: string.Empty;
			return new ClassicWorldMapCitySnapshot(
				isHumanCity ? cityID : -1,
				city.PlayerID,
				name,
				isHumanCity ? city.ActualSize : city.VisibleSize,
				(city.StatusFlag & 0x1) != 0,
				city.HasImprovement(ImprovementEnum.CityWalls),
				hasDefenders || city.Unknown[0] != -1);
		}

		return null;
	}

	private static ClassicWorldMapUnitSnapshot? CaptureVisibleUnit(
		OpenCivOneGame game,
		ClassicRuntimePresentationSnapshot presentation,
		int mapX,
		int mapY,
		TerrainTypeEnum terrainType,
		int visibilityMask)
	{
		bool foundPresentedUnit = TryFindPresentedActiveUnit(
			game,
			presentation,
			mapX,
			mapY,
			out int playerID,
			out int unitID,
			out Unit unit);
		if (!foundPresentedUnit &&
			!TryFindActiveUnit(
				game,
				mapX,
				mapY,
				out playerID,
				out unitID,
				out unit))
		{
			return null;
		}

		if (!foundPresentedUnit)
		{
			if (!game.Var_d806_DebugFlag &&
				playerID != game.GameData.HumanPlayerID &&
				(unit.VisibleByPlayer & visibilityMask) == 0)
			{
				return null;
			}

			unitID = SelectClassicDisplayedUnit(
				game,
				playerID,
				unitID,
				terrainType);
			if (unitID < 0)
			{
				return null;
			}

			unit = game.GameData.Players[playerID].Units[unitID];
		}

		bool hidesSentryPassenger =
			unit.Status.HasFlag(UnitStatusEnum.Sentry) &&
			terrainType == TerrainTypeEnum.Water &&
			game.GameData.Units[(int)unit.UnitType].MovementType !=
				UnitMovementTypeEnum.Water;
		if (hidesSentryPassenger)
		{
			return null;
		}

		bool isHumanUnit =
			playerID == game.GameData.HumanPlayerID;
		UnitStatusEnum visibleStatusMask =
			PublicUnitStatusMask |
			(isHumanUnit
				? UnitStatusEnum.Veteran
				: UnitStatusEnum.None);
		return new ClassicWorldMapUnitSnapshot(
			isHumanUnit ? unitID : -1,
			playerID,
			unit.UnitType,
			unit.Status & visibleStatusMask,
			isHumanUnit ? unit.RemainingMoves : -1,
			unit.NextUnitID != -1,
			playerID == presentation.PlayerID &&
				unitID == presentation.ActiveUnitID,
			isHumanUnit &&
				unit.GoToDestination.X != -1 &&
				unit.GoToDestination.Y != -1);
	}

	private static int SelectClassicDisplayedUnit(
		OpenCivOneGame game,
		int playerID,
		int headUnitID,
		TerrainTypeEnum terrainType)
	{
		Player player = game.GameData.Players[playerID];
		Unit head = player.Units[headUnitID];
		UnitMovementTypeEnum headMovement =
			game.GameData.Units[(int)head.UnitType].MovementType;
		if (head.NextUnitID != -1 &&
			terrainType == TerrainTypeEnum.Water &&
			headMovement != UnitMovementTypeEnum.Water)
		{
			int currentUnitID = headUnitID;
			do
			{
				currentUnitID =
					player.Units[currentUnitID].NextUnitID;
				if (currentUnitID == -1)
				{
					return -1;
				}

				if (currentUnitID < 0 ||
					currentUnitID >= player.Units.Length)
				{
					return -1;
				}

				Unit candidate = player.Units[currentUnitID];
				if (candidate.UnitType == UnitTypeEnum.None)
				{
					return -1;
				}

				if (game.GameData.Units[(int)candidate.UnitType]
					.MovementType == UnitMovementTypeEnum.Water)
				{
					return currentUnitID;
				}
			}
			while (currentUnitID != headUnitID);

			return headUnitID;
		}

		if (head.NextUnitID == -1)
		{
			return headUnitID;
		}

		int bestUnitID = headUnitID;
		int bestDefenseStrength = -1;
		int currentID = headUnitID;
		for (int i = 0; i < 10 && currentID != -1; i++)
		{
			if (currentID < 0 || currentID >= player.Units.Length)
			{
				break;
			}

			Unit candidate = player.Units[currentID];
			if (candidate.UnitType == UnitTypeEnum.None)
			{
				break;
			}

			UnitDefinition definition =
				game.GameData.Units[(int)candidate.UnitType];
			TerrainTypeEnum candidateTerrain =
				game.MapManagement.GetTerrainType(
					candidate.Position.X,
					candidate.Position.Y);
			if (candidateTerrain != TerrainTypeEnum.Water ||
				definition.MovementType == UnitMovementTypeEnum.Water)
			{
				int defenseStrength =
					definition.MovementType == UnitMovementTypeEnum.Land
						? definition.DefenseStrength *
							(candidate.Status.HasFlag(
								UnitStatusEnum.Fortified)
								? 3
								: 2) *
							game.GameData.Terrains[(int)candidateTerrain]
								.DefenseBonus *
							8
						: definition.DefenseStrength * 16;
				if (candidate.Status.HasFlag(UnitStatusEnum.Veteran))
				{
					defenseStrength += defenseStrength / 2;
				}

				if (defenseStrength > bestDefenseStrength)
				{
					bestDefenseStrength = defenseStrength;
					bestUnitID = currentID;
				}
			}

			int nextID = candidate.NextUnitID;
			if (nextID == headUnitID)
			{
				break;
			}

			currentID = nextID;
		}

		return bestUnitID;
	}

	private static bool TryFindPresentedActiveUnit(
		OpenCivOneGame game,
		ClassicRuntimePresentationSnapshot presentation,
		int mapX,
		int mapY,
		out int playerID,
		out int unitID,
		out Unit unit)
	{
		playerID = presentation.PlayerID;
		unitID = presentation.ActiveUnitID;
		unit = null!;
		if (playerID < 0 ||
			playerID >= game.GameData.Players.Length)
		{
			return false;
		}

		Player player = game.GameData.Players[playerID];
		if (unitID < 0 || unitID >= player.Units.Length)
		{
			return false;
		}

		Unit candidate = player.Units[unitID];
		if (candidate.UnitType == UnitTypeEnum.None ||
			candidate.Position.X != mapX ||
			candidate.Position.Y != mapY)
		{
			return false;
		}

		unit = candidate;
		return true;
	}

	private static bool TryFindActiveUnit(
		OpenCivOneGame game,
		int mapX,
		int mapY,
		out int playerID,
		out int unitID,
		out Unit unit)
	{
		playerID =
			game.MapManagement
				.F0_2aea_14e0_GetCellActiveUnitPlayerID(mapX, mapY);
		unitID =
			game.MapManagement
				.F0_2aea_1458_GetCellActiveUnitID(mapX, mapY);
		unit = null!;
		if (playerID < 0 ||
			playerID >= game.GameData.Players.Length ||
			unitID < 0)
		{
			return false;
		}

		Player player = game.GameData.Players[playerID];
		if (unitID >= player.Units.Length)
		{
			return false;
		}

		unit = player.Units[unitID];
		return unit.UnitType != UnitTypeEnum.None &&
			unit.Position.X == mapX &&
			unit.Position.Y == mapY;
	}
}
