using OpenCivOne.Graphics;
using OpenCivOne.Platform;

namespace OpenCivOne
{
	public enum ClassicImproveNearestCityDecision
	{
		Work,
		Ineligible,
		NoKnownNeed
	}

	public readonly record struct ClassicImproveNearestCityPlan(
		ClassicImproveNearestCityDecision Decision,
		int CityID,
		GPoint Target,
		ClassicUnitAutomationWorkKind? WorkKind,
		int TargetPopulation)
	{
		public static ClassicImproveNearestCityPlan Ineligible =>
			new(
				ClassicImproveNearestCityDecision.Ineligible,
				-1,
				new GPoint(-1),
				null,
				0);

		public static ClassicImproveNearestCityPlan NoKnownNeed =>
			new(
				ClassicImproveNearestCityDecision.NoKnownNeed,
				-1,
				new GPoint(-1),
				null,
				0);
	}

	/// <summary>
	/// Selects one deterministic modernization job in the nearest owned city
	/// that has an unfinished, known and legal job. Planning is read-only and
	/// never consumes random numbers.
	/// </summary>
	public static class ClassicImproveNearestCityPlanner
	{
		private const byte InactiveCityStatus = 0xff;

		private static readonly GPoint[] CardinalDirections =
		[
			new GPoint(0, -1),
			new GPoint(1, 0),
			new GPoint(0, 1),
			new GPoint(-1, 0)
		];

		private static readonly GPoint[] LandMoveDirections =
		[
			new GPoint(0, -1),
			new GPoint(1, -1),
			new GPoint(1, 0),
			new GPoint(1, 1),
			new GPoint(0, 1),
			new GPoint(-1, 1),
			new GPoint(-1, 0),
			new GPoint(-1, -1)
		];

		public static ClassicImproveNearestCityPlan Plan(
			GameData gameData,
			MapManagement mapManagement,
			int playerID,
			Unit settler,
			int? requestedTargetPopulation = null,
			IReadOnlySet<GPoint>? reservedTargets = null)
		{
			ArgumentNullException.ThrowIfNull(gameData);
			ArgumentNullException.ThrowIfNull(mapManagement);
			ArgumentNullException.ThrowIfNull(settler);
			if (requestedTargetPopulation is < 1 or > 20)
			{
				throw new ArgumentOutOfRangeException(
					nameof(requestedTargetPopulation),
					requestedTargetPopulation,
					"City improvement target must be between one and twenty.");
			}

			if (!IsEligible(gameData, playerID, settler))
			{
				return ClassicImproveNearestCityPlan.Ineligible;
			}

			int width = gameData.MapVisibility.GetLength(0);
			int height = gameData.MapVisibility.GetLength(1);
			bool[,] reachableCells = BuildReachableKnownLandCells(
				gameData,
				mapManagement,
				playerID,
				settler,
				width,
				height);
			CityPlanCandidate? best = null;

			foreach (City city in gameData.Cities)
			{
				if (!IsEligibleCity(city, playerID, width, height) ||
					!TryPlanCity(
						gameData,
						mapManagement,
						playerID,
						settler,
						city,
						width,
						height,
						reachableCells,
						requestedTargetPopulation,
						reservedTargets,
						out int targetPopulation,
						out WorkCandidate work))
				{
					continue;
				}

				CityPlanCandidate candidate = new(
					GetClassicDistance(
						settler.Position,
						city.Position,
						width),
					city.ID,
					targetPopulation,
					work);

				if (best is null ||
					candidate.CompareTo(best.Value) < 0)
				{
					best = candidate;
				}
			}

			if (best is null)
			{
				return ClassicImproveNearestCityPlan.NoKnownNeed;
			}

			return new ClassicImproveNearestCityPlan(
				ClassicImproveNearestCityDecision.Work,
				best.Value.CityID,
				best.Value.Work.Target,
				best.Value.Work.Kind,
				best.Value.TargetPopulation);
		}

		private static bool IsEligible(
			GameData gameData,
			int playerID,
			Unit settler)
		{
			if (playerID <= 0 ||
				playerID >= gameData.Players.Length ||
				playerID != gameData.HumanPlayerID ||
				settler.PlayerID != playerID ||
				settler.UnitType != UnitTypeEnum.Settler)
			{
				return false;
			}

			int width = gameData.MapVisibility.GetLength(0);
			int height = gameData.MapVisibility.GetLength(1);
			return settler.Position.X >= 0 &&
				settler.Position.X < width &&
				settler.Position.Y >= 0 &&
				settler.Position.Y < height;
		}

