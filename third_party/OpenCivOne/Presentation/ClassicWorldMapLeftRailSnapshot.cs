using OpenCivOne.Runtime;

namespace OpenCivOne.Presentation;

public enum ClassicWorldMapUnitPanelKind : byte
{
	None,
	ActiveUnit,
	EndOfTurn,
}

public readonly record struct ClassicWorldMapStackUnitSnapshot(
	int UnitID,
	UnitTypeEnum UnitType,
	UnitStatusEnum Status,
	bool IsCityDefender);

/// <summary>
/// Semantic state used by the lower half of the source-faithful Classic
/// world-map rail. All data belongs to the human player and is safe to
/// present without revealing an unseen opponent.
/// </summary>
public sealed class ClassicWorldMapActiveUnitPanelSnapshot
{
	private readonly IReadOnlyList<ClassicWorldMapStackUnitSnapshot>
		stackUnits;

	internal ClassicWorldMapActiveUnitPanelSnapshot(
		int unitID,
		int nationalityID,
		string nationalityFallback,
		UnitTypeEnum unitType,
		bool isVeteran,
		int movesWhole,
		int moveThirds,
		int effectiveMovesWhole,
		int homeCityID,
		string homeCityName,
		TerrainTypeEnum terrainType,
		TerrainImprovementFlagsEnum visibleImprovements,
		IEnumerable<ClassicWorldMapStackUnitSnapshot> stackUnits,
		bool hasStackOverflow)
	{
		ArgumentNullException.ThrowIfNull(nationalityFallback);
		ArgumentNullException.ThrowIfNull(homeCityName);
		ArgumentNullException.ThrowIfNull(stackUnits);

		UnitID = unitID;
		NationalityID = nationalityID;
		NationalityFallback = nationalityFallback;
		UnitType = unitType;
		IsVeteran = isVeteran;
		MovesWhole = movesWhole;
		MoveThirds = moveThirds;
		EffectiveMovesWhole = effectiveMovesWhole;
		HomeCityID = homeCityID;
		HomeCityName = homeCityName;
		TerrainType = terrainType;
		VisibleImprovements = visibleImprovements;
		this.stackUnits = Array.AsReadOnly(
			stackUnits.ToArray());
		HasStackOverflow = hasStackOverflow;
	}

	public int UnitID { get; }

	public int NationalityID { get; }

	public string NationalityFallback { get; }

	public UnitTypeEnum UnitType { get; }

	public bool IsVeteran { get; }

	public int MovesWhole { get; }

	public int MoveThirds { get; }

	public int EffectiveMovesWhole { get; }

	public int HomeCityID { get; }

	public string HomeCityName { get; }

	public TerrainTypeEnum TerrainType { get; }

	public TerrainImprovementFlagsEnum VisibleImprovements { get; }

	public IReadOnlyList<ClassicWorldMapStackUnitSnapshot> StackUnits =>
		this.stackUnits;

	public bool HasStackOverflow { get; }
}

/// <summary>
/// Immutable semantic copy of the complete left rail on the interactive
/// Classic world screen. It preserves the original information hierarchy
/// while leaving language, typography and final pixels to the presenter.
/// </summary>
public sealed class ClassicWorldMapLeftRailSnapshot
{
	private readonly IReadOnlyList<short> palacePieceLevels;
	private readonly IReadOnlyList<short> palacePieceStyles;

