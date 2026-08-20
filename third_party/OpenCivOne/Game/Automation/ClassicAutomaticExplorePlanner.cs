using OpenCivOne.Graphics;

namespace OpenCivOne
{
	public enum ClassicAutomaticExploreDecision
	{
		Move,
		Ineligible,
		NoKnownFrontier
	}

	public readonly record struct ClassicAutomaticExplorePlan(
		ClassicAutomaticExploreDecision Decision,
		int Direction,
		GPoint Target)
	{
		public static ClassicAutomaticExplorePlan Ineligible =>
			new(
				ClassicAutomaticExploreDecision.Ineligible,
				0,
				new GPoint(-1));

		public static ClassicAutomaticExplorePlan NoKnownFrontier =>
			new(
				ClassicAutomaticExploreDecision.NoKnownFrontier,
				0,
				new GPoint(-1));
	}

	/// <summary>
	/// Plans one deterministic automatic-exploration move using only map
	/// information already known to the human player. The planner never
	/// changes unit, GoTo, map or random-number-generator state.
	/// </summary>
	public static class ClassicAutomaticExplorePlanner
	{
		private const int DirectionCount = 8;
		private const int OpenSeaExplorationRadius = 5;
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

		public static ClassicAutomaticExplorePlan PlanNextMove(
			GameData gameData,
			MapManagement mapManagement,
			int playerID,
			Unit unit)
		{
			ArgumentNullException.ThrowIfNull(gameData);
			ArgumentNullException.ThrowIfNull(mapManagement);
			ArgumentNullException.ThrowIfNull(unit);

			if (!IsEligible(gameData, playerID, unit))
			{
				return ClassicAutomaticExplorePlan.Ineligible;
			}

			int width = gameData.MapVisibility.GetLength(0);
			int height = gameData.MapVisibility.GetLength(1);
			int startX = unit.Position.X;
			int startY = unit.Position.Y;
			ushort visibilityMask = (ushort)(1 << playerID);
			UnitMovementTypeEnum movementType =
				gameData.Units[(int)unit.UnitType].MovementType;

			if (startX < 0 ||
				startX >= width ||
				startY < 0 ||
				startY >= height ||
				(gameData.MapVisibility[startX, startY] & visibilityMask) == 0)
			{
				return ClassicAutomaticExplorePlan.Ineligible;
			}

			// Ocean-capable ships cannot be lost merely for ending a turn
			// away from land. In 1991+ they should therefore probe an
			// adjacent unknown cell before taking a longer route through
			// already charted coastal water. Triremes deliberately retain
			// the original safety-first return-to-coast planning below.
			if (movementType == UnitMovementTypeEnum.Water &&
				unit.UnitType != UnitTypeEnum.Trireme)
			{
				ClassicAutomaticExplorePlan openSeaProbe =
					PlanUnknownAdjacentStep(
						gameData,
						mapManagement,
						playerID,
						unit,
						visibilityMask);
				if (openSeaProbe.Decision ==
					ClassicAutomaticExploreDecision.Move)
				{
					return openSeaProbe;
				}
			}

			bool[,] passable = new bool[width, height];
			int[,] movementCosts = new int[width, height];
			int[,] unknownNeighbourCounts = new int[width, height];
			bool[,] ownCityCells =
				BuildOwnCityCells(
					gameData,
					playerID,
					width,
					height);
			bool[,] knownEnemyUnitCells =
				BuildKnownEnemyUnitCells(
					gameData,
					playerID,
					visibilityMask,
					width,
					height);

			// The visibility test deliberately happens before every map-data
			// read. Unknown terrain, improvements, ownership, group IDs,
			// cities and units therefore cannot influence this projection.
			for (int y = 0; y < height; y++)
			{
				for (int x = 0; x < width; x++)
				{
					if ((gameData.MapVisibility[x, y] & visibilityMask) == 0)
					{
						continue;
					}

					TerrainTypeEnum terrain =
						mapManagement.GetTerrainType(x, y);
					bool canEnter =
						CanEnter(terrain, movementType) ||
						(movementType ==
								UnitMovementTypeEnum.Water &&
							ownCityCells[x, y]);
					if (!canEnter ||
						knownEnemyUnitCells[x, y])
					{
						continue;
					}

					passable[x, y] = true;
					movementCosts[x, y] =
						GetKnownMovementCost(
							gameData,
							mapManagement,
							x,
							y,
							movementType,
							terrain);
					unknownNeighbourCounts[x, y] =
						CountUnknownNeighbours(
							gameData,
							x,
							y,
							visibilityMask);
				}
			}

			if (!passable[startX, startY])
			{
				return ClassicAutomaticExplorePlan.Ineligible;
			}

			int[,] costs = new int[width, height];
			int[,] steps = new int[width, height];
			int[,] firstDirections = new int[width, height];

			for (int y = 0; y < height; y++)
			{
				for (int x = 0; x < width; x++)
				{
					costs[x, y] = Unreachable;
					steps[x, y] = Unreachable;
					firstDirections[x, y] = Unreachable;
				}
			}

			PriorityQueue<GPoint, SearchPriority> open = new();
			costs[startX, startY] = 0;
			steps[startX, startY] = 0;
			firstDirections[startX, startY] = 0;
			open.Enqueue(
				unit.Position,
				new SearchPriority(0, 0, 0, startY, startX));

			while (open.TryDequeue(out GPoint position, out SearchPriority priority))
			{
				if (priority.Cost != costs[position.X, position.Y] ||
					priority.Steps != steps[position.X, position.Y] ||
					priority.FirstDirection != firstDirections[position.X, position.Y])
				{
					continue;
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

					int nextX = AdjustX(position.X + offset.X, width);
					if (!passable[nextX, nextY])
					{
						continue;
					}

					int nextCost =
						priority.Cost + movementCosts[nextX, nextY];
					int nextSteps = priority.Steps + 1;
					int nextFirstDirection =
						priority.Steps == 0
							? direction
							: priority.FirstDirection;

					if (!IsBetterPath(
						nextCost,
						nextSteps,
						nextFirstDirection,
						costs[nextX, nextY],
						steps[nextX, nextY],
						firstDirections[nextX, nextY]))
					{
						continue;
					}

					costs[nextX, nextY] = nextCost;
					steps[nextX, nextY] = nextSteps;
					firstDirections[nextX, nextY] =
						nextFirstDirection;
					open.Enqueue(
						new GPoint(nextX, nextY),
						new SearchPriority(
							nextCost,
							nextSteps,
							nextFirstDirection,
							nextY,
							nextX));
				}
			}

			FrontierCandidate? best = null;
			for (int y = 0; y < height; y++)
			{
				for (int x = 0; x < width; x++)
				{
					if ((x == startX && y == startY) ||
						!passable[x, y] ||
						costs[x, y] == Unreachable ||
						unknownNeighbourCounts[x, y] == 0 ||
						!IsSafeKnownFirstMove(
							gameData,
							mapManagement,
							playerID,
							unit,
							firstDirections[x, y],
							passable,
							movementCosts,
							visibilityMask))
					{
						continue;
					}

					FrontierCandidate candidate = new(
						GetFrontierExplorationPriority(
							gameData,
							mapManagement,
							unit,
							movementType,
							new GPoint(x, y),
							visibilityMask),
						costs[x, y],
						steps[x, y],
						unknownNeighbourCounts[x, y],
						y,
						x,
						firstDirections[x, y]);

					if (best is null ||
						candidate.CompareTo(best.Value) < 0)
					{
						best = candidate;
					}
				}
			}

			if (best is null)
			{
				return PlanUnknownAdjacentStep(
					gameData,
					mapManagement,
					playerID,
					unit,
					visibilityMask);
			}

			FrontierCandidate target = best.Value;
			return new ClassicAutomaticExplorePlan(
				ClassicAutomaticExploreDecision.Move,
				target.FirstDirection,
				new GPoint(target.X, target.Y));
		}

