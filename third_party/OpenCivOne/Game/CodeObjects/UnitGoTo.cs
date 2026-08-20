using OpenCivOne.Graphics;
using OpenCivOne.Localization;
using OpenCivOne.Runtime;

namespace OpenCivOne
{
	/// <summary>
	/// This class encapsulates new GoTo algorithm.
	/// The old Goto Algorithm is included for archival purposes. It is unreliable and produces array index out of bounds often.
	/// </summary>
	public class UnitGoTo
	{
		private OpenCivOneGame parent;
		private GameData gameData;
		private readonly Dictionary<Unit, TriremeGoToPlanState>
			triremeGoToPlanStates = new();

		private int Var_6590_DestinationX = -1;
		private int Var_6592_DestinationY = -1;
		public int[] Arr_6594_PathX = new int[256];
		public int[] Arr_6694_PathY = new int[256];
		public int Var_6794 = 0;
		public int Var_6796_LastDestinationX = 0;
		public int Var_6798_LastDestinationY = 0;
		public int[,] Arr_b780 = new int[16, 16];
		public int[,] Arr_d816 = new int[20, 13]; // Divided by 4
		public int[,] Arr_db44_LandPath = new int[20, 13]; // Divided by 4
		public int[,] Arr_7f38_WaterPath = new int[20, 13]; // Divided by 4

		public UnitGoTo(OpenCivOneGame parent)
		{
			this.parent = parent;
			this.gameData = parent.GameData;

			// Ensure that all arrays contain zero value initially

			for (int i = 0; i < this.Arr_6594_PathX.Length; i++)
			{
				this.Arr_6594_PathX[i] = 0;
			}

			for (int i = 0; i < this.Arr_6694_PathY.Length; i++)
			{
				this.Arr_6694_PathY[i] = 0;
			}

			for (int i = 0; i < this.Arr_db44_LandPath.GetLength(0); i++)
			{
				for (int j = 0; j < this.Arr_db44_LandPath.GetLength(1); j++)
				{
					this.Arr_db44_LandPath[i, j] = 0;
				}
			}

			for (int i = 0; i < this.Arr_7f38_WaterPath.GetLength(0); i++)
			{
				for (int j = 0; j < this.Arr_7f38_WaterPath.GetLength(1); j++)
				{
					this.Arr_7f38_WaterPath[i, j] = 0;
				}
			}

			for (int i = 0; i < this.Arr_b780.GetLength(0); i++)
			{
				for (int j = 0; j < this.Arr_b780.GetLength(1); j++)
				{
					this.Arr_b780[i, j] = 0;
				}
			}

			for (int i = 0; i < this.Arr_d816.GetLength(0); i++)
			{
				for (int j = 0; j < this.Arr_d816.GetLength(1); j++)
				{
					this.Arr_d816[i, j] = 0;
				}
			}
		}

		/// <summary>
		/// Gets the next position that this unit should move to
		/// </summary>
		/// <param name="playerID"></param>
		/// <param name="unitID"></param>
		/// <returns></returns>
		public int GetNextGoToMove(int playerID, int unitID)
		{
			Unit unit;

			if (playerID > 0 && (this.parent.GameData.ActiveCivilizations & (1 << playerID)) != 0 && unitID >= 0 && unitID < 128 &&
				(unit = this.parent.GameData.Players[playerID].Units[unitID]).UnitType != UnitTypeEnum.None)
			{
				unit.PlayerID = (short)playerID;

				return GetNextGoToMove(unit, true);
			}

			return -1;
		}

		/// <summary>
		/// Gets the next position that this unit should move to
		/// </summary>
		public int GetNextGoToMove(Unit unit, bool testVisibility)
		{
			int direction = -1;

			unit.GoToNextDirection = -1;

			if (this.parent.MapManagement.ValidateMapCoordinates(unit.GoToDestination) && unit.Position != unit.GoToDestination)
			{
				if (ShouldRebuildTrackedTriremePath(
						unit,
						testVisibility))
				{
					unit.GoToPath.Clear();
				}

				if (unit.GoToPath.Count == 0)
				{
					this.FindGoToPath(unit, testVisibility);
				}

				direction = GetNextPathDirection(unit);

				if (direction == -1 && unit.GoToPath.Count > 0)
				{
					// The unit can remain in place after a planned command (for
					// example when movement points are exhausted or a friendly
					// stack blocks the cell). Rebuild only genuinely stale paths
					// instead of treating a later waypoint as a multi-cell move.
					unit.GoToPath.Clear();
					this.FindGoToPath(unit, testVisibility);
					direction = GetNextPathDirection(unit);
				}

				if (direction == -1)
				{
					// We couldn't find a path for a destination
					unit.GoToDestination = OpenCivOneGame.InvalidPosition;
					unit.GoToPath.Clear();
					unit.GoToNextDirection = -1;
				}
				else
				{
					unit.GoToNextDirection = (short)direction;
				}
			}

			return direction;
		}

		internal IReadOnlyList<GPoint> BuildVisibleGoToPreview(
			int playerID,
			int unitID,
			GPoint destination)
		{
			if (!ClassicAiRuntimeProfiles.UsesSmartEnhancements(
					this.gameData.AiProfile) ||
				!this.gameData.GameSettingFlags.ShowGoToPaths ||
				playerID != this.gameData.HumanPlayerID ||
				playerID < 0 ||
				playerID >= this.gameData.Players.Length ||
				unitID < 0 ||
				unitID >= this.gameData.Players[playerID].Units.Length ||
				!this.parent.MapManagement.ValidateMapCoordinates(
					destination))
			{
				return Array.Empty<GPoint>();
			}

			Unit source =
				this.gameData.Players[playerID].Units[unitID];
			if (source.UnitType == UnitTypeEnum.None ||
				source.PlayerID != playerID)
			{
				return Array.Empty<GPoint>();
			}

			Unit preview = new()
			{
				ID = source.ID,
				UnitType = source.UnitType,
				Status = source.Status,
				Position = source.Position,
				RemainingMoves = source.RemainingMoves,
				SpecialMoves = source.SpecialMoves,
				NextUnitID = source.NextUnitID,
				PlayerID = source.PlayerID,
				HomeCityID = source.HomeCityID,
				VisibleByPlayer = source.VisibleByPlayer,
				GoToDestination = destination,
				GoToNextDirection = -1
			};

			FindGoToPath(
				preview,
				testVisibility: true,
				reportFailure: false);
			this.triremeGoToPlanStates.Remove(preview);
			if (preview.GoToDestination ==
					OpenCivOneGame.InvalidPosition ||
				preview.GoToPath.Count == 0)
			{
				return Array.Empty<GPoint>();
			}

			return preview.GoToPath.ToArray();
		}

		private int GetNextPathDirection(Unit unit)
		{
			// A waypoint is consumed only after the unit has actually reached it.
			// This lets a blocked or incomplete movement retry the same command.
			while (unit.GoToPath.Count > 0 &&
				unit.GoToPath.Peek() == unit.Position)
			{
				unit.GoToPath.Pop();
			}

			if (unit.GoToPath.Count == 0)
			{
				return -1;
			}

			GPoint moveOffset = unit.GoToPath.Peek() - unit.Position;

			// The path stores normalized map coordinates, so an adjacent
			// horizontal step across the map seam appears as +/-79 here.
			// Convert it back to the equivalent one-cell move before
			// looking up the original eight-direction command.
			if (moveOffset.X > MapManagement.XMedian)
			{
				moveOffset = new GPoint(
					moveOffset.X - MapManagement.Size.Width,
					moveOffset.Y);
			}
			else if (moveOffset.X < -MapManagement.XMedian)
			{
				moveOffset = new GPoint(
					moveOffset.X + MapManagement.Size.Width,
					moveOffset.Y);
			}

			int direction =
				this.parent.MapManagement.GetMoveOffset(moveOffset);

			return direction is >= 1 and <= 8
				? direction
				: -1;
		}

		/// <summary>
		/// Validates if the given destination coordinates are reachable for a given unit movement type
		/// </summary>
		/// <param name="src"></param>
		/// <param name="dest"></param>
		/// <param name="movementType"></param>
		/// <param name="maxMoves"></param>
		/// <returns></returns>
		public int GetGoToDistance(int srcX, int srcY, int dstX, int dstY, UnitMovementTypeEnum movementType, int maxMoves)
		{
			return GetGoToDistance(new GPoint(srcX, srcY), new GPoint(dstX, dstY), movementType, maxMoves);
		}