		private static bool IsEligibleCity(
			City city,
			int playerID,
			int width,
			int height) =>
			city.StatusFlag != InactiveCityStatus &&
			city.ActualSize > 0 &&
			city.PlayerID == playerID &&
			city.ID >= 0 &&
			city.Position.X >= 0 &&
			city.Position.X < width &&
			city.Position.Y >= 0 &&
			city.Position.Y < height;

		private static bool TryPlanCity(
			GameData gameData,
			MapManagement mapManagement,
			int playerID,
			Unit settler,
			City city,
			int width,
			int height,
			bool[,] reachableCells,
			int? requestedTargetPopulation,
			IReadOnlySet<GPoint>? reservedTargets,
			out int targetPopulation,
			out WorkCandidate best)
		{
			WorkCandidate? selected = null;
			ushort visibilityMask = (ushort)(1 << playerID);
			List<CityTileCandidate> knownTiles = [];
			targetPopulation = requestedTargetPopulation ??
				GetAdaptiveTargetPopulation(city);

			// CityOffsets contains Civ1's twenty workable cells and deliberately
			// omits the four unreachable 5x5 corners. Its final centre entry is
			// skipped explicitly so array ordering cannot make it a work target.
			for (int offsetIndex = 0;
				offsetIndex < gameData.CityOffsets.Length;
				offsetIndex++)
			{
				GPoint offset = gameData.CityOffsets[offsetIndex];
				if (offset.X == 0 && offset.Y == 0)
				{
					continue;
				}

				int y = city.Position.Y + offset.Y;
				if (y < 0 || y >= height)
				{
					continue;
				}

				int x = AdjustX(city.Position.X + offset.X, width);
				if ((gameData.MapVisibility[x, y] &
					visibilityMask) == 0)
				{
					continue;
				}

				// A useful job is not a valid assignment unless the Settler
				// can reach it through the human player's known land. Without
				// this filter, the nearest isolated city was selected forever
				// and the original Go To code immediately abandoned the order.
				if (!reachableCells[x, y])
				{
					continue;
				}

				// Every map read follows the visibility check. The human
				// last-known improvement layer is used instead of the
				// authoritative layer, so hidden changes cannot leak in.
				TerrainTypeEnum terrain =
					mapManagement.GetTerrainType(x, y);
				TerrainImprovementFlagsEnum improvements =
					mapManagement.F0_2aea_15c1_GetTerrainImprovements(
						x,
						y);

				if (terrain == TerrainTypeEnum.Water ||
					improvements.HasFlag(
						TerrainImprovementFlagsEnum.City))
				{
					continue;
				}

				GPoint target = new(x, y);
				if (reservedTargets?.Contains(target) == true)
				{
					continue;
				}

				bool isWorked =
					(city.WorkerFlags &
						(1u << offsetIndex)) != 0;
				CityTileCandidate tile = new(
					offsetIndex,
					target,
					terrain,
					improvements,
					isWorked,
					GetKnownYieldScore(
						gameData,
						mapManagement,
						target,
						terrain,
						improvements));
				knownTiles.Add(tile);

				if (!improvements.HasFlag(
					TerrainImprovementFlagsEnum.Pollution))
				{
					continue;
				}

				WorkCandidate candidate = CreateWorkCandidate(
					settler,
					width,
					tile,
					ClassicUnitAutomationWorkKind.Pollution,
					priority: 0);
				if (selected is null ||
					candidate.CompareTo(selected.Value) < 0)
				{
					selected = candidate;
				}
			}

			// Pollution is an immediate hazard and is cleaned even when the
			// affected field lies outside the current population horizon.
			if (selected is not null)
			{
				best = selected.Value;
				return true;
			}

			HashSet<int> selectedOffsets = knownTiles
				.Where(static tile => tile.IsWorked)
				.Select(static tile => tile.OffsetIndex)
				.ToHashSet();
			foreach (CityTileCandidate tile in knownTiles
				.Where(tile =>
					!selectedOffsets.Contains(tile.OffsetIndex))
				.OrderByDescending(static tile => tile.YieldScore)
				.ThenBy(static tile => tile.OffsetIndex))
			{
				if (selectedOffsets.Count >= targetPopulation)
				{
					break;
				}

				selectedOffsets.Add(tile.OffsetIndex);
			}

			foreach (CityTileCandidate tile in knownTiles)
			{
				if (!selectedOffsets.Contains(tile.OffsetIndex))
				{
					continue;
				}

				WorkChoice? work =
					GetWorkChoice(
						gameData,
						mapManagement,
						playerID,
						tile.Target,
						tile.Terrain,
						tile.Improvements,
						visibilityMask,
						width,
						height);
				if (work is null)
				{
					continue;
				}

				WorkCandidate candidate = CreateWorkCandidate(
					settler,
					width,
					tile,
					work.Value.Kind,
					work.Value.Priority);

				if (selected is null ||
					candidate.CompareTo(selected.Value) < 0)
				{
					selected = candidate;
				}
			}

			best = selected.GetValueOrDefault();
			return selected is not null;
		}