		private static bool IsSafeKnownFirstMove(
			GameData gameData,
			MapManagement mapManagement,
			int playerID,
			Unit unit,
			int firstDirection,
			bool[,] passable,
			int[,] movementCosts,
			ushort visibilityMask)
		{
			if (unit.UnitType != UnitTypeEnum.Trireme)
			{
				return true;
			}

			if (firstDirection is < 1 or > DirectionCount)
			{
				return false;
			}

			int width = passable.GetLength(0);
			int height = passable.GetLength(1);
			GPoint offset = MoveDirections[firstDirection];
			int destinationY = unit.Position.Y + offset.Y;
			if (destinationY < 0 || destinationY >= height)
			{
				return false;
			}

			int destinationX = AdjustX(
				unit.Position.X + offset.X,
				width);
			if (!passable[destinationX, destinationY])
			{
				return false;
			}

			int remainingAfterMove =
				unit.RemainingMoves -
				movementCosts[destinationX, destinationY];
			if (remainingAfterMove < 0)
			{
				return false;
			}

			GPoint destination =
				new(destinationX, destinationY);
			return HasKnownAdjacentLand(
					gameData,
					mapManagement,
					destination,
					visibilityMask) ||
				CanReachKnownCoast(
					gameData,
					mapManagement,
					destination,
					unit.Position,
					remainingAfterMove,
					passable,
					movementCosts,
					visibilityMask);
		}

