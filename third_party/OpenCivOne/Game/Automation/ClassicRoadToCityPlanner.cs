using OpenCivOne.Graphics;

namespace OpenCivOne
{
	public enum ClassicRoadToCityDecision
	{
		Move,
		BuildRoadOnCurrentCell,
		Complete,
		Ineligible
	}

	public readonly record struct ClassicRoadToCityPlan(
		ClassicRoadToCityDecision Decision,
		int Direction,
		GPoint NextPosition)
	{
		public static ClassicRoadToCityPlan BuildRoadOnCurrentCell =>
			new(
				ClassicRoadToCityDecision.BuildRoadOnCurrentCell,
				0,
				new GPoint(-1));

		public static ClassicRoadToCityPlan Complete =>
			new(
				ClassicRoadToCityDecision.Complete,
				0,
				new GPoint(-1));

		public static ClassicRoadToCityPlan Ineligible =>
			new(
				ClassicRoadToCityDecision.Ineligible,
				0,
				new GPoint(-1));
	}

	/// <summary>
	/// Plans one deterministic step for connecting a human Settler's
	/// current cell to a selected human city. The planner reads only the
	/// human player's known map layer and never mutates game state or RNG.
	/// </summary>
	public static class ClassicRoadToCityPlanner
	{
		private const int DirectionCount = 8;
		private const int Unreachable = int.MaxValue;

		private static readonly GPoint[] MoveDirections =
		[
			new GPoint(0, 0),
			new GPoint(0, -1),
			new GPoint(1, -1),
			new GPoint(1, 0),
			new GPoint(1, 1),
			new GPoint(0, 1),
			new GPoint(-1, 1),
			new GPoint(-1, 0),
			new GPoint(-1, -1)
		];