		/// <summary>
		/// Validates if the given destination coordinates are reachable for a given unit movement type
		/// </summary>
		/// <param name="src"></param>
		/// <param name="dest"></param>
		/// <param name="movementType"></param>
		/// <param name="maxMoves"></param>
		/// <returns></returns>
		public int GetGoToDistance(GPoint src, GPoint dest, UnitMovementTypeEnum movementType, int maxMoves)
		{
			Unit unit;

			switch (movementType)
			{
				case UnitMovementTypeEnum.Land:
					unit = new Unit();
					unit.UnitType = UnitTypeEnum.Militia;
					unit.Position = src;
					unit.GoToDestination = dest;
					break;

				case UnitMovementTypeEnum.Water:
					unit = new Unit();
					unit.UnitType = UnitTypeEnum.Trireme;
					unit.Position = src;
					unit.GoToDestination = dest;
					break;

				case UnitMovementTypeEnum.Air:
					unit = new Unit();
					unit.UnitType = UnitTypeEnum.Fighter;
					unit.Position = src;
					unit.GoToDestination = dest;
					break;

				default:
					return -1;
			}

			FindGoToPath(unit, false);

			int distance = -1;

			if (unit.GoToDestination != OpenCivOneGame.InvalidPosition && unit.GoToPath.Count > 0 && unit.GoToPath.Count < maxMoves)
			{
				distance = unit.GoToPath.Count;
			}

			return distance;
		}

		/// <summary>
		/// Validates if the given destination coordinates are reachable for a given unit movement type
		/// </summary>
		/// <param name="src"></param>
		/// <param name="dest"></param>
		/// <param name="movementType"></param>
		/// <param name="maxMoves"></param>
		/// <returns></returns>
		public bool IsValidGoToPath(GPoint src, GPoint dest, UnitMovementTypeEnum movementType, int maxMoves)
		{
			Unit unit;

			switch (movementType)
			{
				case UnitMovementTypeEnum.Land:
					unit = new Unit();
					unit.UnitType = UnitTypeEnum.Militia;
					unit.Position = src;
					unit.GoToDestination = dest;
					break;

				case UnitMovementTypeEnum.Water:
					unit = new Unit();
					unit.UnitType = UnitTypeEnum.Trireme;
					unit.Position = src;
					unit.GoToDestination = dest;
					break;

				case UnitMovementTypeEnum.Air:
					unit = new Unit();
					unit.UnitType = UnitTypeEnum.Fighter;
					unit.Position = src;
					unit.GoToDestination = dest;
					break;

				default:
					return false;
			}

			FindGoToPath(unit, false);

			return unit.GoToDestination != OpenCivOneGame.InvalidPosition && unit.GoToPath.Count > 0 && unit.GoToPath.Count < maxMoves;
		}