		private static ClassicAutomaticExplorePlan
			PlanUnknownAdjacentStep(
				GameData gameData,
				MapManagement mapManagement,
				int playerID,
				Unit unit,
				ushort visibilityMask)
		{
			int width = gameData.MapVisibility.GetLength(0);
			int height = gameData.MapVisibility.GetLength(1);
			bool triremeCanReturn =
				unit.UnitType != UnitTypeEnum.Trireme ||
				(unit.RemainingMoves >= 6 &&
				 HasKnownAdjacentLand(
					gameData,
					mapManagement,
					unit.Position,
					visibilityMask));
			if (!triremeCanReturn)
			{
				return ClassicAutomaticExplorePlan.NoKnownFrontier;
			}

			UnitMovementTypeEnum movementType =
				gameData.Units[(int)unit.UnitType].MovementType;
			bool preferLargestFogMass =
				movementType == UnitMovementTypeEnum.Water &&
				unit.UnitType != UnitTypeEnum.Trireme;
			int bestDirection = 0;
			int bestUnexploredArea = -1;
			for (int direction = 1;
				direction <= DirectionCount;
				direction++)
			{
				GPoint offset = MoveDirections[direction];
				int y = unit.Position.Y + offset.Y;
				if (y < 0 || y >= height)
				{
					continue;
				}

				int x = AdjustX(unit.Position.X + offset.X, width);
				if ((gameData.MapVisibility[x, y] &
					visibilityMask) != 0)
				{
					continue;
				}

				// The target remains deliberately unread. Normal movement
				// decides whether the unknown cell matches the unit's
				// movement type, so automation learns no hidden terrain.
				if (!preferLargestFogMass)
				{
					return new ClassicAutomaticExplorePlan(
						ClassicAutomaticExploreDecision.Move,
						direction,
						new GPoint(x, y));
				}

				int unexploredArea =
					CountUnknownCellsWithinRadius(
						gameData,
						new GPoint(x, y),
						visibilityMask,
						OpenSeaExplorationRadius);
				if (unexploredArea > bestUnexploredArea)
				{
					bestDirection = direction;
					bestUnexploredArea = unexploredArea;
				}
			}

			if (bestDirection != 0)
			{
				GPoint offset = MoveDirections[bestDirection];
				return new ClassicAutomaticExplorePlan(
					ClassicAutomaticExploreDecision.Move,
					bestDirection,
					new GPoint(
						AdjustX(unit.Position.X + offset.X, width),
						unit.Position.Y + offset.Y));
			}

			return ClassicAutomaticExplorePlan.NoKnownFrontier;
		}

		private static int GetFrontierExplorationPriority(
			GameData gameData,
			MapManagement mapManagement,
			Unit unit,
			UnitMovementTypeEnum movementType,
			GPoint position,
			ushort visibilityMask)
		{
			if (movementType != UnitMovementTypeEnum.Water)
			{
				return 0;
			}

			if (unit.UnitType == UnitTypeEnum.Trireme)
			{
				return HasKnownAdjacentLand(
						gameData,
						mapManagement,
						position,
						visibilityMask)
					? 0
					: 1;
			}

			// Sail and all later ships cannot be lost merely for ending a
			// turn on open sea. They therefore rank a broad fog mass ahead
			// of a small coastal remainder, even when the latter is closer.
			// Only visibility is read: hidden terrain remains unknown.
			return -CountUnknownCellsWithinRadius(
				gameData,
				position,
				visibilityMask,
				OpenSeaExplorationRadius);
		}