		public static ClassicRoadToCityPlan PlanNextAction(
			GameData gameData,
			MapManagement mapManagement,
			int playerID,
			Unit settler,
			int destinationCityID)
		{
			ArgumentNullException.ThrowIfNull(gameData);
			ArgumentNullException.ThrowIfNull(mapManagement);
			ArgumentNullException.ThrowIfNull(settler);

			if (!TryValidateRequest(
				gameData,
				playerID,
				settler,
				destinationCityID,
				out City destinationCity))
			{
				return ClassicRoadToCityPlan.Ineligible;
			}

			int width = gameData.MapVisibility.GetLength(0);
			int height = gameData.MapVisibility.GetLength(1);
			int startX = settler.Position.X;
			int startY = settler.Position.Y;
			int destinationX = destinationCity.Position.X;
			int destinationY = destinationCity.Position.Y;
			ushort visibilityMask = (ushort)(1 << playerID);

			if (!IsValidPosition(startX, startY, width, height) ||
				!IsValidPosition(
					destinationX,
					destinationY,
					width,
					height) ||
				(gameData.MapVisibility[startX, startY] &
					visibilityMask) == 0)
			{
				return ClassicRoadToCityPlan.Ineligible;
			}

			bool[,] ownCityCells = BuildOwnCityCells(
				gameData,
				playerID,
				width,
				height);
			bool[,] blockedCells =
				BuildKnownEnemyUnitCells(
					gameData,
					playerID,
					visibilityMask,
					width,
					height);
			bool[,] passable = new bool[width, height];
			bool[,] routeCells = new bool[width, height];
			int[,] buildWorkCosts = new int[width, height];
			int[,] movementCosts = new int[width, height];
			bool hasBridgeBuilding = HasTechnology(
				gameData,
				playerID,
				TechnologyAdvanceEnum.BridgeBuilding);
			bool hasRailroadTechnology = HasTechnology(
				gameData,
				playerID,
				TechnologyAdvanceEnum.Railroad);

			// Every map-data read is guarded by the player's visibility
			// layer. Hidden terrain and improvements cannot affect a plan.
			for (int y = 0; y < height; y++)
			{
				for (int x = 0; x < width; x++)
				{
					if ((gameData.MapVisibility[x, y] &
						visibilityMask) == 0)
					{
						continue;
					}

					TerrainTypeEnum terrain =
						mapManagement.GetTerrainType(x, y);
					TerrainImprovementFlagsEnum improvements =
						mapManagement
							.F0_2aea_15c1_GetTerrainImprovements(
								x,
								y);
					bool isKnownForeignCity =
						improvements.HasFlag(
							TerrainImprovementFlagsEnum.City) &&
						!ownCityCells[x, y];
					bool hasRailRoad = improvements.HasFlag(
						TerrainImprovementFlagsEnum.RailRoad);
					bool hasRoad = hasRailRoad ||
						improvements.HasFlag(
							TerrainImprovementFlagsEnum.Road);
					if (terrain == TerrainTypeEnum.Water ||
						terrain == TerrainTypeEnum.Invalid ||
						blockedCells[x, y] ||
						isKnownForeignCity)
					{
						continue;
					}

					passable[x, y] = true;
					bool riverDoesNotNeedRoad =
						terrain == TerrainTypeEnum.River &&
						!hasBridgeBuilding;
					routeCells[x, y] =
						ownCityCells[x, y] ||
						riverDoesNotNeedRoad ||
						(hasRailroadTechnology
							? hasRailRoad
							: hasRoad);
					buildWorkCosts[x, y] =
						routeCells[x, y]
							? 0
							: hasRailroadTechnology && !hasRoad
								? 2
								: 1;
					movementCosts[x, y] = hasRailRoad
						? 0
						: hasRoad
							? 1
							: Math.Max(
								1,
								gameData.Terrains[
									(int)terrain]
									.MovementCost * 3);
				}
			}

			// The selected own city is known even when no City bit was
			// copied into the historical map-improvement layer.
			if (!passable[startX, startY] ||
				!passable[destinationX, destinationY])
			{
				return ClassicRoadToCityPlan.Ineligible;
			}
			routeCells[destinationX, destinationY] = true;

			if (IsConnectedByExistingRoute(
				startX,
				startY,
				destinationX,
				destinationY,
				passable,
				routeCells))
			{
				return ClassicRoadToCityPlan.Complete;
			}

			ClassicRoadToCityPlan nextMove = FindNextMove(
				startX,
				startY,
				destinationX,
				destinationY,
				passable,
				buildWorkCosts,
				movementCosts);
			if (nextMove.Decision !=
				ClassicRoadToCityDecision.Move)
			{
				return nextMove;
			}

			if (buildWorkCosts[startX, startY] > 0)
			{
				return ClassicRoadToCityPlan
					.BuildRoadOnCurrentCell;
			}

			return nextMove;
		}

		private static bool TryValidateRequest(
			GameData gameData,
			int playerID,
			Unit settler,
			int destinationCityID,
			out City destinationCity)
		{
			destinationCity = null!;
			if (playerID <= 0 ||
				playerID >= gameData.Players.Length ||
				playerID != gameData.HumanPlayerID ||
				settler.PlayerID != playerID ||
				settler.UnitType != UnitTypeEnum.Settler ||
				destinationCityID < 0 ||
				destinationCityID >= gameData.Cities.Length)
			{
				return false;
			}

			destinationCity =
				gameData.Cities[destinationCityID];
			return destinationCity.StatusFlag != byte.MaxValue &&
				destinationCity.ActualSize > 0 &&
				destinationCity.PlayerID == playerID;
		}

		private static bool[,] BuildOwnCityCells(
			GameData gameData,
			int playerID,
			int width,
			int height)
		{
			bool[,] ownCityCells = new bool[width, height];
			foreach (City city in gameData.Cities)
			{
				if (city.StatusFlag == byte.MaxValue ||
					city.ActualSize <= 0 ||
					city.PlayerID != playerID ||
					!IsValidPosition(
						city.Position.X,
						city.Position.Y,
						width,
						height))
				{
					continue;
				}

				ownCityCells[
					city.Position.X,
					city.Position.Y] = true;
			}

			return ownCityCells;
		}

