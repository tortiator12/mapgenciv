using OpenCivOne.Graphics;
using OpenCivOne.Runtime;

namespace OpenCivOne;

/// <summary>
/// Direction of the city's current food-storage trend.
/// </summary>
public enum ClassicPopulationTrend
{
	Stable,
	Growth,
	Famine
}

/// <summary>
/// Exact values already calculated by the Classic city processor.
/// Keeping this record separate makes the timing rules independently testable.
/// </summary>
public readonly record struct ClassicProcessedCityValues(
	int FoodStored,
	int FoodStorageTarget,
	int ShieldsStored,
	int ProductionCost,
	int NetFood,
	int NetProduction,
	int NetTrade,
	bool IsInDisorder,
	int HappinessBalance);

/// <summary>
/// Display-only city forecast. It never mutates the game state.
/// </summary>
public readonly record struct ClassicCityIntelligenceSnapshot(
	int NetFood,
	int NetProduction,
	int NetTrade,
	ClassicPopulationTrend PopulationTrend,
	int? PopulationTurns,
	int? ProductionTurns,
	bool ProductionStalled,
	bool WillStarveNextTurn,
	bool WillEnterDisorderNextTurn,
	bool IsInDisorder,
	int NextTurnShieldOverflow);

/// <summary>
/// Display-only player economy and research forecast.
/// </summary>
public readonly record struct ClassicPlayerIntelligenceSnapshot(
	int NetGoldPerTurn,
	int SciencePerTurn,
	int? ResearchTurns);

/// <summary>
/// Exact, read-only forecasts derived from the same processed values that the
/// Classic runtime applies at turn end. The UI gates this helper to 1991+.
/// </summary>
public static class ClassicCityIntelligence
{
	public static bool IsAvailable(ClassicAiProfile profile) =>
		ClassicAiRuntimeProfiles.UsesSmartEnhancements(profile);

	public static ClassicCityIntelligenceSnapshot Calculate(
		ClassicProcessedCityValues values)
	{
		int? productionTurns = GetProductionTurns(values);
		bool productionStalled =
			values.ProductionCost > 0 &&
			!productionTurns.HasValue;
		int nextTurnShieldOverflow =
			values.ProductionCost <= 0
				? 0
				: ToNonNegativeInt(
					(long)values.ShieldsStored +
						values.NetProduction -
						values.ProductionCost);

		ClassicPopulationTrend populationTrend =
			ClassicPopulationTrend.Stable;
		int? populationTurns = null;
		if (values.NetFood > 0)
		{
			populationTrend = ClassicPopulationTrend.Growth;
			populationTurns = values.FoodStored >=
				values.FoodStorageTarget
					? 1
					: AddOneRound(
						CeilingTurnsOrNull(
							values.FoodStorageTarget -
								values.FoodStored,
							values.NetFood));
		}
		else if (values.NetFood < 0)
		{
			populationTrend = ClassicPopulationTrend.Famine;
			populationTurns =
				values.FoodStored < 0
					? 1
					: ToPositiveInt(
						((long)values.FoodStored /
							-(long)values.NetFood) + 2);
		}

		return new ClassicCityIntelligenceSnapshot(
			values.NetFood,
			values.NetProduction,
			values.NetTrade,
			populationTrend,
			populationTurns,
			productionTurns,
			productionStalled,
			values.FoodStored < 0,
			!values.IsInDisorder &&
				values.HappinessBalance < 0,
			values.IsInDisorder,
			nextTurnShieldOverflow);
	}

	/// <summary>
	/// Captures the global results of the immediately preceding
	/// ProcessCityState call.
	/// </summary>
	public static ClassicCityIntelligenceSnapshot CaptureProcessed(
		OpenCivOneGame game,
		int cityID)
	{
		ArgumentNullException.ThrowIfNull(game);
		ValidateCity(game, cityID);

		City city = game.GameData.Cities[cityID];
		Player owner =
			game.GameData.Players[city.PlayerID];
		int settlerFoodSupport =
			owner.GovernmentType <= 1 ? 1 : 2;
		int storageFactor =
			city.PlayerID == game.GameData.HumanPlayerID
				? 10
				: 16 -
					(game.GameData.DifficultyLevel * 2);
		if (city.PlayerID != game.GameData.HumanPlayerID &&
			game.GameData.Year >= 0 &&
			game.GameData.Players[
				game.GameData.HumanPlayerID].Ranking == 7 &&
			game.GameData.DifficultyLevel > 1)
		{
			storageFactor -= 2;
		}

		int productionCost =
			city.CurrentProductionID >= 0
				? game.GameData.Units[
					city.CurrentProductionID].Cost *
					storageFactor
				: game.GameData.GetImprovementType(
					-city.CurrentProductionID).Cost *
					storageFactor;
		bool isInDisorder =
			(city.StatusFlag & 0x1) != 0;
		int netProduction = isInDisorder
			? 0
			: game.Var_70da_Arr[
				(int)CityResourceTypeEnum.Production] -
				game.Var_d2f6;

		return Calculate(
			new ClassicProcessedCityValues(
				city.FoodCount,
				(city.ActualSize + 1) *
					storageFactor,
				city.ShieldsCount,
				productionCost,
				game.Var_70da_Arr[
					(int)CityResourceTypeEnum.Food] -
					(city.ActualSize * 2) -
					(settlerFoodSupport * game.Var_e3c6),
				netProduction,
				game.Var_70da_Arr[
					(int)CityResourceTypeEnum.Trade] -
					game.Var_d2e0,
				isInDisorder,
				game.Var_70e2 - game.Var_70e4));
	}