		#region AStar (A*) Path finding algorithm
		/// <summary>
		/// A Function to find the shortest path between tho points according to AStar (A*) Algorithm
		/// </summary>
		/// <param name="unit"></param>
		/// <param name="testVisibility">ID of the unit</param>
		private void FindGoToPath(
			Unit unit,
			bool testVisibility,
			bool reportFailure = true)
		{
			this.triremeGoToPlanStates.Remove(unit);

			if (unit.GoToDestination != OpenCivOneGame.InvalidPosition)
			{
				// Rules to satisfy:
				// 1) Source or destination cell position is out of range
				// 2) Destination is the same as the source position
				// 3) Destination has to be in the same movement group that the unit is
				// 4) For the unit that is moving on Land or Water we have to be on the same group
				// 4.1) Exception: water unit entering or exiting from a coastal city
				// 4.2) Exception: land unit embarking or disembarking to/from a transport
				// 5) Destination cell has to be visible to the Player

				bool destinationReached = false; // remains false if we can't find a path to a destination
				TerrainMapGroupTypeEnum group1; // The unit can move on this terrain type
				TerrainMapGroupTypeEnum group2; // The unit can move on this terrain type
				TerrainMapGroupTypeEnum group3; // The unit can move on this terrain type
				UnitMovementTypeEnum unitMovementType = this.gameData.Units[(int)unit.UnitType].MovementType;
				MapManagement map = this.parent.MapManagement;
				GPoint[] moveDirections = this.parent.MoveDirections;
				int startGroup = map.F0_2aea_1942_GetGroupID(unit.Position.X, unit.Position.Y);
				TerrainMapGroupTypeEnum startGroupType = map.GetGroupType(unit.Position);
				int destinationGroup = map.F0_2aea_1942_GetGroupID(unit.GoToDestination.X, unit.GoToDestination.Y);
				TerrainMapGroupTypeEnum destinationGroupType = map.GetGroupType(unit.GoToDestination);

				unit.GoToPath.Clear();

				switch (unitMovementType)
				{
					case UnitMovementTypeEnum.Land:
						group1 = TerrainMapGroupTypeEnum.Land;
						group2 = TerrainMapGroupTypeEnum.Land;
						break;

					case UnitMovementTypeEnum.Water:
						group1 = TerrainMapGroupTypeEnum.Water;
						group2 = TerrainMapGroupTypeEnum.Water;
						break;

					case UnitMovementTypeEnum.Air:
						group1 = TerrainMapGroupTypeEnum.Water;
						group2 = TerrainMapGroupTypeEnum.Land;
						break;

					default:
						throw new Exception("Unknown Unit Movement Type"); // should never happen, but we want to make compiler happy
				}

				group3 = group2;

				// Exception rules temporary values
				bool startGroupAdjacentToDestination = startGroup == destinationGroup && startGroupType == destinationGroupType; // the start group is adjacent to unit destination position
				bool destinationGroupAdjacentToStart = startGroup == destinationGroup && startGroupType == destinationGroupType; // the destination group is adjacent to unit current position

				if (!destinationGroupAdjacentToStart)
				{
					for (int i = 1; i < 9; i++)
					{
						GPoint newPosition = new(
							map.AdjustXPosition(
								unit.Position.X +
									moveDirections[i].X),
							unit.Position.Y +
								moveDirections[i].Y);

						if (map.ValidateMapCoordinates(newPosition) && 
							destinationGroup == map.F0_2aea_1942_GetGroupID(newPosition) && destinationGroupType == map.GetGroupType(newPosition))
						{
							destinationGroupAdjacentToStart = true;
							break;
						}
					}
				}

				if (!startGroupAdjacentToDestination)
				{
					for (int i = 1; i < 9; i++)
					{
						// This is the inverse boundary test: look for the
						// source group around the destination. Looking around
						// the source twice rejects valid embark/disembark and
						// coastal-city transitions from one-cell groups.
						GPoint newPosition = new(
							map.AdjustXPosition(
								unit.GoToDestination.X +
									moveDirections[i].X),
							unit.GoToDestination.Y +
								moveDirections[i].Y);

						if (map.ValidateMapCoordinates(newPosition) && 
							startGroup == map.F0_2aea_1942_GetGroupID(newPosition) && startGroupType == map.GetGroupType(newPosition))
						{
							startGroupAdjacentToDestination = true;
							break;
						}
					}
				}

				bool startIsTransportUnit = this.parent.UnitManagement.F0_1866_1380_GetStackUnitCount(unit.PlayerID, unit.ID, UnitRoleTypeEnum.SeaTransport) > 0;
				int destinationPlayerID = map.F0_2aea_14e0_GetCellActiveUnitPlayerID(unit.GoToDestination.X, unit.GoToDestination.Y);
				int destinationUnitID = map.F0_2aea_1458_GetCellActiveUnitID(unit.GoToDestination.X, unit.GoToDestination.Y);
				bool destinationIsTransportUnit = (destinationPlayerID >= 0 && destinationUnitID >= 0 && 
					this.parent.UnitManagement.F0_1866_1380_GetStackUnitCount(destinationPlayerID, destinationUnitID, UnitRoleTypeEnum.SeaTransport) > 0);
				int goToDistance = map.GetDistance(unit.Position, unit.GoToDestination);

				int startCityID = this.parent.Tools.F0_2dc4_00ba_GetCityByLocation(unit.Position.X, unit.Position.Y);
				int destinationCityID = this.parent.Tools.F0_2dc4_00ba_GetCityByLocation(unit.GoToDestination.X, unit.GoToDestination.Y);

				// Exception rules

				// water unit entering or exiting from a coastal city
				bool waterUnitCanMove = (unitMovementType == UnitMovementTypeEnum.Water) && 
					((startGroupAdjacentToDestination && destinationCityID >= 0 && startGroupType == TerrainMapGroupTypeEnum.Water && destinationGroupType == TerrainMapGroupTypeEnum.Land) ||
						(destinationGroupAdjacentToStart && startCityID >= 0 && startGroupType == TerrainMapGroupTypeEnum.Land && destinationGroupType == TerrainMapGroupTypeEnum.Water));

				// land unit embarking or disembarking to/from a transport
				bool landUnitCanMove = (unitMovementType == UnitMovementTypeEnum.Land) &&
					((startGroupAdjacentToDestination && startGroupType == TerrainMapGroupTypeEnum.Land && destinationIsTransportUnit) ||
						(destinationGroupAdjacentToStart && destinationGroupType == TerrainMapGroupTypeEnum.Land && startIsTransportUnit) ||
						(startGroupType == TerrainMapGroupTypeEnum.Water && startIsTransportUnit && destinationGroupType == TerrainMapGroupTypeEnum.Water && destinationIsTransportUnit));

				if (!map.ValidateMapCoordinates(unit.Position) || !map.ValidateMapCoordinates(unit.GoToDestination) ||
					unit.Position == unit.GoToDestination ||
					(map.GetGroupType(unit.GoToDestination) != group1 && map.GetGroupType(unit.GoToDestination) != group2 && !landUnitCanMove && !waterUnitCanMove) ||
					(unitMovementType != UnitMovementTypeEnum.Air && startGroup != destinationGroup && !landUnitCanMove && !waterUnitCanMove) ||
					(testVisibility && (this.parent.GameData.MapVisibility[unit.GoToDestination.X, unit.GoToDestination.Y] & (1 << unit.PlayerID)) == 0))
				{
					return;
				}

				// This assignment of group3 is because of exception rules, so we can cover these
				if (landUnitCanMove || waterUnitCanMove)
				{
					group3 = (startGroupType != group1 || startGroupType != group2) ? startGroupType :
						((destinationGroupType != group1 || destinationGroupType != group2) ? destinationGroupType : group3);
				}

				AStarCell[,] cells = new AStarCell[80, 50];

				for (int i = 0; i < cells.GetLength(0); i++)
				{
					for (int j = 0; j < cells.GetLength(1); j++)
					{
						cells[i, j] = new AStarCell(i, j);
					}
				}

				// Create a sorted open list in descending order (sorted from higher to lower value)
				// We compare this list by cell's f value
				List<AStarCell> openCells = new List<AStarCell>();

				// Initialize start cell
				AStarCell cell = cells[unit.Position.X, unit.Position.Y];
				cell.GCost = 0.0;
				cell.HCost = 0.0;
				cell.FCost = 0.0;
				cell.ParentPos = cell.Position;

				// Put the starting cell on the open list
				openCells.Add(cell);

				while (openCells.Count > 0)
				{
					// Our most favorable current cell is the cell with the
					// lowest accumulated movement cost. A geometric heuristic
					// is deliberately not used here: roads can cost one third
					// of a move and railroads can cost zero, so map distance
					// would overestimate the remaining cost and could make a
					// longer but faster route lose.
					cell = openCells[openCells.Count - 1];
					GPoint pos = cell.Position;

					openCells.RemoveAt(openCells.Count - 1);

					// Mark this cell as closed
					cell.IsCellClosed = true;
					if (pos == unit.GoToDestination)
					{
						destinationReached = true;
						break;
					}

					// Generate all 8 successors of this cell
					for (int i = -1; i <= 1; i++)
					{
						for (int j = -1; j <= 1; j++)
						{
							if (i == 0 && j == 0)
								continue;

							GPoint newPos = pos.Offset(j, i);
							newPos = new(this.parent.MapManagement.AdjustXPosition(newPos.X), newPos.Y);

							// If new cell successor position is a valid position
							if (map.ValidateMapCoordinates(newPos))
							{
								AStarCell newCell = cells[newPos.X, newPos.Y];
								TerrainMapGroupTypeEnum cellGroupType = map.GetGroupType(newPos.X, newPos.Y);

								if (cellGroupType == group1 || cellGroupType == group2 || (newPos == unit.GoToDestination && cellGroupType == group3))
								{
									// Ignore the successor cell if it is closed or blocked
									if (!newCell.IsCellClosed &&
										(!testVisibility || (this.gameData.MapVisibility[newPos.X, newPos.Y] & (1 << unit.PlayerID)) != 0))
									{
										double movementCost =
											GetVisibleGoToMovementCost(
												unit,
												pos,
												newPos);
										if (movementCost == double.MaxValue)
										{
											continue;
										}

										double newGCost =
											cell.GCost + movementCost;
										double newHCost = 0.0;
										double newFCost = newGCost + newHCost;

										// Make current cell the parent of the new successor cell
										if (newCell.GCost == double.MaxValue)
										{
											// We have found a new path
											// Update the details of the new successor cell and add it to the open cell list in descending order
											newCell.GCost = newGCost;
											newCell.HCost = newHCost;
											newCell.FCost = newFCost;
											newCell.ParentPos = pos;

											bool bAdded = false;

											for (int k = 0; k < openCells.Count; k++)
											{
												if (openCells[k].FCost.CompareTo(newCell.FCost) <= 0)
												{
													openCells.Insert(k, newCell);
													bAdded = true;
													break;
												}
											}

											if (!bAdded)
											{
												openCells.Add(newCell);
											}
										}
										else if (newCell.GCost > newGCost)
										{
											// We have found a more favorable path
											// First, remove existing cell from open cell list to avoid duplicates
											for (int k = 0; k < openCells.Count; k++)
											{
												if (openCells[k].Position == newPos)
												{
													openCells.RemoveAt(k);
													break;
												}
											}

											// Update the details of the new successor cell and add it to the open cell list in descending order
											newCell.GCost = newGCost;
											newCell.HCost = newHCost;
											newCell.FCost = newFCost;
											newCell.ParentPos = pos;

											bool bAdded = false;

											for (int k = 0; k < openCells.Count; k++)
											{
												if (openCells[k].FCost.CompareTo(newCell.FCost) <= 0)
												{
													openCells.Insert(k, newCell);
													bAdded = true;
													break;
												}
											}

											if (!bAdded)
											{
												openCells.Add(newCell);
											}
										}
									}
								}
							}
						}
					}
				}

				// When the destination cell is not found and the open list is empty
				// We can safely conclude that we failed to reach the destination cell.
				// This may happen when there is no way to destination cell
				if (!destinationReached)
				{
					unit.GoToDestination = OpenCivOneGame.InvalidPosition;
				}
				else
				{
					bool usesTurnSafeTriremeRoute = false;

					// We have successfully found a path from Source to Destination position
					GPoint pos = unit.GoToDestination;

					// Exclude out source position
					while ((cell = cells[pos.X, pos.Y]).ParentPos != pos)
					{
						unit.GoToPath.Push(pos); // Store in reverse order
						pos = cell.ParentPos;
					}

					if (RequiresTurnSafePreNavigationTriremePath(
							unit,
							testVisibility))
					{
						if (!TryFindTurnSafePreNavigationTriremePath(
								unit,
								testVisibility,
								group3,
								out Stack<GPoint>? safePath))
						{
							// Smart 1991+ must never silently fall back to
							// the original route when that route would end a
							// pre-Navigation turn in open sea.
							unit.GoToDestination =
								OpenCivOneGame.InvalidPosition;
							unit.GoToPath.Clear();
							unit.GoToNextDirection = -1;
							this.triremeGoToPlanStates.Remove(unit);
							if (reportFailure)
							{
								this.parent.Host.ShowTransientStatus(
									ClassicGameText.Current[
										ClassicGameTextKey
											.TriremeNoSafeCoastalRoute]);
							}
							return;
						}

						unit.GoToPath = safePath;
						usesTurnSafeTriremeRoute = true;
					}

					RememberTrackedTriremePath(
						unit,
						testVisibility,
						usesTurnSafeTriremeRoute);
				}
			}
		}