	internal ClassicWorldMapLeftRailSnapshot(
		int peaceTurnCount,
		bool hasPalace,
		int palaceLevel,
		IEnumerable<short> palacePieceLevels,
		IEnumerable<short> palacePieceStyles,
		int populationThousands,
		int researchProgressStage,
		int? pollutionStage,
		int coins,
		int taxRate,
		int luxuryRate,
		int scienceRate,
		bool uses1991PlusOverview,
		int? netGoldPerTurn,
		int? researchTurns,
		ClassicWorldMapUnitPanelKind unitPanelKind,
		ClassicWorldMapActiveUnitPanelSnapshot? activeUnit)
	{
		ArgumentNullException.ThrowIfNull(palacePieceLevels);
		ArgumentNullException.ThrowIfNull(palacePieceStyles);
		short[] levels = palacePieceLevels.ToArray();
		short[] styles = palacePieceStyles.ToArray();
		if (levels.Length != 9)
		{
			throw new ArgumentException(
				"The Classic palace preview needs nine piece levels.",
				nameof(palacePieceLevels));
		}

		if (styles.Length != 9)
		{
			throw new ArgumentException(
				"The Classic palace preview needs nine piece styles.",
				nameof(palacePieceStyles));
		}

		if ((unitPanelKind ==
				ClassicWorldMapUnitPanelKind.ActiveUnit) !=
			(activeUnit is not null))
		{
			throw new ArgumentException(
				"An active-unit rail needs exactly one active-unit snapshot.",
				nameof(activeUnit));
		}

		PeaceTurnCount = peaceTurnCount;
		HasPalace = hasPalace;
		PalaceLevel = palaceLevel;
		this.palacePieceLevels = Array.AsReadOnly(levels);
		this.palacePieceStyles = Array.AsReadOnly(styles);
		PopulationThousands = populationThousands;
		ResearchProgressStage = researchProgressStage;
		PollutionStage = pollutionStage;
		Coins = coins;
		TaxRate = taxRate;
		LuxuryRate = luxuryRate;
		ScienceRate = scienceRate;
		Uses1991PlusOverview = uses1991PlusOverview;
		NetGoldPerTurn = netGoldPerTurn;
		ResearchTurns = researchTurns;
		UnitPanelKind = unitPanelKind;
		ActiveUnit = activeUnit;
	}

	public int PeaceTurnCount { get; }

	public bool HasPalace { get; }

	public int PalaceLevel { get; }

	public IReadOnlyList<short> PalacePieceLevels =>
		this.palacePieceLevels;

	public IReadOnlyList<short> PalacePieceStyles =>
		this.palacePieceStyles;

	/// <summary>
	/// Population in thousands, matching Classic's triangular city-size
	/// formula before the original renderer appends the three zeroes.
	/// </summary>
	public int PopulationThousands { get; }

	public int ResearchProgressStage { get; }

	public int? PollutionStage { get; }

	public int Coins { get; }

	public int TaxRate { get; }

	public int LuxuryRate { get; }

	public int ScienceRate { get; }

	public bool Uses1991PlusOverview { get; }

	public int? NetGoldPerTurn { get; }

	public int? ResearchTurns { get; }

	public ClassicWorldMapUnitPanelKind UnitPanelKind { get; }

	public ClassicWorldMapActiveUnitPanelSnapshot? ActiveUnit { get; }
}

internal static class ClassicWorldMapLeftRailCapture
{
	private const TerrainImprovementFlagsEnum VisibleRailImprovementMask =
		TerrainImprovementFlagsEnum.Road |
		TerrainImprovementFlagsEnum.RailRoad |
		TerrainImprovementFlagsEnum.Irrigation |
		TerrainImprovementFlagsEnum.Mines |
		TerrainImprovementFlagsEnum.Pollution;