	public static ClassicCityIntelligenceSnapshot MeasureCity(
		OpenCivOneGame game,
		int cityID)
	{
		ArgumentNullException.ThrowIfNull(game);
		ValidateCity(game, cityID);
		return game.CityWorker.SynchronizeProcessing(
			() =>
			{
				using MeasurementState state = new(game);
				game.CityWorker.F0_1d12_0045_ProcessCityState(
					cityID,
					-1);
				return CaptureProcessed(game, cityID);
			});
	}

	public static ClassicPlayerIntelligenceSnapshot MeasurePlayer(
		OpenCivOneGame game,
		int playerID) =>
		MeasurePlayer(
			game,
			playerID,
			assumeResearchChoice: false);

	/// <summary>
	/// Measures the research time shown while the human player is choosing a
	/// new technology. At that point Classic deliberately stores no active
	/// research target, although the cost and current science output are
	/// already known.
	/// </summary>
	public static ClassicPlayerIntelligenceSnapshot
		MeasurePlayerForResearchChoice(
			OpenCivOneGame game,
			int playerID) =>
		MeasurePlayer(
			game,
			playerID,
			assumeResearchChoice: true);

	private static ClassicPlayerIntelligenceSnapshot MeasurePlayer(
		OpenCivOneGame game,
		int playerID,
		bool assumeResearchChoice)
	{
		ArgumentNullException.ThrowIfNull(game);
		return game.CityWorker.SynchronizeProcessing(
			() => MeasurePlayerCore(
				game,
				playerID,
				assumeResearchChoice));
	}

	private static ClassicPlayerIntelligenceSnapshot MeasurePlayerCore(
		OpenCivOneGame game,
		int playerID,
		bool assumeResearchChoice)
	{
		if (playerID < 0 ||
			playerID >= game.GameData.Players.Length)
		{
			throw new ArgumentOutOfRangeException(
				nameof(playerID));
		}

		Player player = game.GameData.Players[playerID];
		using MeasurementState state = new(game);
		bool isAnarchy = player.GovernmentType == 0;
		short projectedCoins = player.Coins;
		short projectedResearchProgress =
			player.ResearchProgress;
		TechnologyAdvanceEnum?
			completedMaintenanceTechnology =
				null;
		int startingCoins = player.Coins;
		int science = 0;
		bool hasSeti =
			game.CityWorker.F0_1d12_6c97_PlayerHasWonder(
				playerID,
				WonderEnum.SETIProgram);
		bool receivesChieftainCatchUp =
			playerID == game.GameData.HumanPlayerID &&
			game.GameData.DifficultyLevel == 0 &&
			player.ResearchTechnologyID >= 0 &&
			(game.GameData.TechnologyFirstDiscoveredBy[
				player.ResearchTechnologyID] & 7) != 0;

		foreach (City city in game.GameData.Cities)
		{
			if (city.StatusFlag == 0xff ||
				city.PlayerID != playerID)
			{
				continue;
			}

			game.CityWorker.F0_1d12_0045_ProcessCityState(
				city.ID,
				-1);
			if (isAnarchy)
			{
				continue;
			}

			int cityScience = game.Var_70e6;
			projectedResearchProgress =
				AddCityScienceToProjectedResearch(
					projectedResearchProgress,
					cityScience,
					receivesChieftainCatchUp,
					hasSeti);
			completedMaintenanceTechnology ??=
				GetCompletedMaintenanceTechnology(
					game,
					playerID,
					projectedResearchProgress);
			projectedCoins = ApplyCityTreasuryStep(
				game,
				city,
				playerID,
				projectedCoins,
				game.Var_e17a,
				completedMaintenanceTechnology);
			if (receivesChieftainCatchUp)
			{
				science += cityScience;
			}
			science += cityScience;
			if (hasSeti)
			{
				science += cityScience / 2;
			}
		}

		return new ClassicPlayerIntelligenceSnapshot(
			projectedCoins - startingCoins,
			science,
			GetResearchTurns(
				game,
				playerID,
				science,
				assumeResearchChoice));
	}