		private static bool[,] BuildReachableKnownLandCells(
			GameData gameData,
			MapManagement mapManagement,
			int playerID,
			Unit settler,
			int width,
			int height)
		{
			ushort visibilityMask = (ushort)(1 << playerID);
			bool[,] ownCityCells = new bool[width, height];
			foreach (City city in gameData.Cities)
			{
				if (city.StatusFlag != InactiveCityStatus &&
					city.ActualSize > 0 &&
					city.PlayerID == playerID &&
					city.Position.X >= 0 &&
					city.Position.X < width &&
					city.Position.Y >= 0 &&
					city.Position.Y < height)
				{
					ownCityCells[
						city.Position.X,
						city.Position.Y] = true;
				}
			}

			bool[,] blockedCells = new bool[width, height];
			for (int otherPlayerID = 0;
				otherPlayerID < gameData.Players.Length;
				otherPlayerID++)
			{
				if (otherPlayerID == playerID)
				{
					continue;
				}

				foreach (Unit unit in
					gameData.Players[otherPlayerID].Units)
				{
					if (unit.UnitType == UnitTypeEnum.None ||
						(unit.VisibleByPlayer & visibilityMask) == 0 ||
						unit.Position.X < 0 ||
						unit.Position.X >= width ||
						unit.Position.Y < 0 ||
						unit.Position.Y >= height ||
						(gameData.MapVisibility[
							unit.Position.X,
							unit.Position.Y] &
							visibilityMask) == 0)
					{
						continue;
					}

					blockedCells[
						unit.Position.X,
						unit.Position.Y] = true;
				}
			}

			bool[,] passable = new bool[width, height];
			for (int y = 0; y < height; y++)
			{
				for (int x = 0; x < width; x++)
				{
					if ((gameData.MapVisibility[x, y] &
						visibilityMask) == 0)
					{
						// Unknown cells are possible transit cells. Treating
						// them as blocked would reject legitimate assignments
						// merely because the shortest connecting strip has not
						// been explored; reading their real terrain would leak
						// private map information.
						passable[x, y] = true;
						continue;
					}

					if (blockedCells[x, y])
					{
						continue;
					}

					TerrainTypeEnum terrain =
						mapManagement.GetTerrainType(x, y);
					if (terrain is
						TerrainTypeEnum.Water or
						TerrainTypeEnum.Invalid)
					{
						continue;
					}

					TerrainImprovementFlagsEnum improvements =
						mapManagement
							.F0_2aea_15c1_GetTerrainImprovements(
								x,
								y);
					bool knownForeignCity =
						improvements.HasFlag(
							TerrainImprovementFlagsEnum.City) &&
						!ownCityCells[x, y];
					passable[x, y] = !knownForeignCity;
				}
			}

			bool[,] reachable = new bool[width, height];
			if (!passable[
				settler.Position.X,
				settler.Position.Y])
			{
				return reachable;
			}

			Queue<GPoint> open = new();
			reachable[
				settler.Position.X,
				settler.Position.Y] = true;
			open.Enqueue(settler.Position);
			while (open.TryDequeue(out GPoint position))
			{
				foreach (GPoint direction in LandMoveDirections)
				{
					int nextY = position.Y + direction.Y;
					if (nextY < 0 || nextY >= height)
					{
						continue;
					}

					int nextX = AdjustX(
						position.X + direction.X,
						width);
					if (reachable[nextX, nextY] ||
						!passable[nextX, nextY])
					{
						continue;
					}

					reachable[nextX, nextY] = true;
					open.Enqueue(new GPoint(nextX, nextY));
				}
			}

			return reachable;
		}

		private static WorkCandidate CreateWorkCandidate(
			Unit settler,
			int width,
			CityTileCandidate tile,
			ClassicUnitAutomationWorkKind kind,
			int priority) =>
			new(
				priority,
				GetClassicDistance(
					settler.Position,
					tile.Target,
					width),
				tile.Target.Y,
				tile.Target.X,
				kind,
				tile.Target);