		private bool ShouldRebuildTrackedTriremePath(
			Unit unit,
			bool testVisibility)
		{
			if (!ShouldTrackTriremePath(unit, testVisibility) ||
				unit.GoToPath.Count == 0)
			{
				return false;
			}

			TriremeGoToPlanState current =
				CaptureTriremeGoToPlanState(
					unit,
					usesTurnSafeRoute: false);
			if (!this.triremeGoToPlanStates.TryGetValue(
					unit,
					out TriremeGoToPlanState planned) ||
				planned.HasNavigation != current.HasNavigation ||
				planned.FullTurnMoves != current.FullTurnMoves)
			{
				return true;
			}

			return planned.UsesTurnSafeRoute &&
				!current.HasNavigation &&
				!IsCachedTriremePathTurnSafe(
					unit,
					current.FullTurnMoves);
		}

		private void RememberTrackedTriremePath(
			Unit unit,
			bool testVisibility,
			bool usesTurnSafeRoute)
		{
			if (!ShouldTrackTriremePath(unit, testVisibility) ||
				unit.GoToPath.Count == 0)
			{
				return;
			}

			this.triremeGoToPlanStates[unit] =
				CaptureTriremeGoToPlanState(
					unit,
					usesTurnSafeRoute);
		}

		private bool ShouldTrackTriremePath(
			Unit unit,
			bool testVisibility)
		{
			return testVisibility &&
				ClassicAiRuntimeProfiles.UsesSmartEnhancements(
					this.gameData.AiProfile) &&
				unit.UnitType == UnitTypeEnum.Trireme &&
				unit.PlayerID == this.gameData.HumanPlayerID &&
				unit.RemainingMoves > 0;
		}

		private bool RequiresTurnSafePreNavigationTriremePath(
			Unit unit,
			bool testVisibility)
		{
			return ShouldTrackTriremePath(unit, testVisibility) &&
				!this.parent.Segment_1ade
					.F0_1ade_22b5_PlayerHasTechnology(
						unit.PlayerID,
						TechnologyAdvanceEnum.Navigation);
		}

		private TriremeGoToPlanState CaptureTriremeGoToPlanState(
			Unit unit,
			bool usesTurnSafeRoute)
		{
			return new TriremeGoToPlanState(
				this.parent.Segment_1ade
					.F0_1ade_22b5_PlayerHasTechnology(
						unit.PlayerID,
						TechnologyAdvanceEnum.Navigation),
				GetTriremeFullTurnMoves(unit),
				usesTurnSafeRoute);
		}

		private int GetTriremeFullTurnMoves(Unit unit)
		{
			int fullTurnMoves =
				this.gameData.Units[(int)unit.UnitType].MoveCount * 3;
			if (this.parent.CityWorker
					.F0_1d12_6c97_PlayerHasWonder(
						unit.PlayerID,
						WonderEnum.Lighthouse) ||
				this.parent.CityWorker
					.F0_1d12_6c97_PlayerHasWonder(
						unit.PlayerID,
						WonderEnum.MagellansExpedition))
			{
				fullTurnMoves += 3;
			}

			return fullTurnMoves;
		}

		private bool IsCachedTriremePathTurnSafe(
			Unit unit,
			int fullTurnMoves)
		{
			if (fullTurnMoves <= 0)
			{
				return false;
			}

			int remainingMoves = unit.RemainingMoves;
			ushort visibilityMask =
				(ushort)(1 << unit.PlayerID);
			bool leftCurrentPosition = false;
			foreach (GPoint waypoint in unit.GoToPath)
			{
				if (!leftCurrentPosition &&
					waypoint == unit.Position)
				{
					continue;
				}

				leftCurrentPosition = true;
				remainingMoves -= 3;
				if (remainingMoves > 0)
				{
					continue;
				}

				if (!IsKnownCoastalTriremeCell(
						waypoint,
						visibilityMask))
				{
					return false;
				}

				remainingMoves = fullTurnMoves;
			}

			return true;
		}

		private bool TryFindTurnSafePreNavigationTriremePath(
			Unit unit,
			bool testVisibility,
			TerrainMapGroupTypeEnum destinationGroupType,
			out Stack<GPoint> safePath)
		{
			safePath = new Stack<GPoint>();
			if (!RequiresTurnSafePreNavigationTriremePath(
					unit,
					testVisibility))
			{
				return false;
			}

			int fullTurnMoves = GetTriremeFullTurnMoves(unit);

			if (fullTurnMoves <= 0)
			{
				return false;
			}

			ushort visibilityMask =
				(ushort)(1 << unit.PlayerID);
			TriremeRouteState start = new(
				unit.Position,
				unit.RemainingMoves);
			Dictionary<TriremeRouteState, double> bestCosts =
				new()
				{
					[start] = 0.0
				};
			Dictionary<TriremeRouteState, TriremeRouteState>
				parents = new();
			PriorityQueue<
				TriremeRouteState,
				(double Cost, int Steps, long Sequence)> open =
					new();
			long sequence = 0;
			open.Enqueue(start, (0.0, 0, sequence++));

			while (open.TryDequeue(
				out TriremeRouteState current,
				out (double Cost, int Steps, long Sequence)
					priority))
			{
				if (!bestCosts.TryGetValue(
						current,
						out double currentBestCost) ||
					priority.Cost > currentBestCost)
				{
					continue;
				}

				if (current.Position == unit.GoToDestination)
				{
					TriremeRouteState pathState = current;
					while (pathState != start)
					{
						safePath.Push(pathState.Position);
						pathState = parents[pathState];
					}

					return safePath.Count > 0;
				}

				for (int yOffset = -1;
					yOffset <= 1;
					yOffset++)
				{
					for (int xOffset = -1;
						xOffset <= 1;
						xOffset++)
					{
						if (xOffset == 0 && yOffset == 0)
						{
							continue;
						}

						GPoint nextPosition = new(
							this.parent.MapManagement.AdjustXPosition(
								current.Position.X + xOffset),
							current.Position.Y + yOffset);
						if (!this.parent.MapManagement
								.ValidateMapCoordinates(nextPosition) ||
							(this.gameData.MapVisibility[
								nextPosition.X,
								nextPosition.Y] &
								visibilityMask) == 0)
						{
							continue;
						}

						TerrainMapGroupTypeEnum nextGroupType =
							this.parent.MapManagement.GetGroupType(
								nextPosition);
						if (nextGroupType !=
								TerrainMapGroupTypeEnum.Water &&
							(nextPosition != unit.GoToDestination ||
							 nextGroupType != destinationGroupType))
						{
							continue;
						}

						double movementCost =
							GetVisibleGoToMovementCost(
								unit,
								current.Position,
								nextPosition);
						if (movementCost == double.MaxValue)
						{
							continue;
						}

						// Sea movement consumes one complete move (three
						// internal movement points), independently of the
						// terrain image below the ship.
						int remainingAfterMove =
							current.RemainingMoves - 3;
						bool endsTurn = remainingAfterMove <= 0;
						if (endsTurn &&
							!IsKnownCoastalTriremeCell(
								nextPosition,
								visibilityMask))
						{
							continue;
						}

						int nextRemainingMoves = endsTurn
							? fullTurnMoves
							: remainingAfterMove;
						TriremeRouteState next = new(
							nextPosition,
							nextRemainingMoves);
						double nextCost =
							currentBestCost + movementCost;
						if (bestCosts.TryGetValue(
								next,
								out double oldCost) &&
							oldCost <= nextCost)
						{
							continue;
						}

						bestCosts[next] = nextCost;
						parents[next] = current;
						open.Enqueue(
							next,
							(
								nextCost,
								priority.Steps + 1,
								sequence++));
					}
				}
			}

			safePath.Clear();
			return false;
		}