		private static int CountUnknownCellsWithinRadius(
			GameData gameData,
			GPoint position,
			ushort visibilityMask,
			int radius)
		{
			int width = gameData.MapVisibility.GetLength(0);
			int height = gameData.MapVisibility.GetLength(1);
			int count = 0;

			for (int yOffset = -radius;
				yOffset <= radius;
				yOffset++)
			{
				int y = position.Y + yOffset;
				if (y < 0 || y >= height)
				{
					continue;
				}

				for (int xOffset = -radius;
					xOffset <= radius;
					xOffset++)
				{
					int x = AdjustX(position.X + xOffset, width);
					if ((gameData.MapVisibility[x, y] &
						visibilityMask) == 0)
					{
						count++;
					}
				}
			}

			return count;
		}

		private static bool CanReachKnownCoast(
			GameData gameData,
			MapManagement mapManagement,
			GPoint start,
			GPoint turnOrigin,
			int movementBudget,
			bool[,] passable,
			int[,] movementCosts,
			ushort visibilityMask)
		{
			if (movementBudget <= 0)
			{
				return false;
			}

			int width = passable.GetLength(0);
			int height = passable.GetLength(1);
			int[,] costs = new int[width, height];
			for (int y = 0; y < height; y++)
			{
				for (int x = 0; x < width; x++)
				{
					costs[x, y] = Unreachable;
				}
			}

			PriorityQueue<GPoint, int> open = new();
			costs[start.X, start.Y] = 0;
			open.Enqueue(start, 0);
			while (open.TryDequeue(
				out GPoint position,
				out int cost))
			{
				if (cost != costs[position.X, position.Y] ||
					cost > movementBudget)
				{
					continue;
				}

				// Returning to the exact cell where this turn started is
				// survival, but it is not exploration progress. Accepting
				// that cell as the only reachable coast made a Trireme sail
				// out and back along the same edge every turn after the
				// probed sea cell had already become known.
				if (position != start &&
					position != turnOrigin &&
					HasKnownAdjacentLand(
						gameData,
						mapManagement,
						position,
						visibilityMask))
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
					if (!passable[nextX, nextY])
					{
						continue;
					}

					int nextCost =
						cost + movementCosts[nextX, nextY];
					if (nextCost > movementBudget ||
						nextCost >= costs[nextX, nextY])
					{
						continue;
					}

					costs[nextX, nextY] = nextCost;
					open.Enqueue(
						new GPoint(nextX, nextY),
						nextCost);
				}
			}

			return false;
		}

		private static bool HasKnownAdjacentLand(
			GameData gameData,
			MapManagement mapManagement,
			GPoint position,
			ushort visibilityMask)
		{
			int width = gameData.MapVisibility.GetLength(0);
			int height = gameData.MapVisibility.GetLength(1);
			for (int direction = 1;
				direction <= DirectionCount;
				direction++)
			{
				GPoint offset = MoveDirections[direction];
				int y = position.Y + offset.Y;
				if (y < 0 || y >= height)
				{
					continue;
				}

				int x = AdjustX(position.X + offset.X, width);
				if ((gameData.MapVisibility[x, y] &
						visibilityMask) == 0 ||
					mapManagement.GetTerrainType(x, y) ==
						TerrainTypeEnum.Water)
				{
					continue;
				}

				return true;
			}

			return false;
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
					city.Position.X < 0 ||
					city.Position.X >= width ||
					city.Position.Y < 0 ||
					city.Position.Y >= height)
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
					// Visibility is checked before the position and type.
					// Unseen units therefore cannot influence exploration.
					if ((unit.VisibleByPlayer &
						visibilityMask) == 0)
					{
						continue;
					}