		private static WorkChoice? GetWorkChoice(
			GameData gameData,
			MapManagement mapManagement,
			int playerID,
			GPoint target,
			TerrainTypeEnum terrain,
			TerrainImprovementFlagsEnum improvements,
			ushort visibilityMask,
			int width,
			int height)
		{
			bool hasRoad =
				improvements.HasFlag(
					TerrainImprovementFlagsEnum.Road) ||
				improvements.HasFlag(
					TerrainImprovementFlagsEnum.RailRoad);
			bool hasRailRoad =
				improvements.HasFlag(
					TerrainImprovementFlagsEnum.RailRoad);
			bool canBuildRoad =
				terrain != TerrainTypeEnum.River ||
				HasTechnology(
					gameData,
					playerID,
					TechnologyAdvanceEnum.BridgeBuilding);
			if (!hasRoad &&
				canBuildRoad)
			{
				return new WorkChoice(
					ClassicUnitAutomationWorkKind.Road,
					Priority: 1);
			}

			if (hasRoad &&
				!hasRailRoad &&
				HasTechnology(
					gameData,
					playerID,
					TechnologyAdvanceEnum.Railroad))
			{
				// Civ1 deliberately uses the same Settler command for roads
				// and railroads. With Railroad researched, issuing 'r' on an
				// existing road upgrades it instead of rebuilding a road.
				return new WorkChoice(
					ClassicUnitAutomationWorkKind.Road,
					Priority: 2);
			}

			// Deliberate first-slice rule: automation only adds direct yield
			// improvements. Positive Civ1 effects transform the terrain and are
			// left to an explicit player decision. A cell already irrigated or
			// mined is also left unchanged, preventing automated oscillation.
			if (improvements.HasFlag(
					TerrainImprovementFlagsEnum.Irrigation) ||
				improvements.HasFlag(
					TerrainImprovementFlagsEnum.Mines))
			{
				return null;
			}

			TerrainModification modification =
				gameData.TerrainModifications[(int)terrain];
			bool canIrrigate =
				modification.IrrigationEffect <= -2 &&
				HasKnownWaterSource(
					gameData,
					mapManagement,
					target,
					terrain,
					visibilityMask,
					width,
					height);
			bool canMine = modification.MiningEffect <= -2;

			if (!canIrrigate)
			{
				return canMine
					? new WorkChoice(
						ClassicUnitAutomationWorkKind.Mine,
						Priority: 3)
					: null;
			}

			if (!canMine)
			{
				return new WorkChoice(
					ClassicUnitAutomationWorkKind.Irrigation,
					Priority: 3);
			}

			int irrigationGain = -1 - modification.IrrigationEffect;
			int miningGain = -1 - modification.MiningEffect;
			return miningGain > irrigationGain
				? new WorkChoice(
					ClassicUnitAutomationWorkKind.Mine,
					Priority: 3)
				: new WorkChoice(
					ClassicUnitAutomationWorkKind.Irrigation,
					Priority: 3);
		}

		private static bool HasKnownWaterSource(
			GameData gameData,
			MapManagement mapManagement,
			GPoint target,
			TerrainTypeEnum terrain,
			ushort visibilityMask,
			int width,
			int height)
		{
			if (terrain == TerrainTypeEnum.River)
			{
				return true;
			}

			foreach (GPoint direction in CardinalDirections)
			{
				int y = target.Y + direction.Y;
				if (y < 0 || y >= height)
				{
					continue;
				}

				int x = AdjustX(target.X + direction.X, width);
				if ((gameData.MapVisibility[x, y] &
					visibilityMask) == 0)
				{
					continue;
				}

				TerrainTypeEnum neighbourTerrain =
					mapManagement.GetTerrainType(x, y);
				TerrainImprovementFlagsEnum neighbourImprovements =
					mapManagement.F0_2aea_15c1_GetTerrainImprovements(
						x,
						y);
				if (neighbourImprovements.HasFlag(
					TerrainImprovementFlagsEnum.City))
				{
					continue;
				}

				if (neighbourTerrain is
						TerrainTypeEnum.Water or
						TerrainTypeEnum.River ||
					neighbourImprovements.HasFlag(
						TerrainImprovementFlagsEnum.Irrigation))
				{
					return true;
				}
			}

			return false;
		}

		private static bool HasTechnology(
			GameData gameData,
			int playerID,
			TechnologyAdvanceEnum technology)
		{
			if (technology == TechnologyAdvanceEnum.None)
			{
				return true;
			}

			int technologyID = (int)technology;
			return playerID > 0 &&
				technologyID >= 0 &&
				technologyID < 71 &&
				(gameData.Players[playerID]
					.DiscoveredTechnologyFlags[technologyID >> 4] &
					(1 << (technologyID & 0xf))) != 0;
		}