		private bool IsKnownCoastalTriremeCell(
			GPoint position,
			ushort visibilityMask)
		{
			if (this.parent.MapManagement.GetTerrainType(position) !=
				TerrainTypeEnum.Water)
			{
				return true;
			}

			for (int direction = 1; direction <= 8; direction++)
			{
				GPoint offset = this.parent.MoveDirections[direction];
				GPoint neighbour = new(
					this.parent.MapManagement.AdjustXPosition(
						position.X + offset.X),
					position.Y + offset.Y);
				if (!this.parent.MapManagement
						.ValidateMapCoordinates(neighbour) ||
					(this.gameData.MapVisibility[
						neighbour.X,
						neighbour.Y] &
						visibilityMask) == 0)
				{
					continue;
				}

				if (this.parent.MapManagement.GetTerrainType(
						neighbour) != TerrainTypeEnum.Water)
				{
					return true;
				}
			}

			return false;
		}

		private readonly record struct TriremeRouteState(
			GPoint Position,
			int RemainingMoves);

		private readonly record struct TriremeGoToPlanState(
			bool HasNavigation,
			int FullTurnMoves,
			bool UsesTurnSafeRoute);

		/// <summary>
		/// Movement cost based on currently visible terrain and improvements
		/// </summary>
		internal double GetVisibleGoToMovementCost(
			Unit unit,
			GPoint source,
			GPoint destination)
		{
			MapManagement map = this.parent.MapManagement;
			if (!map.ValidateMapCoordinates(source) ||
				!map.ValidateMapCoordinates(destination) ||
				unit.UnitType < UnitTypeEnum.Settler ||
				unit.UnitType >= UnitTypeEnum.Max)
			{
				return double.MaxValue;
			}

			if (!ClassicAiRuntimeProfiles.UsesSmartEnhancements(
					this.parent.GameData.AiProfile))
			{
				return GetOriginalVisibleGoToMovementCost(
					unit.PlayerID,
					destination);
			}

			UnitMovementTypeEnum movementType =
				this.gameData.Units[(int)unit.UnitType].MovementType;
			bool destinationOccupied =
				map.F0_2aea_1458_GetCellActiveUnitID(
					destination.X,
					destination.Y) != -1;
			if (ClassicZoneOfControlPolicy.Applies(
					movementType,
					unit.UnitType,
					map.GetTerrainType(source),
					destinationOccupied) &&
				this.parent.UnitManagement
					.IsKnownEnemyZoneOfControlAt(
						unit.PlayerID,
						source) &&
				this.parent.UnitManagement
					.IsKnownEnemyZoneOfControlAt(
						unit.PlayerID,
						destination))
			{
				return double.MaxValue;
			}

			double dValue;
			if (movementType == UnitMovementTypeEnum.Land)
			{
				TerrainImprovementFlagsEnum sourceImprovements =
					map.F0_2aea_1585_GetVisibleTerrainImprovements(
						source.X,
						source.Y);
				TerrainImprovementFlagsEnum destinationImprovements =
					map.F0_2aea_1585_GetVisibleTerrainImprovements(
						destination.X,
						destination.Y);
				bool connectedByRoad =
					(sourceImprovements & destinationImprovements)
						.HasFlag(TerrainImprovementFlagsEnum.Road);
				dValue = connectedByRoad
					? 1.0 / 3.0
					: this.gameData.Terrains[
						(int)map.GetTerrainType(
							destination.X,
							destination.Y)].MovementCost;
			}
			else
			{
				// PlayerTurn charges one complete move for sea and air units,
				// independent of the terrain drawn below them.
				dValue = 1.0;
			}

			// Increase movement cost for nearby enemy units and cities

			if (this.parent.UnitManagement.IsEnemyCityNear(
					unit.PlayerID,
					destination.X,
					destination.Y,
					1))
			{
				// Entering one enemy control zone from outside it is legal.
				// Keep a routing penalty so safer equal-cost routes win; the
				// transition check above blocks only ZOC-to-ZOC movement.
				dValue += 2.0;
			}
			else
			{
				if (this.parent.UnitManagement.IsEnemyCityNear(
						unit.PlayerID,
						destination.X,
						destination.Y,
						2))
				{
					// this cell has enemy city near, increase cost to avoid it if possible
					dValue += 1.0;
				}

				if (this.parent.UnitManagement.IsEnemyUnitNear(
						unit.PlayerID,
						destination.X,
						destination.Y,
						2))
				{
					// this cell has enemy unit near, increase cost to avoid it if possible
					dValue += 1.0;
				}
			}

			return dValue;
		}

		private double GetOriginalVisibleGoToMovementCost(
			int playerID,
			GPoint destination)
		{
			MapManagement map = this.parent.MapManagement;
			TerrainDefinition terrain =
				this.gameData.Terrains[
					(int)map.GetTerrainType(
						destination.X,
						destination.Y)];
			TerrainImprovementFlagsEnum improvements =
				map.F0_2aea_1585_GetVisibleTerrainImprovements(
					destination.X,
					destination.Y);
			double movementCost = terrain.MovementCost;
			if (improvements.HasFlag(
					TerrainImprovementFlagsEnum.Road))
			{
				movementCost = 1.0 / 3.0;
			}

			if (improvements.HasFlag(
					TerrainImprovementFlagsEnum.RailRoad))
			{
				movementCost = 0.0;
			}

			if (this.parent.UnitManagement.IsEnemyCityNear(
					playerID,
					destination.X,
					destination.Y,
					1))
			{
				return double.MaxValue;
			}

			if (this.parent.UnitManagement.IsEnemyCityNear(
					playerID,
					destination.X,
					destination.Y,
					2))
			{
				movementCost += 1.0;
			}

			if (this.parent.UnitManagement.IsEnemyUnitNear(
					playerID,
					destination.X,
					destination.Y,
					2))
			{
				movementCost += 1.0;
			}

			return movementCost;
		}

		private class AStarCell
		{
			public GPoint Position = new GPoint(-1);
			public GPoint ParentPos = new GPoint(-1); // Position of our parent cell
			public double GCost = double.MaxValue;
			public double HCost = double.MaxValue;
			public double FCost = double.MaxValue; // FCost = GCost + HCost
			public bool IsCellClosed = false;

			public AStarCell(int x, int y)
			{
				this.Position = new GPoint(x, y);
			}
		}
		#endregion

		#region Old unfixable GoTo algorithm
		/// <summary>
		/// Checks if there is path from start to destination for a given unit
		/// </summary>
		/// <param name="x"></param>
		/// <param name="y"></param>
		/// <param name="x1"></param>
		/// <param name="y1"></param>
		/// <param name="waterUnit"></param>
		/// <param name="param6"></param>
		/// <returns></returns>
		public int F0_2e31_111c_CheckUnitPath(int x, int y, int x1, int y1, bool waterUnit, short param6)
		{
			//this.oParent.GoToLog.EnterBlock($"F0_2e31_111c({xPos}, {yPos}, {xPos1}, {yPos1}, {flag}, {param6})");

			// function body
			int result = -1;

			if (Math.Abs(x - x1) <= 7 && Math.Abs(y - y1) <= 7)
			{
				// Temporary unit...
				Unit unit = this.parent.GameData.Players[0].Units[127];

				unit.UnitType = (waterUnit ? UnitTypeEnum.Trireme : UnitTypeEnum.Militia);
				unit.Position = new(x, y);
				unit.GoToDestination = new(x1, y1);

				this.Var_6590_DestinationX = (short)x1;
				this.Var_6592_DestinationY = (short)y1;

				// Instruction address 0x2e31:0x117c, size: 3
				result = F0_2e31_0c1d_FindShortestPath(unit, param6);

				unit.UnitType = UnitTypeEnum.None;
				unit.Position = OpenCivOneGame.InvalidPosition;
				unit.GoToDestination = OpenCivOneGame.InvalidPosition;

				if (result != -1)
				{
					result = this.Var_6794;
				}
			}

			return result;
		}