	private static short ApplyCityTreasuryStep(
		OpenCivOneGame game,
		City city,
		int playerID,
		short coins,
		int cityIncome,
		TechnologyAdvanceEnum?
			completedMaintenanceTechnology)
	{
		coins = AddWithClassicShortArithmetic(
			coins,
			cityIncome);
		for (int bit = 1; bit < 24; bit++)
		{
			if (!city.HasImprovement(
				City.BitToImprovementEnum(bit)))
			{
				continue;
			}

			int improvementTypeID = bit + 1;
			coins = AddWithClassicShortArithmetic(
				coins,
				-GetImprovementMaintenanceCost(
					game,
					improvementTypeID,
					playerID,
					completedMaintenanceTechnology));
			if (coins >= 0)
			{
				continue;
			}

			// Classic clamps an insolvent treasury, sells the improvement
			// currently being maintained, and immediately credits its
			// proceeds before continuing with the next improvement/city.
			coins = AddWithClassicShortArithmetic(
				0,
				10 * game.GameData
					.GetImprovementType(improvementTypeID)
					.Cost);
		}

		return coins;
	}

	private static int GetImprovementMaintenanceCost(
		OpenCivOneGame game,
		int improvementTypeID,
		int playerID,
		TechnologyAdvanceEnum?
			completedMaintenanceTechnology)
	{
		int maintenance = game.GameData
			.GetImprovementType(improvementTypeID)
			.MaintenanceCost;
		if (improvementTypeID !=
			(int)ImprovementEnum.Barracks)
		{
			return maintenance;
		}

		if (game.GameData.DifficultyLevel >= 2)
		{
			maintenance++;
		}
		if (game.GameData.DifficultyLevel >= 4)
		{
			maintenance++;
		}
		if (game.Segment_1ade
			.F0_1ade_22b5_PlayerHasTechnology(
				playerID,
				TechnologyAdvanceEnum.Gunpowder) ||
			completedMaintenanceTechnology ==
				TechnologyAdvanceEnum.Gunpowder)
		{
			maintenance++;
		}
		if (game.Segment_1ade
			.F0_1ade_22b5_PlayerHasTechnology(
				playerID,
				TechnologyAdvanceEnum.Combustion) ||
			completedMaintenanceTechnology ==
				TechnologyAdvanceEnum.Combustion)
		{
			maintenance++;
		}

		return maintenance;
	}

	private static short AddCityScienceToProjectedResearch(
		short progress,
		int cityScience,
		bool receivesChieftainCatchUp,
		bool hasSeti)
	{
		progress = AddWithClassicShortArithmetic(
			progress,
			cityScience);
		if (receivesChieftainCatchUp)
		{
			progress = AddWithClassicShortArithmetic(
				progress,
				cityScience);
		}
		if (hasSeti)
		{
			progress = AddWithClassicShortArithmetic(
				progress,
				cityScience / 2);
		}

		return progress;
	}

	private static TechnologyAdvanceEnum?
		GetCompletedMaintenanceTechnology(
			OpenCivOneGame game,
			int playerID,
			short projectedResearchProgress)
	{
		if (playerID != game.GameData.HumanPlayerID ||
			(game.GameData.DebugFlags & 0x8) == 0)
		{
			return null;
		}

		Player player = game.GameData.Players[playerID];
		TechnologyAdvanceEnum technology =
			(TechnologyAdvanceEnum)
				player.ResearchTechnologyID;
		if (technology is not
				TechnologyAdvanceEnum.Gunpowder and not
				TechnologyAdvanceEnum.Combustion ||
			game.Segment_1ade
				.F0_1ade_22b5_PlayerHasTechnology(
					playerID,
					technology))
		{
			return null;
		}

		return projectedResearchProgress >=
			GetResearchTargetProgress(
				game,
				playerID)
				? technology
				: null;
	}

	private static short AddWithClassicShortArithmetic(
		short value,
		int amount) =>
		unchecked((short)(value + amount));