		private static bool[,] BuildKnownEnemyUnitCells(
			GameData gameData,
			int playerID,
			ushort visibilityMask,
			int width,
			int height)
		{
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
					// VisibleByPlayer is checked before all hidden unit
					// fields, so an unseen unit cannot affect routing.
					if ((unit.VisibleByPlayer &
						visibilityMask) == 0)
					{
						continue;
					}

					int x = unit.Position.X;
					int y = unit.Position.Y;
					if (unit.UnitType != UnitTypeEnum.None &&
						IsKnownPosition(
							gameData,
							visibilityMask,
							x,
							y,
							width,
							height))
					{
						blockedCells[x, y] = true;
					}
				}
			}

			return blockedCells;
		}

		private static bool IsConnectedByExistingRoute(
			int startX,
			int startY,
			int destinationX,
			int destinationY,
			bool[,] passable,
			bool[,] routeCells)
		{
			if (!routeCells[startX, startY])
			{
				return false;
			}

			int width = passable.GetLength(0);
			int height = passable.GetLength(1);
			bool[,] visited = new bool[width, height];
			Queue<GPoint> open = new();
			visited[startX, startY] = true;
			open.Enqueue(new GPoint(startX, startY));

			while (open.TryDequeue(out GPoint position))
			{
				if (position.X == destinationX &&
					position.Y == destinationY)
				{
					return true;
				}

				for (int direction = 1;
					direction <= DirectionCount;
					direction++)
				{
					GPoint offset = MoveDirections[direction];
					int nextY = position.Y + offset.Y;
					if (nextY < 0 || nextY >= height)
					{
						continue;
					}

					int nextX = AdjustX(
						position.X + offset.X,
						width);
					if (visited[nextX, nextY] ||
						!passable[nextX, nextY] ||
						!routeCells[nextX, nextY])
					{
						continue;
					}

					visited[nextX, nextY] = true;
					open.Enqueue(new GPoint(nextX, nextY));
				}
			}

			return false;
		}

		private static ClassicRoadToCityPlan FindNextMove(
			int startX,
			int startY,
			int destinationX,
			int destinationY,
			bool[,] passable,
			int[,] buildWorkCosts,
			int[,] movementCosts)
		{
			int width = passable.GetLength(0);
			int height = passable.GetLength(1);
			int[,] buildCellCounts = new int[width, height];
			int[,] costs = new int[width, height];
			int[,] steps = new int[width, height];
			int[,] firstDirections = new int[width, height];

			for (int y = 0; y < height; y++)
			{
				for (int x = 0; x < width; x++)
				{
					buildCellCounts[x, y] = Unreachable;
					costs[x, y] = Unreachable;
					steps[x, y] = Unreachable;
					firstDirections[x, y] = Unreachable;
				}
			}

			PriorityQueue<GPoint, SearchPriority> open = new();
			buildCellCounts[startX, startY] = 0;
			costs[startX, startY] = 0;
			steps[startX, startY] = 0;
			firstDirections[startX, startY] = 0;
			open.Enqueue(
				new GPoint(startX, startY),
				new SearchPriority(
					0,
					0,
					0,
					0,
					startY,
					startX));

			while (open.TryDequeue(
				out GPoint position,
				out SearchPriority priority))
			{
				if (priority.BuildCellCount !=
						buildCellCounts[
							position.X,
							position.Y] ||
					priority.MovementCost !=
						costs[position.X, position.Y] ||
					priority.Steps !=
						steps[position.X, position.Y] ||
					priority.FirstDirection !=
						firstDirections[
							position.X,
							position.Y])
				{
					continue;
				}

				if (position.X == destinationX &&
					position.Y == destinationY)
				{
					GPoint offset = MoveDirections[
						priority.FirstDirection];
					return new ClassicRoadToCityPlan(
						ClassicRoadToCityDecision.Move,
						priority.FirstDirection,
						new GPoint(
							AdjustX(startX + offset.X, width),
							startY + offset.Y));
				}

				for (int direction = 1;
					direction <= DirectionCount;
					direction++)
				{
					GPoint offset = MoveDirections[direction];
					int nextY = position.Y + offset.Y;
					if (nextY < 0 || nextY >= height)
					{
						continue;
					}

					int nextX = AdjustX(
						position.X + offset.X,
						width);
					if (!passable[nextX, nextY])
					{
						continue;
					}

					int nextBuildCellCount =
						priority.BuildCellCount +
						buildWorkCosts[nextX, nextY];
					int nextCost =
						priority.MovementCost +
						movementCosts[nextX, nextY];
					int nextSteps = priority.Steps + 1;
					int nextFirstDirection =
						priority.Steps == 0
							? direction
							: priority.FirstDirection;

					if (!IsBetterPath(
						nextBuildCellCount,
						nextCost,
						nextSteps,
						nextFirstDirection,
						buildCellCounts[nextX, nextY],
						costs[nextX, nextY],
						steps[nextX, nextY],
						firstDirections[nextX, nextY]))
					{
						continue;
					}

					buildCellCounts[nextX, nextY] =
						nextBuildCellCount;
					costs[nextX, nextY] = nextCost;
					steps[nextX, nextY] = nextSteps;
					firstDirections[nextX, nextY] =
						nextFirstDirection;
					open.Enqueue(
						new GPoint(nextX, nextY),
						new SearchPriority(
							nextBuildCellCount,
							nextCost,
							nextSteps,
							nextFirstDirection,
							nextY,
							nextX));
				}
			}

			return ClassicRoadToCityPlan.Ineligible;
		}

		private static bool IsBetterPath(
			int buildCellCount,
			int movementCost,
			int steps,
			int firstDirection,
			int oldBuildCellCount,
			int oldMovementCost,
			int oldSteps,
			int oldFirstDirection)
		{
			return buildCellCount < oldBuildCellCount ||
				(buildCellCount == oldBuildCellCount &&
					(movementCost < oldMovementCost ||
						(movementCost == oldMovementCost &&
							(steps < oldSteps ||
								(steps == oldSteps &&
									firstDirection <
										oldFirstDirection)))));
		}

		private static bool IsKnownPosition(
			GameData gameData,
			ushort visibilityMask,
			int x,
			int y,
			int width,
			int height)
		{
			return IsValidPosition(x, y, width, height) &&
				(gameData.MapVisibility[x, y] &
					visibilityMask) != 0;
		}

		private static bool HasTechnology(
			GameData gameData,
			int playerID,
			TechnologyAdvanceEnum technology)
		{
			int technologyID = (int)technology;
			return playerID > 0 &&
				playerID < gameData.Players.Length &&
				technologyID >= 0 &&
				technologyID < 71 &&
				(gameData.Players[playerID]
					.DiscoveredTechnologyFlags[technologyID >> 4] &
					(1 << (technologyID & 0xf))) != 0;
		}

		private static bool IsValidPosition(
			int x,
			int y,
			int width,
			int height)
		{
			return x >= 0 &&
				x < width &&
				y >= 0 &&
				y < height;
		}

		private static int AdjustX(int x, int width)
		{
			int adjusted = x % width;
			return adjusted < 0 ? adjusted + width : adjusted;
		}

		private readonly record struct SearchPriority(
			int BuildCellCount,
			int MovementCost,
			int Steps,
			int FirstDirection,
			int Y,
			int X)
			: IComparable<SearchPriority>
		{
			public int CompareTo(SearchPriority other)
			{
				int comparison =
					BuildCellCount.CompareTo(
						other.BuildCellCount);
				if (comparison != 0)
				{
					return comparison;
				}

				comparison =
					MovementCost.CompareTo(
						other.MovementCost);
				if (comparison != 0)
				{
					return comparison;
				}

				comparison = Steps.CompareTo(other.Steps);
				if (comparison != 0)
				{
					return comparison;
				}

				comparison =
					FirstDirection.CompareTo(
						other.FirstDirection);
				if (comparison != 0)
				{
					return comparison;
				}

				comparison = Y.CompareTo(other.Y);
				return comparison != 0
					? comparison
					: X.CompareTo(other.X);
			}
		}
	}
}
