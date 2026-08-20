using OpenCivOne.Graphics;
using OpenCivOne.Runtime;

namespace OpenCivOne
{
	/// <summary>
	/// Builds a conservative, side-effect-free support projection from the
	/// current human state and applies only the HomeCityID changes accepted by
	/// <see cref="ClassicHomeCityReassignmentPlanner"/>.
	/// </summary>
	public static class ClassicHomeCityReassignmentRuntime
	{
		public static ClassicHomeCityReassignmentPlan TryApply(
			OpenCivOneGame game,
			int playerID)
		{
			ArgumentNullException.ThrowIfNull(game);

			if (!ClassicAiRuntimeProfiles.UsesSmartEnhancements(
					game.GameData.AiProfile) ||
				!game.GameData.GameSettingFlags
				.AutomaticHomeCityReassignment)
			{
				return EmptyPlan(
					ClassicHomeCityReassignmentDecision.Disabled);
			}

			if (playerID != game.GameData.HumanPlayerID)
			{
				return EmptyPlan(
					ClassicHomeCityReassignmentDecision.NotHumanPlayer);
			}

			ClassicHomeCityReassignmentSnapshot snapshot =
				BuildSnapshot(game, playerID);
			ClassicHomeCityReassignmentPlan plan =
				ClassicHomeCityReassignmentPlanner.Plan(snapshot);
			Player player = game.GameData.Players[playerID];

			foreach (ClassicHomeCityReassignment reassignment in
				plan.Reassignments)
			{
				if (reassignment.UnitID < 0 ||
					reassignment.UnitID >= player.Units.Length)
				{
					continue;
				}

				Unit unit = player.Units[reassignment.UnitID];

				if (unit.UnitType == UnitTypeEnum.None ||
					unit.HomeCityID != reassignment.PreviousHomeCityID)
				{
					continue;
				}

				unit.HomeCityID = (short)reassignment.NewHomeCityID;
			}

			return plan;
		}