					int x = unit.Position.X;
					int y = unit.Position.Y;
					if (unit.UnitType != UnitTypeEnum.None &&
						x >= 0 &&
						x < width &&
						y >= 0 &&
						y < height &&
						(gameData.MapVisibility[x, y] &
							visibilityMask) != 0)
					{
						blockedCells[x, y] = true;
					}
				}
			}

			return blockedCells;
		}

		private static bool IsEligible(
			GameData gameData,
			int playerID,
			Unit unit)
		{
			if (playerID < 0 ||
				playerID >= gameData.Players.Length ||
				playerID != gameData.HumanPlayerID ||
				unit.PlayerID != playerID ||
				unit.RemainingMoves <= 0 ||
				unit.UnitType == UnitTypeEnum.None ||
				unit.UnitType == UnitTypeEnum.Nuclear ||
				(int)unit.UnitType < 0 ||
				(int)unit.UnitType >= gameData.Units.Length)
			{
				return false;
			}

			UnitMovementTypeEnum movementType =
				gameData.Units[(int)unit.UnitType].MovementType;
			return movementType == UnitMovementTypeEnum.Land ||
				movementType == UnitMovementTypeEnum.Water;
		}

		private static bool CanEnter(
			TerrainTypeEnum terrain,
			UnitMovementTypeEnum movementType)
		{
			return movementType switch
			{
				UnitMovementTypeEnum.Land =>
					terrain != TerrainTypeEnum.Water,
				UnitMovementTypeEnum.Water =>
					terrain == TerrainTypeEnum.Water,
				_ => false
			};
		}

		private static int GetKnownMovementCost(
			GameData gameData,
			MapManagement mapManagement,
			int x,
			int y,
			UnitMovementTypeEnum movementType,
			TerrainTypeEnum terrain)
		{
			if (movementType == UnitMovementTypeEnum.Water)
			{
				return 3;
			}

			// Despite the historical method names, 15c1 reads the human
			// player's last-known improvement layer while 1585 reads the
			// authoritative layer.
			TerrainImprovementFlagsEnum improvements =
				mapManagement.F0_2aea_15c1_GetTerrainImprovements(x, y);
			if (improvements.HasFlag(
				TerrainImprovementFlagsEnum.RailRoad))
			{
				return 0;
			}

			if (improvements.HasFlag(
				TerrainImprovementFlagsEnum.Road))
			{
				return 1;
			}

			return Math.Max(
				1,
				gameData.Terrains[(int)terrain].MovementCost * 3);
		}

		private static int CountUnknownNeighbours(
			GameData gameData,
			int x,
			int y,
			ushort visibilityMask)
		{
			int width = gameData.MapVisibility.GetLength(0);
			int height = gameData.MapVisibility.GetLength(1);
			int count = 0;

			for (int direction = 1;
				direction <= DirectionCount;
				direction++)
			{
				GPoint offset = MoveDirections[direction];
				int neighbourY = y + offset.Y;
				if (neighbourY < 0 || neighbourY >= height)
				{
					continue;
				}

				int neighbourX = AdjustX(x + offset.X, width);
				if ((gameData.MapVisibility[
					neighbourX,
					neighbourY] & visibilityMask) == 0)
				{
					count++;
				}
			}

			return count;
		}

		private static bool IsBetterPath(
			int cost,
			int steps,
			int firstDirection,
			int oldCost,
			int oldSteps,
			int oldFirstDirection)
		{
			return cost < oldCost ||
				(cost == oldCost &&
					(steps < oldSteps ||
						(steps == oldSteps &&
							firstDirection < oldFirstDirection)));
		}

		private static int AdjustX(int x, int width)
		{
			int adjusted = x % width;
			return adjusted < 0 ? adjusted + width : adjusted;
		}

		private readonly record struct SearchPriority(
			int Cost,
			int Steps,
			int FirstDirection,
			int Y,
			int X)
			: IComparable<SearchPriority>
		{
			public int CompareTo(SearchPriority other)
			{
				int comparison = Cost.CompareTo(other.Cost);
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
					FirstDirection.CompareTo(other.FirstDirection);
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

		private readonly record struct FrontierCandidate(
			int ExplorationPriority,
			int Cost,
			int Steps,
			int UnknownNeighbourCount,
			int Y,
			int X,
			int FirstDirection)
			: IComparable<FrontierCandidate>
		{
			public int CompareTo(FrontierCandidate other)
			{
				int comparison =
					ExplorationPriority.CompareTo(
						other.ExplorationPriority);
				if (comparison != 0)
				{
					return comparison;
				}

				comparison = Cost.CompareTo(other.Cost);
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
					other.UnknownNeighbourCount.CompareTo(
						UnknownNeighbourCount);
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
				return comparison != 0
					? comparison
					: FirstDirection.CompareTo(other.FirstDirection);
			}
		}
	}
}