	public static ClassicWorldMapLeftRailSnapshot Capture(
		OpenCivOneGame game,
		ClassicRuntimePresentationSnapshot presentation)
	{
		ArgumentNullException.ThrowIfNull(game);
		GameData gameData = game.GameData;
		int humanPlayerID = gameData.HumanPlayerID;
		Player human = gameData.Players[humanPlayerID];
		bool uses1991PlusOverview =
			ClassicAiRuntimeProfiles.UsesSmartEnhancements(
				gameData.AiProfile);
		ClassicPlayerIntelligenceSnapshot? forecast =
			uses1991PlusOverview
				? ClassicCityIntelligence.MeasurePlayer(
					game,
					humanPlayerID)
				: null;
		ClassicWorldMapUnitPanelKind panelKind =
			presentation.IsEndOfTurnPrompt
				? ClassicWorldMapUnitPanelKind.EndOfTurn
				: ClassicWorldMapUnitPanelKind.None;
		ClassicWorldMapActiveUnitPanelSnapshot? activeUnit = null;
		if (!presentation.IsEndOfTurnPrompt &&
			TryCaptureActiveUnit(
				game,
				presentation,
				out activeUnit))
		{
			panelKind =
				ClassicWorldMapUnitPanelKind.ActiveUnit;
		}

		int researchDenominator =
			(((gameData.DifficultyLevel * 2) +
				game.Var_d2de +
				6) *
				human.DiscoveredTechnologyCount *
				(gameData.Year < 0 ? 1 : 2)) +
			1;
		int researchProgressStage =
			Math.Clamp(
				(human.ResearchProgress * 4) /
					Math.Max(researchDenominator, 1),
				0,
				3);
		int? pollutionStage =
			gameData.PollutionEffectLevel == 0
				? null
				: Math.Clamp(
					gameData.PollutionEffectLevel / 4,
					0,
					3);

		return new ClassicWorldMapLeftRailSnapshot(
			gameData.PeaceTurnCount,
			human.CityCount != 0,
			human.PalaceLevel,
			human.PalaceData1.Skip(2).Take(9),
			human.PalaceData2.Take(9),
			game.Tools.F0_2dc4_02cd_GetPlayerTotalPopulationCount(
				humanPlayerID),
			researchProgressStage,
			pollutionStage,
			human.Coins,
			human.TaxRate,
			10 - human.TaxRate - human.ScienceTaxRate,
			human.ScienceTaxRate,
			uses1991PlusOverview,
			forecast?.NetGoldPerTurn,
			forecast?.ResearchTurns,
			panelKind,
			activeUnit);
	}

	private static bool TryCaptureActiveUnit(
		OpenCivOneGame game,
		ClassicRuntimePresentationSnapshot presentation,
		out ClassicWorldMapActiveUnitPanelSnapshot? snapshot)
	{
		snapshot = null;
		int playerID = presentation.PlayerID;
		int unitID = presentation.ActiveUnitID;
		if (playerID != game.GameData.HumanPlayerID ||
			playerID < 0 ||
			playerID >= game.GameData.Players.Length)
		{
			return false;
		}

		Player player = game.GameData.Players[playerID];
		if (unitID < 0 || unitID >= player.Units.Length)
		{
			return false;
		}

		Unit unit = player.Units[unitID];
		if (unit.UnitType == UnitTypeEnum.None)
		{
			return false;
		}

		UnitDefinition definition =
			game.GameData.Units[(int)unit.UnitType];
		int movesWhole = Math.Clamp(
			unit.RemainingMoves / 3,
			0,
			99);
		int effectiveMovesWhole =
			movesWhole +
			(definition.TurnsOutside != 0
				? definition.MoveCount * unit.SpecialMoves
				: 0);
		TerrainTypeEnum terrainType =
			game.MapManagement.GetTerrainType(unit.Position);
		TerrainImprovementFlagsEnum allVisibleImprovements =
			game.MapManagement
				.F0_2aea_1585_GetVisibleTerrainImprovements(
					unit.Position.X,
					unit.Position.Y);
		TerrainImprovementFlagsEnum visibleImprovements =
			allVisibleImprovements &
			VisibleRailImprovementMask;
		List<ClassicWorldMapStackUnitSnapshot> stackUnits =
			CaptureStackUnits(
				game,
				playerID,
				unitID,
				unit,
				allVisibleImprovements);
		int lineCount =
			5 +
			(unit.Status.HasFlag(UnitStatusEnum.Veteran) ? 1 : 0) +
			(visibleImprovements.HasFlag(
				TerrainImprovementFlagsEnum.RailRoad) ||
			 visibleImprovements.HasFlag(
				TerrainImprovementFlagsEnum.Road)
				? 1
				: 0) +
			(visibleImprovements.HasFlag(
				TerrainImprovementFlagsEnum.Irrigation) ||
			 visibleImprovements.HasFlag(
				TerrainImprovementFlagsEnum.Mines)
				? 1
				: 0) +
			(visibleImprovements.HasFlag(
				TerrainImprovementFlagsEnum.Pollution)
				? 1
				: 0);
		int iconStartY = 99 + (lineCount * 8) + 4;
		int iconRows =
			Math.Max(0, (184 - iconStartY + 15) / 16);
		int visibleIconCapacity = iconRows * 4;

		snapshot = new ClassicWorldMapActiveUnitPanelSnapshot(
			unitID,
			player.NationalityID,
			player.Nationality,
			unit.UnitType,
			unit.Status.HasFlag(UnitStatusEnum.Veteran),
			movesWhole,
			Math.Max(unit.RemainingMoves % 3, 0),
			effectiveMovesWhole,
			unit.HomeCityID,
			GetHomeCityName(game, unit.HomeCityID),
			terrainType,
			visibleImprovements,
			stackUnits,
			stackUnits.Count > visibleIconCapacity);
		return true;
	}