		private static int GetAdaptiveTargetPopulation(City city)
		{
			int size = Math.Clamp((int)city.ActualSize, 1, 20);
			int milestone = size switch
			{
				< 6 => 6,
				< 8 => 8,
				< 12 => 12,
				< 16 => 16,
				_ => 20
			};

			// Civ1 needs (size + 1) * 10 food for the human city to grow.
			// A nearly full food box prepares the next milestone early, while
			// young cities normally stop at the classic four-to-six range.
			int growthThreshold = (size + 1) * 10;
			bool growthIsNear =
				city.FoodCount >= (growthThreshold * 3) / 4;
			if (!growthIsNear)
			{
				return milestone;
			}

			return milestone switch
			{
				6 => 8,
				8 => 12,
				12 => 16,
				_ => 20
			};
		}

		private static int GetKnownYieldScore(
			GameData gameData,
			MapManagement mapManagement,
			GPoint target,
			TerrainTypeEnum terrain,
			TerrainImprovementFlagsEnum improvements)
		{
			int terrainIndex = (int)terrain;
			if (mapManagement.F0_2aea_1836_CellHasSpecialResource(
				target.X,
				target.Y))
			{
				terrainIndex += 12;
			}

			TerrainDefinition definition =
				gameData.Terrains[terrainIndex];
			int food = definition.Food;
			int production = definition.Production;
			int trade = definition.Trade;
			TerrainModification modification =
				gameData.TerrainModifications[(int)terrain];

			if (improvements.HasFlag(
				TerrainImprovementFlagsEnum.Irrigation))
			{
				food += -1 - modification.IrrigationEffect;
			}

			if (improvements.HasFlag(
				TerrainImprovementFlagsEnum.Mines))
			{
				production += -1 - modification.MiningEffect;
			}

			if (improvements.HasFlag(
					TerrainImprovementFlagsEnum.Road) &&
				terrain is
					TerrainTypeEnum.Desert or
					TerrainTypeEnum.Plains or
					TerrainTypeEnum.Grassland)
			{
				trade++;
			}

			if (improvements.HasFlag(
				TerrainImprovementFlagsEnum.RailRoad))
			{
				food += food / 2;
				production += production / 2;
				trade += trade / 2;
			}

			if (improvements.HasFlag(
				TerrainImprovementFlagsEnum.Pollution))
			{
				food = (food + 1) / 2;
				production = (production + 1) / 2;
				trade = (trade + 1) / 2;
			}

			// Food dominates growth-field selection, followed by production
			// and trade. The large factors make the ordering lexicographic.
			return (food * 10_000) +
				(production * 100) +
				trade;
		}

		private static int GetClassicDistance(
			GPoint from,
			GPoint to,
			int width)
		{
			int horizontal = Math.Abs(from.X - to.X);
			horizontal = Math.Min(horizontal, width - horizontal);
			int vertical = Math.Abs(from.Y - to.Y);

			return horizontal > vertical
				? horizontal + (vertical / 2)
				: vertical + (horizontal / 2);
		}

		private static int AdjustX(int x, int width)
		{
			int adjusted = x % width;
			return adjusted < 0 ? adjusted + width : adjusted;
		}

		private readonly record struct CityPlanCandidate(
			int Distance,
			int CityID,
			int TargetPopulation,
			WorkCandidate Work) :
			IComparable<CityPlanCandidate>
		{
			public int CompareTo(CityPlanCandidate other)
			{
				int comparison = Distance.CompareTo(other.Distance);
				return comparison != 0
					? comparison
					: CityID.CompareTo(other.CityID);
			}
		}

		private readonly record struct CityTileCandidate(
			int OffsetIndex,
			GPoint Target,
			TerrainTypeEnum Terrain,
			TerrainImprovementFlagsEnum Improvements,
			bool IsWorked,
			int YieldScore);

		private readonly record struct WorkChoice(
			ClassicUnitAutomationWorkKind Kind,
			int Priority);

		private readonly record struct WorkCandidate(
			int Priority,
			int Distance,
			int Y,
			int X,
			ClassicUnitAutomationWorkKind Kind,
			GPoint Target) :
			IComparable<WorkCandidate>
		{
			public int CompareTo(WorkCandidate other)
			{
				int comparison = Priority.CompareTo(other.Priority);
				if (comparison != 0)
				{
					return comparison;
				}

				comparison = Distance.CompareTo(other.Distance);
				if (comparison != 0)
				{
					return comparison;
				}

				comparison = Y.CompareTo(other.Y);
				if (comparison != 0)
				{
					return comparison;
				}

				comparison = X.CompareTo(other.X);
				if (comparison != 0)
				{
					return comparison;
				}

				return Kind.CompareTo(other.Kind);
			}
		}
	}
}