		/// <summary>
		/// Gets next move unit should take on it's path
		/// </summary>
		/// <param name="playerID"></param>
		/// <param name="unitID"></param>
		/// <returns></returns>
		public int F0_2e31_000e_GetNextMove(int playerID, int unitID)
		{
			//this.oParent.GoToLog.EnterBlock($"F0_2e31_000e({playerID}, {unitID})");
			//OpenCivOneGame.LogUnit(this.oParent, this.oParent.GoToLog, playerID, unitID, this.oParent.GameData.HumanPlayerID);

			// function body
			Unit unit;

			if (playerID < 0 || playerID > 7 || unitID < 0 || unitID > 127 ||
				(unit = this.parent.GameData.Players[playerID].Units[unitID]).UnitType == UnitTypeEnum.None || unit.GoToDestination.X == -1)
			{
				return -1;
			}

			GPoint move = unit.GoToDestination - unit.Position;
			GPoint absMove = GPoint.Abs(move);

			if (playerID == this.parent.GameData.HumanPlayerID && absMove.X < 2 && absMove.Y < 2)
			{
				move = new((absMove.X >= 40) ? -Math.Sign(move.X) : Math.Sign(move.X), Math.Sign(move.Y));

				unit.GoToDestination = new GPoint(-1);

				for (int i = 1; i < 9; i++)
				{
					if (this.parent.MoveDirections[i] == move)
					{
						return i;
					}
				}

				return -1;
			}

			if (this.parent.GameData.Units[(int)unit.UnitType].MovementType == UnitMovementTypeEnum.Air)
			{
				this.Var_6590_DestinationX = unit.GoToDestination.X;
				this.Var_6592_DestinationY = unit.GoToDestination.Y;
			}
			else
			{
				bool local_e = false;

				if (absMove.Y > 6 || (absMove.X > 6 && absMove.X < 74))
				{
					this.Var_6590_DestinationX = unit.GoToDestination.X;
					this.Var_6592_DestinationY = unit.GoToDestination.Y;

					// Instruction address 0x2e31:0x01bf, size: 3
					int moveDirection = F0_2e31_0c1d_FindShortestPath(unit, 999);

					if (moveDirection != -1)
					{
						return moveDirection;
					}

					local_e = true;
				}

				// Instruction address 0x2e31:0x01df, size: 3
				if (F0_2e31_05e6(unit) || !local_e)
				{
					// Instruction address 0x2e31:0x01fa, size: 3
					int moveDirection = F0_2e31_0c1d_FindShortestPath(unit, 999);

					if (moveDirection != -1)
					{
						return moveDirection;
					}
				}
			}

			move = new(this.Var_6590_DestinationX - unit.Position.X, this.Var_6592_DestinationY - unit.Position.Y);
			absMove = GPoint.Abs(move);
			int vector = (absMove.X > absMove.Y) ? Math.Abs(move.X) : Math.Abs(move.Y) + absMove.X + absMove.Y;

			if (move.X == 0 && move.Y == 0)
			{
				unit.GoToDestination = OpenCivOneGame.InvalidPosition;
				unit.GoToNextDirection = -1;
				unit.RemainingMoves = 0;

				return -1;
			}
			else
			{
				// Instruction address 0x2e31:0x02c8, size: 5
				TerrainImprovementFlagsEnum terrainImprovements = this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(unit.Position.X, unit.Position.Y);

				// Instruction address 0x2e31:0x02e5, size: 5
				bool unitIsNear = this.parent.UnitManagement.F0_1866_1725_IsUnitNear(playerID, unit.Position.X, unit.Position.Y);
				int newDistance = 9999;
				int newMoveDirection = 0;

				for (int i = 1; i < 9; i++)
				{
					GPoint direction = this.parent.MoveDirections[i];
					int unitNewX = unit.Position.X + direction.X;
					int unitNewY = unit.Position.Y + direction.Y;
					absMove = new(Math.Abs(move.X - direction.X), Math.Abs(move.Y - direction.Y));
					int newVector = ((absMove.X <= absMove.Y) ? absMove.Y : absMove.X) + absMove.X + absMove.Y;

					if (playerID != this.parent.GameData.HumanPlayerID || newVector <= vector)
					{
						// Instruction address 0x2e31:0x03b7, size: 5
						TerrainTypeEnum newTerrainType = this.parent.MapManagement.GetTerrainType(unitNewX, unitNewY);

						// Instruction address 0x2e31:0x03c8, size: 5
						int cellOwner = this.parent.MapManagement.F0_2aea_14e0_GetCellActiveUnitPlayerID(unitNewX, unitNewY);

						if (((cellOwner == -1 || cellOwner == playerID) &&
							((((this.parent.GameData.Units[(int)unit.UnitType].MovementType == UnitMovementTypeEnum.Water) ? 1 : 0) == (newTerrainType == TerrainTypeEnum.Water ? 1 : 0) &&
								(!unitIsNear || !this.parent.UnitManagement.F0_1866_1725_IsUnitNear(playerID, unitNewX, unitNewY))) ||
								this.parent.GameData.Units[(int)unit.UnitType].MovementType == UnitMovementTypeEnum.Air)) ||
							(this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(unitNewX, unitNewY).HasFlag(TerrainImprovementFlagsEnum.City) &&
								this.parent.MapManagement.F0_2aea_1369_GetCityOwner(unitNewX, unitNewY) == playerID))
						{
							if (newTerrainType != TerrainTypeEnum.Water || this.parent.MapManagement.F0_2aea_195d_GetMapGroupSize(unitNewX, unitNewY) >= 5)
							{
								int movementCost;

								if (terrainImprovements.HasFlag(TerrainImprovementFlagsEnum.Road) &&
									this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(unitNewX, unitNewY).HasFlag(TerrainImprovementFlagsEnum.Road))
								{
									movementCost = 1;
								}
								else
								{
									movementCost = ((this.parent.GameData.Units[(int)unit.UnitType].MoveCount > 1) ? (this.parent.GameData.Terrains[(int)newTerrainType].MovementCost * 3) : 3);
								}

								movementCost += (newVector * 4) + absMove.X + absMove.Y;

								if (unit.GoToNextDirection != -1)
								{
									int movement = Math.Abs(unit.GoToNextDirection - i);

									if (movement > 4)
									{
										movement = 8 - movement;
									}

									movementCost += movement * movement;
								}

								if (movementCost < newDistance)
								{
									newMoveDirection = i;
									newDistance = movementCost;
								}
							}
						}
					}
				}

				if (unit.GoToNextDirection != -1)
				{
					if ((unit.GoToNextDirection ^ 0x4) == newMoveDirection)
					{
						unit.RemainingMoves = 0;

						newMoveDirection = 0;
					}
				}

				if (newMoveDirection == 0)
				{
					unit.GoToDestination = OpenCivOneGame.InvalidPosition;
					unit.GoToNextDirection = -1;

					return -1;
				}
				else
				{
					unit.GoToNextDirection = (short)newMoveDirection;

					return newMoveDirection;
				}
			}
		}