	private static int? GetResearchTurns(
		OpenCivOneGame game,
		int playerID,
		int sciencePerTurn,
		bool assumeResearchChoice)
	{
		Player player = game.GameData.Players[playerID];
		if (!assumeResearchChoice &&
			(player.ResearchTechnologyID < 0 ||
			game.Segment_1ade
				.F0_1ade_22b5_PlayerHasTechnology(
					playerID,
					(TechnologyAdvanceEnum)
						player.ResearchTechnologyID)))
		{
			return null;
		}

		int targetProgress =
			GetResearchTargetProgress(
				game,
				playerID);
		return CeilingTurnsOrNull(
			Math.Max(
				0,
				targetProgress -
					player.ResearchProgress),
			sciencePerTurn) switch
			{
				0 => 1,
				int turns => turns,
				null => null
			};
	}

	private static int GetResearchTargetProgress(
		OpenCivOneGame game,
		int playerID)
	{
		Player player = game.GameData.Players[playerID];
		int costFactor =
			playerID == game.GameData.HumanPlayerID
				? (game.GameData.DifficultyLevel * 2) +
					game.Var_d2de + 6
				: 14 -
					game.GameData.DifficultyLevel +
					game.Var_d2de;
		if (playerID == game.GameData.HumanPlayerID)
		{
			costFactor = Math.Max(
				costFactor,
				11 - player.DiscoveredTechnologyCount);
		}

		int eraFactor =
			game.GameData.Year < 0 ? 1 : 2;
		return
			((player.DiscoveredTechnologyCount *
				costFactor) + 1) * eraFactor;
	}

	private static int? CeilingTurnsOrNull(
		int amount,
		int perTurn)
	{
		if (amount <= 0)
		{
			return 0;
		}

		return perTurn <= 0
			? null
			: (int)(((long)amount + perTurn - 1) /
				perTurn);
	}

	private static int? GetProductionTurns(
		ClassicProcessedCityValues values)
	{
		if (values.ProductionCost <= 0)
		{
			return null;
		}

		if (values.NetProduction > 0)
		{
			int? turns = CeilingTurnsOrNull(
				Math.Max(
					0,
					values.ProductionCost -
						values.ShieldsStored),
				values.NetProduction);
			return Math.Max(1, turns ?? 1);
		}

		return (long)values.ShieldsStored +
			values.NetProduction >=
			values.ProductionCost
				? 1
				: null;
	}

	private static int? AddOneRound(int? turns) =>
		turns.HasValue
			? ToPositiveInt((long)turns.Value + 1)
			: null;

	private static int ToPositiveInt(long value) =>
		(int)Math.Clamp(value, 1, int.MaxValue);

	private static int ToNonNegativeInt(long value) =>
		(int)Math.Clamp(value, 0, int.MaxValue);

	private static void ValidateCity(
		OpenCivOneGame game,
		int cityID)
	{
		if (cityID < 0 ||
			cityID >= game.GameData.Cities.Length ||
			game.GameData.Cities[cityID].StatusFlag == 0xff)
		{
			throw new ArgumentOutOfRangeException(
				nameof(cityID));
		}
	}

	private readonly record struct CityState(
		uint ImprovementFlags,
		int PositionX,
		int PositionY,
		byte StatusFlag,
		sbyte ActualSize,
		sbyte VisibleSize,
		sbyte CurrentProductionID,
		sbyte BaseTrade,
		short PlayerID,
		short FoodCount,
		short ShieldsCount,
		uint WorkerFlags,
		ushort SpecialWorkerFlags,
		byte NameID,
		sbyte[] TradeCityIDs,
		sbyte[] Unknown)
	{
		public static CityState Capture(City city) =>
			new(
				city.ImprovementFlags,
				city.Position.X,
				city.Position.Y,
				city.StatusFlag,
				city.ActualSize,
				city.VisibleSize,
				city.CurrentProductionID,
				city.BaseTrade,
				city.PlayerID,
				city.FoodCount,
				city.ShieldsCount,
				city.WorkerFlags,
				city.SpecialWorkerFlags,
				city.NameID,
				(sbyte[])city.TradeCityIDs.Clone(),
				(sbyte[])city.Unknown.Clone());

		public void Restore(City city)
		{
			city.ImprovementFlags = this.ImprovementFlags;
			city.Position = new GPoint(
				this.PositionX,
				this.PositionY);
			city.StatusFlag = this.StatusFlag;
			city.ActualSize = this.ActualSize;
			city.VisibleSize = this.VisibleSize;
			city.CurrentProductionID =
				this.CurrentProductionID;
			city.BaseTrade = this.BaseTrade;
			city.PlayerID = this.PlayerID;
			city.FoodCount = this.FoodCount;
			city.ShieldsCount = this.ShieldsCount;
			city.WorkerFlags = this.WorkerFlags;
			city.SpecialWorkerFlags =
				this.SpecialWorkerFlags;
			city.NameID = this.NameID;
			Array.Copy(
				this.TradeCityIDs,
				city.TradeCityIDs,
				this.TradeCityIDs.Length);
			Array.Copy(
				this.Unknown,
				city.Unknown,
				this.Unknown.Length);
		}
	}

