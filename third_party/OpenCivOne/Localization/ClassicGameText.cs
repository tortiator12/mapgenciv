using System.Globalization;

namespace OpenCivOne.Localization;

/// <summary>
/// Keys for text drawn inside the original 320x200 Classic framebuffer.
/// Values must stay seven-bit ASCII because the original fonts reserve
/// characters above 0x7f for color control.
/// </summary>
public enum ClassicGameTextKey
{
	DifficultyMenu,
	DifficultyNameChieftain,
	DifficultyNameWarlord,
	DifficultyNamePrince,
	DifficultyNameKing,
	DifficultyNameEmperor,
	AiProfileMenu,
	CompetitionTitle,
	CivilizationCount,
	PickTribe,
	InitialRoadsSuffix,
	CityPopulation,
	CityRequiresAqueduct,
	CityPopulationDecrease,
	CityBuildsUnit,
	CityCannotSupportUnit,
	CityCivilDisorder,
	CityOrderRestored,
	CityPollutionNear,
	CityBuildsImprovement,
	CityNuclearWeaponsTestNear,
	DiplomatsReportCapitalMoved,
	CapitalMoved,
	CityProductionCost,
	CityProductionCivilDisorder,
	CityProductionPurchasePrompt,
	CitySellImprovementPrompt,
	CityCannotMaintainImprovement,
	CityFoodStorageExhaustedSettlerLost,
	CityFoodStorageExhaustedFamineFeared,
	CitySpecialistsRequireFivePopulation,
	CityGovernmentCollapsed,
	CityLeaderDayCelebrated,
	CityLeaderCelebrationCanceled,
	CityNuclearCatastrophe,
	CityInfoButton,
	CityHappyButton,
	CityMapButton,
	CityViewButton,
	CityExitButton,
	CityRenameButton,
	More,
	Wonders,
	AutomaticProduction,
	ChangeProduction,
	BuyProduction,
	MainMenuGame,
	MainMenuOrders,
	MainMenuAdvisors,
	MainMenuWorld,
	MainMenuCivilopedia,
	GameMenu,
	GameMenu1991Plus,
	GameMenuViewReplay,
	GameOptionsMenu,
	GameOptionsMenu1991Plus,
	QualityOfLifeMenu,
	OrdersNoOrders,
	OrdersAddToCity,
	OrdersFoundNewCity,
	OrdersBuildRoad,
	OrdersBuildRailroad,
	OrdersBuildIrrigation,
	OrdersChangeToPrefix,
	OrdersBuildMines,
	OrdersCleanPollution,
	OrdersBuildFortress,
	OrdersFortify,
	OrdersWaitSentryGoTo,
	OrdersAutomaticExplore,
	OrdersImproveNearestCity,
	ImproveNearestCityComplete,
	OrdersRoadToCity,
	RoadToCityComplete,
	RoadToCitySelectOwnCity,
	RoadToCityUnavailable,
	TriremeNoSafeCoastalRoute,
	AutomaticExploreNoSafeCoastalRoute,
	HomeCityReassignedOne,
	HomeCityReassignedMany,
	OrdersPillage,
	OrdersHomeCity,
	OrdersUnload,
	OrdersDisbandUnit,
	OrdersWakeAllOfType,
	WakeAllOfTypeResult,
	OrdersSuggestTradeDestination,
	CaravanTradeAdvisorTitle,
	CaravanTradeAdvisorNoKnownDestination,
	CaravanTradeAdvisorExactResult,
	CaravanTradeAdvisorApproximateResult,
	CaravanTradeAdvisorNewRoute,
	CaravanTradeAdvisorExistingRoute,
	CaravanTradeAdvisorKnownLandRoute,
	CaravanTradeAdvisorTransportRequired,
	CombatPreviewPrompt,
	CombatPreviewReducedStrength,
	AdvisorsMenu,
	WorldMenu,
	EncyclopediaMenu,
	EndOfTurn,
	PressEnter,
	ToContinue,
	Veteran,
	UnitMoves,
	RailRoadLabel,
	RoadLabel,
	IrrigationLabel,
	MiningLabel,
	PollutionLabel,
	NoHomeCity,
	FoodStorage,
	CityResources,
	ProductionQuestionPrefix,
	ProductionQuestionSuffix,
	Researching,
	ScienceReportTitle,
	ScienceAdvisorRecommendation,
	ScienceAdvisorBuilds,
	ResearchChoicePrefix,
	Scientists,
	WiseMen,
	ResearchChoiceSuffix,
	ResearchChoiceTurns,
	TechnologyDiscoveryConnector,
	FutureTechnology,
	GameSaved,
	GameNotSaved,
	ContinueAfterSave,
	SaveSlotEmpty,
	SaveSlotInvalid,
	SaveSlotProfileUnavailable,
	SaveSlotLegacyPrefix,
	SaveSlotClassicPrefix,
	SaveSlotEnhancedPrefix,
	LoadGameMenuTitle,
	SaveGameMenuTitle,
	LoadGameCatalogTitle,
	LoadGameCatalogEmpty,
	LoadGameCatalogPreviousPage,
	LoadGameCatalogNextPage,
	SaveGameNameDialogTitle,
	SaveGameNameDialogPlaceholder,
	SaveGameNameInvalid,
	SaveGameOverwriteQuestion,
	SpaceshipTitleConnector,
	SpaceshipFuelPrefix,
	SpaceshipFlightTime,
	SpaceshipYearsSuffix,
	SpaceshipSuccessProbability,
	SpaceshipLanded,
	SpaceshipLaunched,
	SpaceshipLaunchButton,
	SpaceshipConfirmLaunch,
	SpaceshipBuildsSuffix,
	SpaceshipLaunchesSuffix,
	SpaceshipArrivalPrefix,
	DiplomatArrivesInConnector,
	DiplomatCityActionMenu,
	DiplomatStealsConnector,
	DiplomatDestroyedSuffix,
	DiplomatProductionSabotagedSuffix,
	DiplomatCityResultInPrefix,
	DiplomatDissidentsInPrefix,
	DiplomatRevoltPriceSuffix,
	DiplomatInciteMenu,
	DiplomatSubvertCityOption,
	DiplomatWillDesertForConnector,
	DiplomatTreasuryPrefix,
	DiplomatPayMenu,
	DiplomatUnitBribedByConnector,
	TradeReportTitle,
	TradeReportCityTrade,
	TradeReportDisorder,
	TradeReportTotalIncome,
	TradeReportDiscoveries,
	TradeReportTurnsSuffix,
	TradeReportMaintenanceCosts,
	TradeReportTotalCost,
	CityStatusReportTitle,
	CityQolNetSummary,
	CityQolGrowthTurns,
	CityQolFamineTurns,
	CityQolStableGrowth,
	CityQolProductionTurns,
	CityQolProductionStalled,
	CityQolFamineWarning,
	CityQolDisorderWarning,
	CityQolShieldOverflow,
	CityStatusQolTurnsSuffix,
	EconomyQolCurrentForecast,
	ScienceQolForecast,
	OverviewQolEconomyResearch,
	QolNoEta,
	DemographicsReportTitle,
	DemographicsApprovalRating,
	DemographicsPopulation,
	DemographicsGrossNationalProduct,
	DemographicsManufacturedGoods,
	DemographicsLandArea,
	DemographicsLiteracy,
	DemographicsDisease,
	DemographicsPollution,
	DemographicsLifeExpectancy,
	DemographicsFamilySize,
	DemographicsMilitaryService,
	DemographicsAnnualIncome,
	DemographicsProductivity,
	ReportEmpireOfNation,
	ReportKingdomOfNation,
	ReportRepublicOfNation,
	ReportRulerTitleMr,
	ReportRulerTitleEmperor,
	ReportRulerTitleKing,
	ReportRulerTitleComrade,
	ReportRulerTitlePresident,
	ReportGovernmentAnarchy,
	ReportGovernmentDespotism,
	ReportGovernmentMonarchy,
	ReportGovernmentCommunist,
	ReportGovernmentRepublic,
	ReportGovernmentDemocratic,
	ReportRulerAndYear,
	ReportYearBeforeCommonEra,
	ReportYearCommonEra,
	MilitaryReportTitle,
	MilitaryLossesReportTitle,
	MilitaryActiveSuffix,
	MilitaryInProductionSuffix,
	IntelligenceOverviewTitle,
	IntelligenceReportTitle,
	IntelligenceNoEmbassy,
	IntelligenceInfoButton,
	IntelligenceSubjectPrefix,
	IntelligenceLeaderPrefix,
	IntelligenceAggressive,
	IntelligenceFriendly,
	IntelligenceExpansionistic,
	IntelligencePerfectionist,
	IntelligenceCivilized,
	IntelligenceMilitaristic,
	IntelligenceCapitalPrefix,
	IntelligenceGovernmentPrefix,
	IntelligenceTreasuryPrefix,
	IntelligenceMilitaryPrefix,
	IntelligenceUnitsSuffix,
	IntelligenceForeignAffairs,
	IntelligencePeace,
	IntelligenceWar,
	IntelligenceAtPeace,
	IntelligenceAtWar,
	IntelligenceAllied,
	IntelligenceWithNationConnector,
	IntelligenceTechnologies,
	AttitudeReportTitle,
	AttitudePopulationPrefix,
	AttitudeHappyPrefix,
	AttitudeContentPrefix,
	AttitudeUnhappyPrefix,
	PowerGraphTitle,
	WondersReportTitle,
	WondersBuiltIn,
	WondersAncientName,
	WondersDestroyed,
	CivilizationScoreTitle,
	ScoreCompleted,
	ScoreCitizensConnector,
	ScoreAchievementsConnector,
	ScoreSpaceshipPrefix,
	ScorePossibleSuffix,
	ScorePollutionPrefix,
	ScorePeacePrefix,
	ScoreFutureTechnologyPrefix,
	ScoreTotalPrefix,
	ScoreBonusPrefix,
	ReplayFileError,
	ReplayFoundCityConnector,
	ReplayCaptureConnector,
	ReplayCityDestroyedSuffix,
	ReplayDeclareWarConnector,
	ReplayMakePeaceConnector,
	ReplayDiscoverConnector,
	ReplayProduceFirstConnector,
	ReplayFormConnector,
	ReplayBuildWonderConnector,
	ReplayBuildAncientWonderConnector,
	ReplayEmpireCitiesConnector,
	ReplayEmpirePopulationSuffix,
	ReplayCivilizationDestroyed,
	ReplayWorldHails,
	ReplayConquerorLine,
	ReplayDestroyLine,
	ReplayDestroyedCivilizationLine
}