		/// <summary>
		/// Checks if there is a more favorable path available
		/// </summary>
		/// <param name="playerID"></param>
		/// <param name="unitID"></param>
		/// <returns></returns>
		private bool F0_2e31_05e6(Unit unit)
		{
			//this.oParent.GoToLog.EnterBlock($"F0_2e31_05e6({playerID}, {unitID})");
			//OpenCivOneGame.LogUnit(this.oParent, this.oParent.GoToLog, playerID, unitID, this.oParent.GameData.HumanPlayerID);

			// function body
			bool waterUnit = this.parent.GameData.Units[(int)unit.UnitType].MovementType == UnitMovementTypeEnum.Water;
			int local_a = 0;
			int unitX = unit.Position.X;
			int unitY = unit.Position.Y;
			this.Var_6590_DestinationX = unit.GoToDestination.X;
			this.Var_6592_DestinationY = unit.GoToDestination.Y;

			if (!F0_2e31_0a2c_CanUnitMove(unitX, unitY, waterUnit))
			{
				this.Var_6590_DestinationX = unit.GoToDestination.X;
				this.Var_6592_DestinationY = unit.GoToDestination.Y;

				return false;
			}

			unitX = this.Var_6590_DestinationX;
			unitY = this.Var_6592_DestinationY;

			// Instruction address 0x2e31:0x06a7, size: 3
			F0_2e31_0a2c_CanUnitMove(unit.GoToDestination.X, unit.GoToDestination.Y, waterUnit);

			// Instruction address 0x2e31:0x06b8, size: 5
			for (int i = 0; i < this.Arr_d816.GetLength(0); i++)
			{
				for (int j = 0; j < this.Arr_d816.GetLength(1); j++)
				{
					this.Arr_d816[i, j] = 0;
				}
			}

			int pathCount1 = 0;
			int pathCount2 = 0;

			this.Arr_6594_PathX[pathCount1] = this.Var_6590_DestinationX;
			this.Arr_6694_PathY[pathCount1] = this.Var_6592_DestinationY;

			pathCount1++;

			this.Arr_d816[this.Var_6590_DestinationX, this.Var_6592_DestinationY] = 1;

			bool oldPath = false;

			do
			{
				int prevPathX = this.Arr_6594_PathX[pathCount2];
				int prevPathY = this.Arr_6694_PathY[pathCount2];

				if (prevPathX != unitX || prevPathY != unitY)
				{
					int pathFlags;

					local_a = this.Arr_d816[prevPathX, prevPathY];

					pathCount2++;
					pathCount2 &= 0xff;

					if (waterUnit)
					{
						pathFlags = this.Arr_7f38_WaterPath[prevPathX, prevPathY];
					}
					else
					{
						pathFlags = this.Arr_db44_LandPath[prevPathX, prevPathY];
					}

					for (int i = 1; i < 9; i++)
					{
						if ((pathFlags & (0x1 << (i - 1))) != 0)
						{
							GPoint direction = this.parent.MoveDirections[i];

							int newX = prevPathX + direction.X;

							if (newX == 20)
							{
								newX = 0;
							}

							if (newX == -1)
							{
								newX = 19;
							}

							int newY = prevPathY + direction.Y;

							if (this.Arr_d816[newX, newY] == 0)
							{
								this.Arr_d816[newX, newY] = local_a + 1;
								this.Arr_6594_PathX[pathCount1] = newX;
								this.Arr_6694_PathY[pathCount1] = newY;

								pathCount1++;
								pathCount1 &= 0xff;
							}
						}
					}
				}
				else
				{
					oldPath = true;
				}
			}
			while (!oldPath && pathCount2 != pathCount1);

			this.Var_6590_DestinationX = -1;

			if (oldPath)
			{
				int local_6 = 0;
				int local_8 = 99;
				int newDirection = -1;
				int pathFlags;

				if (this.parent.GameData.Units[(int)unit.UnitType].MovementType == UnitMovementTypeEnum.Water)
				{
					pathFlags = this.Arr_7f38_WaterPath[unitX, unitY];
				}
				else
				{
					pathFlags = this.Arr_db44_LandPath[unitX, unitY];
				}

				for (int i = 1; i < 9; i++)
				{
					if ((pathFlags & (0x1 << (i - 1))) != 0)
					{
						GPoint direction = this.parent.MoveDirections[i];
						int newX = unitX + direction.X;
						int newY = unitY + direction.Y;

						if (newX == 20)
						{
							newX = 0;
						}

						if (newX == -1)
						{
							newX = 19;
						}

						local_6 = this.Arr_d816[newX, newY];

						if (local_6 != 0)
						{
							if (local_6 < local_8)
							{
								local_8 = local_6;
								newDirection = i;

								// Instruction address 0x2e31:0x0976, size: 5
								local_a = this.parent.Tools.F0_2dc4_0289_GetShortestDistance(unit.GoToDestination.X, unit.GoToDestination.Y,
									newX * 4 + 1, newY * 4 + 1);
							}
							else if (local_6 == local_8)
							{
								// Instruction address 0x2e31:0x08b0, size: 5
								int local_12 = this.parent.Tools.F0_2dc4_0289_GetShortestDistance(unit.GoToDestination.X, unit.GoToDestination.Y,
									newX * 4 + 1, newY * 4 + 1);

								if (local_12 < local_a)
								{
									newDirection = i;
									local_a = local_12;
								}
							}
						}
					}
				}

				if (newDirection != -1)
				{
					GPoint direction = this.parent.MoveDirections[newDirection];

					// Instruction address 0x2e31:0x099d, size: 3
					this.Var_6590_DestinationX = this.parent.MapManagement.AdjustXPosition(((unitX + direction.X) * 4) + 1);
					this.Var_6592_DestinationY = ((unitY + direction.Y) * 4) + 1;

					if ((this.parent.MapManagement.GetTerrainType(this.Var_6590_DestinationX, this.Var_6592_DestinationY) == TerrainTypeEnum.Water) != waterUnit)
					{
						this.Var_6590_DestinationX++;

						if ((this.parent.MapManagement.GetTerrainType(this.Var_6590_DestinationX, this.Var_6592_DestinationY) == TerrainTypeEnum.Water) != waterUnit)
						{
							this.Var_6592_DestinationY++;
						}
					}
				}
			}

			if (this.Var_6590_DestinationX == -1)
			{
				this.Var_6590_DestinationX = unit.GoToDestination.X;
				this.Var_6592_DestinationY = unit.GoToDestination.Y;
			}

			return oldPath;
		}

		/// <summary>
		/// Tests if unit can move in any direction
		/// </summary>
		/// <param name="x"></param>
		/// <param name="y"></param>
		/// <param name="waterUnit"></param>
		/// <returns>true if unit can move in any direction</returns>
		private bool F0_2e31_0a2c_CanUnitMove(int x, int y, bool waterUnit)
		{
			//this.oParent.GoToLog.EnterBlock($"F0_2e31_0a2c({x}, {y}, {waterFlag})");

			// function body
			int newMoveDirection = -1;
			int shortX = x / 4;
			int shortY = y / 4;

			if (waterUnit)
			{
				if (this.Arr_7f38_WaterPath[shortX, shortY] != 0)
				{
					newMoveDirection = 0;
				}
			}
			else if (this.Arr_db44_LandPath[shortX, shortY] != 0)
			{
				newMoveDirection = 0;
			}

			if (newMoveDirection == -1)
			{
				int minDistance = 99;

				for (int i = 1; i < 9; i++)
				{
					GPoint direction = this.parent.MoveDirections[i];

					int newShortX = shortX + direction.X;
					int newShortY = shortY + direction.Y;

					if ((waterUnit && this.Arr_7f38_WaterPath[newShortX, newShortY] != 0) ||
						(!waterUnit && this.Arr_db44_LandPath[newShortX, newShortY] != 0))
					{
						// Instruction address 0x2e31:0x0b43, size: 5
						int distance = this.parent.Tools.F0_2dc4_0289_GetShortestDistance(x - (newShortX * 4) - 1, y - (newShortY * 4) - 1);

						if (distance < minDistance)
						{
							int testShortX = newShortX + 1;
							int testShortY = newShortY + 1;

							if ((this.parent.MapManagement.GetTerrainType(testShortX, testShortY) == TerrainTypeEnum.Water) == waterUnit)
							{
								if (F0_2e31_111c_CheckUnitPath(testShortX, testShortY, x, y, waterUnit, 18) != -1)
								{
									minDistance = distance;
									newMoveDirection = i;
								}
							}
							else
							{
								testShortX++;

								if ((this.parent.MapManagement.GetTerrainType(testShortX, testShortY) == TerrainTypeEnum.Water) == waterUnit)
								{
									if (F0_2e31_111c_CheckUnitPath(testShortX, testShortY, x, y, waterUnit, 18) != -1)
									{
										minDistance = distance;
										newMoveDirection = i;
									}
								}
								else
								{
									testShortY++;

									if ((this.parent.MapManagement.GetTerrainType(testShortX, testShortY) == TerrainTypeEnum.Water) == waterUnit)
									{
										if (F0_2e31_111c_CheckUnitPath(testShortX, testShortY, x, y, waterUnit, 18) != -1)
										{
											minDistance = distance;
											newMoveDirection = i;
										}
									}
									else
									{
										testShortX--;

										if ((this.parent.MapManagement.GetTerrainType(testShortX, testShortY) == TerrainTypeEnum.Water) == waterUnit)
										{
											if (F0_2e31_111c_CheckUnitPath(testShortX, testShortY, x, y, waterUnit, 18) != -1)
											{
												minDistance = distance;
												newMoveDirection = i;
											}
										}
									}
								}
							}
						}
					}
				}
			}

			if (newMoveDirection != -1)
			{
				GPoint direction = this.parent.MoveDirections[newMoveDirection];

				this.Var_6590_DestinationX = (shortX * 4) + direction.X;
				this.Var_6592_DestinationY = (shortY * 4) + direction.Y;

				return true;
			}

			return false;
		}