		internal static ClassicHomeCityReassignmentSnapshot BuildSnapshot(
			OpenCivOneGame game,
			int playerID)
		{
			GameData gameData = game.GameData;
			Player player = gameData.Players[playerID];
			int governmentType = player.GovernmentType;
			int settlerFoodCost = governmentType <= 1 ? 1 : 2;
			List<City> activeCities = gameData.Cities
				.Where(city =>
					city.StatusFlag != 0xff &&
					city.PlayerID == playerID)
				.OrderBy(city => city.ID)
				.ToList();
			List<ClassicHomeCitySupportSnapshot> citySnapshots = [];
			List<ClassicHomeCitySupportFailureSnapshot> failures = [];

			foreach (City city in activeCities)
			{
				int internalDefenderCount =
					city.Unknown.Count(unitID => unitID != -1);
				int supportedUnitCount = player.Units.Count(unit =>
					unit.UnitType != UnitTypeEnum.None &&
					unit.HomeCityID == city.ID &&
					IsShieldSupportedUnit(unit.UnitType));
				int settlerCount = player.Units.Count(unit =>
					unit.UnitType == UnitTypeEnum.Settler &&
					unit.HomeCityID == city.ID);
				List<int> foodLossSettlerIDs = [];
				if (city.FoodCount < 0)
				{
					for (int unitID = 0;
						unitID < player.Units.Length;
						unitID++)
					{
						Unit unit = player.Units[unitID];
						if (unit.UnitType == UnitTypeEnum.Settler &&
							unit.HomeCityID == city.ID)
						{
							foodLossSettlerIDs.Add(unitID);
						}
					}
				}
				bool hasCompleteNeighborhood =
					HasCompleteCityNeighborhood(game, city);
				int currentSize = Math.Max(
					0,
					(int)city.ActualSize);
				bool pendingFamine = city.FoodCount < 0;
				int minimumSize = pendingFamine
					? Math.Max(0, currentSize - 1)
					: currentSize;
				int maximumSize = currentSize;

				if (!pendingFamine &&
					city.FoodCount >=
						((currentSize + 1) * 10) &&
					(currentSize < 10 ||
						city.HasImprovement(
							ImprovementEnum.Aqueduct) ||
						(gameData.DebugFlags & 0x4) == 0))
				{
					maximumSize++;
				}

				int maximumGrossProduction =
					hasCompleteNeighborhood
						? CalculateMaximumGrossProduction(
							game,
							playerID,
							city,
							maximumSize)
						: 0;

				if (CouldCompletePopulationSettler(
					gameData,
					player,
					city,
					maximumGrossProduction))
				{
					minimumSize = Math.Max(
						0,
						minimumSize - 1);
				}

				int minimumPossibleSupport =
					CalculateShieldSupport(
						gameData,
						governmentType,
						maximumSize,
						internalDefenderCount,
						supportedUnitCount);
				int maximumPossibleSupport =
					CalculateShieldSupport(
						gameData,
						governmentType,
						minimumSize,
						internalDefenderCount,
						supportedUnitCount);
				int minimumGrossProduction =
					hasCompleteNeighborhood
						? ApplyProductionModifiers(
							game,
							playerID,
							city,
							GetCellResource(
								game,
								playerID,
								city,
								offsetIndex: 20,
								CityResourceTypeEnum.Production))
						: 0;
				int minimumGrossFood =
					hasCompleteNeighborhood
						? CalculateCurrentlyWorkedGrossFood(
							game,
							playerID,
							city,
							minimumSize)
						: 0;
				int freeSlots =
					UsesPerUnitShieldSupport(
						gameData,
						governmentType)
						? 0
						: Math.Max(
							0,
							minimumSize -
								internalDefenderCount -
								supportedUnitCount);
				int shieldHeadroom = Math.Max(
					0,
					minimumGrossProduction -
						maximumPossibleSupport);
				int foodSurplus =
					minimumGrossFood -
					(minimumSize * 2) -
					(settlerCount * settlerFoodCost);
				bool canReceiveReassignment =
					hasCompleteNeighborhood &&
					!pendingFamine &&
					minimumSize > 0;

				citySnapshots.Add(
					new ClassicHomeCitySupportSnapshot(
						city.ID,
						playerID,
						canReceiveReassignment,
						freeSlots,
						shieldHeadroom,
						foodSurplus,
						UnrestHeadroom: 0));

				if (pendingFamine)
				{
					foreach (int foodLossSettlerID in
						foodLossSettlerIDs)
					{
						failures.Add(
							new ClassicHomeCitySupportFailureSnapshot(
								city.ID,
								RequiredDisbandCount: 1,
								RequiredUnitID: foodLossSettlerID));
					}

					continue;
				}

				if (!hasCompleteNeighborhood)
				{
					continue;
				}

				int requiredDisbandCount = Math.Max(
					0,
					minimumPossibleSupport -
						maximumGrossProduction);

				if (requiredDisbandCount > 0)
				{
					failures.Add(
						new ClassicHomeCitySupportFailureSnapshot(
							city.ID,
							requiredDisbandCount));
				}
			}

			List<ClassicHomeCityUnitSnapshot> unitSnapshots = [];
			List<ClassicHomeCityRelationSnapshot> relations = [];

			for (int unitID = 0;
				unitID < player.Units.Length;
				unitID++)
			{
				Unit unit = player.Units[unitID];

				if (unit.UnitType == UnitTypeEnum.None)
				{
					continue;
				}

				int originalDistance = 0;
				City? homeCity = activeCities.FirstOrDefault(
					city => city.ID == unit.HomeCityID);

				if (homeCity is not null)
				{
					originalDistance =
						game.Tools.F0_2dc4_0289_GetShortestDistance(
							homeCity.Position.X,
							homeCity.Position.Y,
							unit.Position.X,
							unit.Position.Y);
				}

				UnitDefinition definition =
					gameData.Units[(int)unit.UnitType];
				unitSnapshots.Add(
					new ClassicHomeCityUnitSnapshot(
						unitID,
						playerID,
						unit.HomeCityID,
						unit.UnitType,
						definition.MovementType,
						definition.AttackStrength,
						originalDistance));

				foreach (City city in activeCities)
				{
					relations.Add(
						new ClassicHomeCityRelationSnapshot(
							unitID,
							city.ID,
							game.Tools
								.F0_2dc4_0289_GetShortestDistance(
									city.Position.X,
									city.Position.Y,
									unit.Position.X,
									unit.Position.Y),
							unit.Position.X == city.Position.X &&
								unit.Position.Y == city.Position.Y));
				}
			}

			return new ClassicHomeCityReassignmentSnapshot(
				playerID,
				gameData.HumanPlayerID,
				governmentType,
				game.CityWorker.F0_1d12_6c97_PlayerHasWonder(
					playerID,
					WonderEnum.WomensSuffrage),
				citySnapshots,
				unitSnapshots,
				relations,
				failures);
		}