/// <summary>
/// Immutable text catalog with per-key fallback.
/// </summary>
public sealed class ClassicGameTextCatalog
{
	private readonly IReadOnlyDictionary<ClassicGameTextKey, string> texts;
	private readonly ClassicGameTextCatalog? fallback;
	private readonly ClassicDisplayNameCatalog displayNames;

	public ClassicGameTextCatalog(
		IReadOnlyDictionary<ClassicGameTextKey, string> texts,
		ClassicGameTextCatalog? fallback = null)
		: this(
			texts,
			fallback,
			"und",
			ClassicDisplayNameCatalog.Empty)
	{
	}

	internal ClassicGameTextCatalog(
		IReadOnlyDictionary<ClassicGameTextKey, string> texts,
		ClassicGameTextCatalog? fallback,
		string languageCode,
		ClassicDisplayNameCatalog displayNames)
	{
		ArgumentNullException.ThrowIfNull(texts);
		ArgumentException.ThrowIfNullOrWhiteSpace(languageCode);
		ArgumentNullException.ThrowIfNull(displayNames);

		this.texts = new Dictionary<ClassicGameTextKey, string>(texts);
		this.fallback = fallback;
		this.LanguageCode = languageCode;
		this.displayNames = displayNames;
	}

	public string LanguageCode { get; }