		/// <summary>
		/// Finds the shortest path from start to destination
		/// </summary>
		/// <param name="playerID"></param>
		/// <param name="unitID"></param>
		/// <param name="param3"></param>
		/// <returns></returns>
		private int F0_2e31_0c1d_FindShortestPath(Unit unit, short param3)
		{
			//this.oParent.GoToLog.EnterBlock($"F0_2e31_0c1d({playerID}, {unitID}, {param3})");
			//OpenCivOneGame.LogUnit(this.oParent, this.oParent.GoToLog, playerID, unitID, this.oParent.GameData.HumanPlayerID);

			// function body
			bool waterUnit = this.parent.GameData.Units[(int)unit.UnitType].MovementType == UnitMovementTypeEnum.Water;
			int local_20 = this.Var_6590_DestinationX - 8;
			int local_3a = this.Var_6592_DestinationY - 8;
			int unitX = unit.Position.X;
			int unitY = unit.Position.Y;
			GPoint direction;

			this.Var_6794 = 0;

			if (this.Var_6590_DestinationX != this.Var_6796_LastDestinationX || this.Var_6592_DestinationY != this.Var_6798_LastDestinationY ||
				this.Arr_b780[unitX - local_20, unitY - local_3a] == 0)
			{
				this.Var_6796_LastDestinationX = this.Var_6590_DestinationX;
				this.Var_6798_LastDestinationY = this.Var_6592_DestinationY;

				for (int i = 0; i < this.Arr_b780.GetLength(0); i++)
				{
					for (int j = 0; j < this.Arr_b780.GetLength(1); j++)
					{
						this.Arr_b780[i, j] = 0;
					}
				}

				int local_2 = 0;

				this.Arr_6594_PathX[local_2] = this.Var_6590_DestinationX;
				this.Arr_6694_PathY[local_2] = this.Var_6592_DestinationY;

				local_2++;

				this.Arr_b780[this.Var_6590_DestinationX - local_20, this.Var_6592_DestinationY - local_3a] = 1;
				this.Var_6794 = param3;
				int oneMove = (this.parent.GameData.Units[(int)unit.UnitType].MoveCount == 1) ? 1 : 0;

				// local_2 will always be 1, so local_4 loop will also end at 1
				for (int local_4 = 0; local_4 != local_2 && local_4 < 225;)
				{
					int oldX = this.Arr_6594_PathX[local_4];
					int oldY = this.Arr_6694_PathY[local_4];

					local_4++;
					local_4 &= 0xff;

					int local_e = this.Arr_b780[oldX - local_20, oldY - local_3a];

					if (local_e <= this.Var_6794)
					{
						if (this.parent.MapManagement.AdjustXPosition(oldX) != unitX || oldY != unitY)
						{
							for (int i = 1; i < 9; i++)
							{
								direction = this.parent.MoveDirections[i];

								int newX = oldX + direction.X;

								if (Math.Abs(newX - this.Var_6590_DestinationX) < 8)
								{
									int newXAdjusted = this.parent.MapManagement.AdjustXPosition(newX);
									int newY = oldY + direction.Y;
									TerrainTypeEnum local_3e = this.parent.MapManagement.GetTerrainType(newXAdjusted, newY);

									if (Math.Abs(newY - this.Var_6592_DestinationY) < 8 &&
										this.parent.MapManagement.ValidateMapCoordinates(newXAdjusted, newY) &&
										((local_3e == TerrainTypeEnum.Water) == waterUnit ||
										this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(newXAdjusted, newY).HasFlag(TerrainImprovementFlagsEnum.City)))
									{
										int local_1a;

										if (this.parent.MapManagement.F0_2aea_1570_CheckIfCellHasRoad(this.parent.MapManagement.AdjustXPosition(oldX), oldY) &&
											this.parent.MapManagement.F0_2aea_1570_CheckIfCellHasRoad(newXAdjusted, newY))
										{
											local_1a = local_e + 1;
										}
										else if (oneMove != 0)
										{
											local_1a = local_e + 3;
										}
										else
										{
											local_1a = (3 * this.parent.GameData.Terrains[(int)local_3e].MovementCost) + local_e;
										}

										int local_38 = this.Arr_b780[newX - local_20, newY - local_3a];

										if (local_38 == 0 || local_38 > local_1a)
										{
											this.Arr_b780[newX - local_20, newY - local_3a] = local_1a;

											this.Arr_6594_PathX[local_2] = newX;
											this.Arr_6694_PathY[local_2] = newY;

											local_2++;
											local_2 &= 0xff;
										}
									}
								}
							}
						}
						else
						{
							this.Var_6794 = local_e;
						}
					}
				}
			}

			int nextMoveDirection = -1;

			if (param3 > this.Var_6794)
			{
				int local_a = 99;

				for (int i = 1; i < 9; i++)
				{
					direction = this.parent.MoveDirections[i];

					int newX = unitX + direction.X;

					if (Math.Abs(newX - this.Var_6590_DestinationX) >= 72)
					{
						if (newX <= this.Var_6590_DestinationX)
						{
							newX += 80;
						}
						else
						{
							newX -= 80;
						}
					}

					if (Math.Abs(newX - this.Var_6590_DestinationX) < 8)
					{
						int newXAdjusted = this.parent.MapManagement.AdjustXPosition(newX);
						int newY = unitY + direction.Y;

						if (Math.Abs(newY - this.Var_6592_DestinationY) < 8)
						{
							if ((this.parent.MapManagement.GetTerrainType(newXAdjusted, newY) == TerrainTypeEnum.Water) == waterUnit ||
								this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(newXAdjusted, newY).HasFlag(TerrainImprovementFlagsEnum.City))
							{
								int local_6 = this.Arr_b780[newX - local_20, newY - local_3a];

								if (local_6 != 0)
								{
									int local_e = 0;

									if (local_6 < local_a)
									{
										local_a = local_6;
										nextMoveDirection = i;

										// Instruction address 0x2e31:0x1025, size: 5
										int activeUnitID = this.parent.MapManagement.F0_2aea_1458_GetCellActiveUnitID(newXAdjusted, newY);

										if (activeUnitID != -1)
										{
											// Instruction address 0x2e31:0x103f, size: 5
											local_e = (short)this.parent.UnitManagement.F0_1866_1251_GetStackUnitValueSum(unit.PlayerID, activeUnitID, UnitStackValueTypeEnum.UnitCount) * 4;
										}
										else
										{
											local_e = 0;
										}

										// Instruction address 0x2e31:0x1063, size: 5
										local_e += this.parent.Tools.F0_2dc4_0289_GetShortestDistance(this.Var_6590_DestinationX, this.Var_6592_DestinationY, newXAdjusted, newY);
									}

									if (local_6 == local_a)
									{
										int local_1a;

										// Instruction address 0x2e31:0x107f, size: 5
										int activeUnitID = this.parent.MapManagement.F0_2aea_1458_GetCellActiveUnitID(newXAdjusted, newY);

										if (activeUnitID != -1)
										{
											// Instruction address 0x2e31:0x1099, size: 5
											local_1a = (short)this.parent.UnitManagement.F0_1866_1251_GetStackUnitValueSum(unit.PlayerID, activeUnitID, UnitStackValueTypeEnum.UnitCount) * 4;
										}
										else
										{
											local_1a = 0;
										}

										// Instruction address 0x2e31:0x10bd, size: 5
										local_1a += this.parent.Tools.F0_2dc4_0289_GetShortestDistance(this.Var_6590_DestinationX, this.Var_6592_DestinationY, newXAdjusted, newY);

										if (local_1a < local_e)
										{
											nextMoveDirection = i;
											local_e = local_1a;
										}
									}
								}
							}
						}
					}
				}

				if (nextMoveDirection != -1)
				{
					return nextMoveDirection;
				}
			}

			if (nextMoveDirection == -1)
			{
				this.Var_6590_DestinationX = unit.GoToDestination.X;
				this.Var_6592_DestinationY = unit.GoToDestination.Y;
			}

			return -1;
		}
		#endregion
	}
}