	private sealed class MeasurementState : IDisposable
	{
		private readonly OpenCivOneGame game;
		private readonly CityState[] cities;
		private readonly byte[] mapPixels;
		private readonly bool mapModified;
		private readonly bool mapVisible;
		private readonly ushort[,] mapVisibility;
		private readonly CityWorker.ScratchState cityWorker;
		private readonly int var2f9e;
		private readonly int var6c98;
		private readonly int[] var70da;
		private readonly int var70e2;
		private readonly int var70e4;
		private readonly int var70e6;
		private readonly int var8078;
		private readonly int varB1e8;
		private readonly int varB2ba;
		private readonly int varB882;
		private readonly int varD2e0;
		private readonly int varD2f6;
		private readonly int varDb42;
		private readonly int varDeb8;
		private readonly int varE17a;
		private readonly int varE3c2;
		private readonly int varE3c6;
		private readonly int varE8b8;

		public MeasurementState(OpenCivOneGame game)
		{
			this.game = game;
			this.cities = game.GameData.Cities
				.Select(CityState.Capture)
				.ToArray();
			this.mapPixels =
				(byte[])game.GameData.Map.Pixels.Clone();
			this.mapModified =
				game.GameData.Map.Modified;
			this.mapVisible =
				game.GameData.Map.Visible;
			this.mapVisibility =
				(ushort[,])game.GameData.MapVisibility.Clone();
			this.cityWorker =
				game.CityWorker.CaptureScratchState();
			this.var2f9e =
				(int)game.Var_2f9e_MessageBoxStyle;
			this.var6c98 = game.Var_6c98;
			this.var70da =
				(int[])game.Var_70da_Arr.Clone();
			this.var70e2 = game.Var_70e2;
			this.var70e4 = game.Var_70e4;
			this.var70e6 = game.Var_70e6;
			this.var8078 = game.Var_8078;
			this.varB1e8 = game.Var_b1e8;
			this.varB2ba = game.Var_b2ba;
			this.varB882 = game.Var_b882;
			this.varD2e0 = game.Var_d2e0;
			this.varD2f6 = game.Var_d2f6;
			this.varDb42 = game.Var_db42;
			this.varDeb8 = game.Var_deb8;
			this.varE17a = game.Var_e17a;
			this.varE3c2 = game.Var_e3c2;
			this.varE3c6 = game.Var_e3c6;
			this.varE8b8 = game.Var_e8b8;
		}

		public void Dispose()
		{
			for (int i = 0; i < this.cities.Length; i++)
			{
				this.cities[i].Restore(
					this.game.GameData.Cities[i]);
			}

			Array.Copy(
				this.mapPixels,
				this.game.GameData.Map.Pixels,
				this.mapPixels.Length);
			this.game.GameData.Map.Modified =
				this.mapModified;
			this.game.GameData.Map.Visible =
				this.mapVisible;
			Array.Copy(
				this.mapVisibility,
				this.game.GameData.MapVisibility,
				this.mapVisibility.Length);
			this.game.CityWorker.RestoreScratchState(
				this.cityWorker);
			this.game.Var_2f9e_MessageBoxStyle =
				(MenuBoxReportTypeEnum)this.var2f9e;
			this.game.Var_6c98 = this.var6c98;
			Array.Copy(
				this.var70da,
				this.game.Var_70da_Arr,
				this.var70da.Length);
			this.game.Var_70e2 = this.var70e2;
			this.game.Var_70e4 = this.var70e4;
			this.game.Var_70e6 = this.var70e6;
			this.game.Var_8078 = this.var8078;
			this.game.Var_b1e8 = this.varB1e8;
			this.game.Var_b2ba = this.varB2ba;
			this.game.Var_b882 = this.varB882;
			this.game.Var_d2e0 = this.varD2e0;
			this.game.Var_d2f6 = this.varD2f6;
			this.game.Var_db42 = this.varDb42;
			this.game.Var_deb8 = this.varDeb8;
			this.game.Var_e17a = this.varE17a;
			this.game.Var_e3c2 = this.varE3c2;
			this.game.Var_e3c6 = this.varE3c6;
			this.game.Var_e8b8 = this.varE8b8;
		}
	}
}