	public string this[ClassicGameTextKey key]
	{
		get
		{
			if (this.texts.TryGetValue(key, out string? text))
			{
				return text;
			}

			if (this.fallback is not null)
			{
				return this.fallback[key];
			}

			throw new KeyNotFoundException(
				$"Classic game text '{key}' is not defined.");
		}
	}

	public string Format(
		ClassicGameTextKey key,
		params object?[] arguments)
	{
		return string.Format(
			CultureInfo.InvariantCulture,
			this[key],
			arguments);
	}

	public bool Defines(ClassicGameTextKey key)
	{
		return this.texts.ContainsKey(key);
	}

	internal bool TryGetUnitDisplayName(
		UnitTypeEnum type,
		out string name)
	{
		return this.displayNames.TryGetUnit(type, out name!);
	}

	internal bool TryGetTerrainDisplayName(
		TerrainTypeEnum type,
		out string name)
	{
		return this.displayNames.TryGetTerrain(type, out name!);
	}

	internal bool TryGetImprovementDisplayName(
		ImprovementEnum type,
		out string name)
	{
		return this.displayNames.TryGetImprovement(type, out name!);
	}

	internal bool TryGetWonderDisplayName(
		WonderEnum type,
		out string name)
	{
		return this.displayNames.TryGetWonder(type, out name!);
	}

	internal bool TryGetNationDisplayName(
		int nationalityID,
		out string name)
	{
		return this.displayNames.TryGetNation(
			nationalityID,
			out name!);
	}
}

/// <summary>
/// German-first catalog for the Classic framebuffer. The source texts live in
/// validated embedded JSON packs; English remains the complete per-key
/// fallback without changing game or save data.
/// </summary>
public static class ClassicGameText
{
	public static ClassicGameTextCatalog English { get; } =
		ClassicLanguagePackLoader.LoadEmbedded(
			"en",
			fallback: null,
			requireComplete: true);

	public static ClassicGameTextCatalog German { get; } =
		ClassicLanguagePackLoader.LoadEmbedded(
			"de",
			English,
			requireComplete: true);

	private static ClassicGameTextCatalog current = German;

	public static ClassicGameTextCatalog Current =>
		Volatile.Read(ref current);

	public static ClassicGameTextCatalog ForLanguage(
		string? languageCode)
	{
		if (string.IsNullOrWhiteSpace(languageCode))
		{
			return German;
		}

		string neutralLanguage = languageCode
			.Split(
				['-', '_'],
				2,
				StringSplitOptions.RemoveEmptyEntries)[0];

		return neutralLanguage.Equals(
			"en",
			StringComparison.OrdinalIgnoreCase)
				? English
				: German;
	}

	public static void UseLanguage(string? languageCode)
	{
		Volatile.Write(ref current, ForLanguage(languageCode));
	}
}