	private static List<ClassicWorldMapStackUnitSnapshot>
		CaptureStackUnits(
			OpenCivOneGame game,
			int playerID,
			int activeUnitID,
			Unit activeUnit,
			TerrainImprovementFlagsEnum visibleImprovements)
	{
		List<ClassicWorldMapStackUnitSnapshot> stackUnits = [];
		if (visibleImprovements.HasFlag(
				TerrainImprovementFlagsEnum.City))
		{
			int cityID =
				game.Tools.F0_2dc4_00ba_GetCityByLocation(
					activeUnit.Position.X,
					activeUnit.Position.Y);
			if (cityID >= 0 &&
				cityID < game.GameData.Cities.Length)
			{
				City city = game.GameData.Cities[cityID];
				for (int i = 0; i < 2; i++)
				{
					int cityDefender = city.Unknown[i];
					if (cityDefender != -1)
					{
						stackUnits.Add(
							new ClassicWorldMapStackUnitSnapshot(
								UnitID: -1,
								(UnitTypeEnum)(cityDefender & 0x3f),
								UnitStatusEnum.Fortified,
								IsCityDefender: true));
					}
				}
			}
		}

		Player player = game.GameData.Players[playerID];
		HashSet<int> visited = [activeUnitID];
		int nextUnitID = activeUnit.NextUnitID;
		while (nextUnitID >= 0 &&
			nextUnitID < player.Units.Length &&
			visited.Add(nextUnitID))
		{
			Unit stackedUnit = player.Units[nextUnitID];
			if (stackedUnit.UnitType == UnitTypeEnum.None)
			{
				break;
			}

			stackUnits.Add(
				new ClassicWorldMapStackUnitSnapshot(
					nextUnitID,
					stackedUnit.UnitType,
					stackedUnit.Status,
					IsCityDefender: false));
			nextUnitID = stackedUnit.NextUnitID;
		}

		return stackUnits;
	}

	private static string GetHomeCityName(
		OpenCivOneGame game,
		int homeCityID)
	{
		if (homeCityID < 0 ||
			homeCityID >= game.GameData.Cities.Length)
		{
			return string.Empty;
		}

		City city = game.GameData.Cities[homeCityID];
		if (city.StatusFlag == byte.MaxValue ||
			city.NameID >= game.GameData.CityNames.Length)
		{
			return string.Empty;
		}

		return game.GameData.CityNames[city.NameID]
			.TrimEnd('\0', ' ');
	}
}