		private static int CalculateShieldSupport(
			GameData gameData,
			int governmentType,
			int citySize,
			int internalDefenderCount,
			int supportedUnitCount)
		{
			int internalDefenderSupport = Math.Max(
				0,
				internalDefenderCount - citySize);

			if (UsesPerUnitShieldSupport(
				gameData,
				governmentType))
			{
				return internalDefenderSupport + supportedUnitCount;
			}

			return Math.Max(
				0,
				internalDefenderCount +
					supportedUnitCount -
					citySize);
		}

		private static bool UsesPerUnitShieldSupport(
			GameData gameData,
			int governmentType)
		{
			return governmentType > 1 &&
				(gameData.DebugFlags & 0x2) != 0;
		}

		private static int CalculateMaximumGrossProduction(
			OpenCivOneGame game,
			int playerID,
			City city,
			int maximumSize)
		{
			int baseProduction = GetCellResource(
				game,
				playerID,
				city,
				offsetIndex: 20,
				CityResourceTypeEnum.Production);
			IEnumerable<int> bestPossibleCitizenProduction =
				Enumerable.Range(0, 20)
					.Select(offsetIndex =>
						GetCellResource(
							game,
							playerID,
							city,
							offsetIndex,
							CityResourceTypeEnum.Production))
					.OrderByDescending(value => value)
					// Civ1 works the city centre in addition to one
					// outer cell for each population point.
					.Take(Math.Max(0, maximumSize));

			baseProduction +=
				bestPossibleCitizenProduction.Sum();

			return ApplyProductionModifiers(
				game,
				playerID,
				city,
				baseProduction);
		}

		private static int CalculateCurrentlyWorkedGrossFood(
			OpenCivOneGame game,
			int playerID,
			City city,
			int maximumWorkedCitizens)
		{
			int grossFood = GetCellResource(
				game,
				playerID,
				city,
				offsetIndex: 20,
				CityResourceTypeEnum.Food);
			List<int> workedFood = [];

			for (int offsetIndex = 0;
				offsetIndex < 20;
				offsetIndex++)
			{
				if ((city.WorkerFlags & (1u << offsetIndex)) == 0)
				{
					continue;
				}

				workedFood.Add(
					GetCellResource(
						game,
						playerID,
						city,
						offsetIndex,
						CityResourceTypeEnum.Food));
			}

			// If this city can finish a Settler in the same phase, its
			// population (and therefore one worked outer cell) can fall
			// before support is charged. Keep the lowest current yields when
			// projecting that conservative lower bound.
			return grossFood +
				workedFood
					.OrderBy(value => value)
					.Take(Math.Max(0, maximumWorkedCitizens))
					.Sum();
		}

		private static bool CouldCompletePopulationSettler(
			GameData gameData,
			Player player,
			City city,
			int maximumGrossProduction)
		{
			if (city.CurrentProductionID !=
					(int)UnitTypeEnum.Settler ||
				(city.ActualSize <= 1 &&
					player.CityCount <= 1))
			{
				return false;
			}

			int settlerCost =
				gameData.Units[(int)UnitTypeEnum.Settler].Cost *
				10;

			return city.ShieldsCount +
				maximumGrossProduction >=
				settlerCost;
		}

		private static int GetCellResource(
			OpenCivOneGame game,
			int playerID,
			City city,
			int offsetIndex,
			CityResourceTypeEnum resourceType)
		{
			GPoint offset = game.CityOffsets[offsetIndex];
			int x = city.Position.X + offset.X;
			int y = city.Position.Y + offset.Y;

			if (!IsUsableTerrainCell(game, x, y))
			{
				return 0;
			}

			return game.CityWorker.F0_1d12_6abc_GetCityResourceCount(
				playerID,
				city.ID,
				x,
				y,
				resourceType);
		}

		private static bool HasCompleteCityNeighborhood(
			OpenCivOneGame game,
			City city)
		{
			return game.CityOffsets.All(offset =>
				IsUsableTerrainCell(
					game,
					city.Position.X + offset.X,
					city.Position.Y + offset.Y));
		}

		private static bool IsUsableTerrainCell(
			OpenCivOneGame game,
			int x,
			int y)
		{
			if (!game.MapManagement.ValidateMapCoordinates(x, y))
			{
				return false;
			}

			int terrainIndex =
				(int)game.MapManagement.GetTerrainType(x, y);

			if (terrainIndex < (int)TerrainTypeEnum.Desert ||
				terrainIndex > (int)TerrainTypeEnum.River)
			{
				return false;
			}

			if (game.MapManagement
				.F0_2aea_1836_CellHasSpecialResource(x, y))
			{
				terrainIndex += 12;
			}

			return terrainIndex >= 0 &&
				terrainIndex < game.GameData.Terrains.Length;
		}

		private static int ApplyProductionModifiers(
			OpenCivOneGame game,
			int playerID,
			City city,
			int baseProduction)
		{
			int factoryFactor = 0;

			if (city.HasImprovement(ImprovementEnum.Factory))
			{
				factoryFactor = 2;
			}

			if (city.HasImprovement(
				ImprovementEnum.ManufacturingPlant))
			{
				factoryFactor = 4;
			}

			int powerFactor =
				city.HasImprovement(ImprovementEnum.PowerPlant) ||
				city.HasImprovement(ImprovementEnum.HydroPlant) ||
				city.HasImprovement(ImprovementEnum.NuclearPlant)
					? 2
					: 0;

			if (game.CityWorker.F0_1d12_6c97_PlayerHasWonder(
				playerID,
				WonderEnum.HooverDam))
			{
				int wonderCityID =
					game.GameData.WonderCityID[(int)WonderEnum.HooverDam];

				if (wonderCityID >= 0 &&
					wonderCityID < game.GameData.Cities.Length)
				{
					City wonderCity =
						game.GameData.Cities[wonderCityID];
					if (game.MapManagement
							.F0_2aea_1942_GetGroupID(
								city.Position.X,
								city.Position.Y) ==
						game.MapManagement
							.F0_2aea_1942_GetGroupID(
								wonderCity.Position.X,
								wonderCity.Position.Y))
					{
						powerFactor = 2;
					}
				}
			}

			powerFactor = Math.Clamp(
				powerFactor,
				0,
				factoryFactor);

			return baseProduction +
				((factoryFactor * baseProduction) / 4) +
				((powerFactor * baseProduction) / 4);
		}

		private static bool IsShieldSupportedUnit(
			UnitTypeEnum unitType)
		{
			return unitType != UnitTypeEnum.None &&
				unitType != UnitTypeEnum.Diplomat &&
				unitType != UnitTypeEnum.Caravan;
		}

		private static ClassicHomeCityReassignmentPlan EmptyPlan(
			ClassicHomeCityReassignmentDecision decision)
		{
			return new ClassicHomeCityReassignmentPlan(
				decision,
				Array.Empty<ClassicHomeCityReassignment>(),
				Array.Empty<int>(),
				0);
		}
	}
}
