namespace OpenCivOne.Localization;

/// <summary>
/// Immutable, display-only names carried by a Classic language pack.
/// Canonical game data and serialized names remain outside this type.
/// </summary>
internal sealed class ClassicDisplayNameCatalog
{
	public static ClassicDisplayNameCatalog Empty { get; } = new(
		new Dictionary<UnitTypeEnum, string>(),
		new Dictionary<TerrainTypeEnum, string>(),
		new Dictionary<ImprovementEnum, string>(),
		new Dictionary<WonderEnum, string>(),
		new Dictionary<int, string>());

	private readonly IReadOnlyDictionary<UnitTypeEnum, string> units;
	private readonly IReadOnlyDictionary<TerrainTypeEnum, string> terrains;
	private readonly IReadOnlyDictionary<ImprovementEnum, string> improvements;
	private readonly IReadOnlyDictionary<WonderEnum, string> wonders;
	private readonly IReadOnlyDictionary<int, string> nations;

	public ClassicDisplayNameCatalog(
		IReadOnlyDictionary<UnitTypeEnum, string> units,
		IReadOnlyDictionary<TerrainTypeEnum, string> terrains,
		IReadOnlyDictionary<ImprovementEnum, string> improvements,
		IReadOnlyDictionary<WonderEnum, string> wonders,
		IReadOnlyDictionary<int, string> nations)
	{
		ArgumentNullException.ThrowIfNull(units);
		ArgumentNullException.ThrowIfNull(terrains);
		ArgumentNullException.ThrowIfNull(improvements);
		ArgumentNullException.ThrowIfNull(wonders);
		ArgumentNullException.ThrowIfNull(nations);

		this.units = new Dictionary<UnitTypeEnum, string>(units);
		this.terrains = new Dictionary<TerrainTypeEnum, string>(terrains);
		this.improvements =
			new Dictionary<ImprovementEnum, string>(improvements);
		this.wonders = new Dictionary<WonderEnum, string>(wonders);
		this.nations = new Dictionary<int, string>(nations);
	}

	public bool TryGetUnit(UnitTypeEnum type, out string name)
	{
		return this.units.TryGetValue(type, out name!);
	}

	public bool TryGetTerrain(TerrainTypeEnum type, out string name)
	{
		return this.terrains.TryGetValue(type, out name!);
	}

	public bool TryGetImprovement(ImprovementEnum type, out string name)
	{
		return this.improvements.TryGetValue(type, out name!);
	}

	public bool TryGetWonder(WonderEnum type, out string name)
	{
		return this.wonders.TryGetValue(type, out name!);
	}

	public bool TryGetNation(int nationalityID, out string name)
	{
		return this.nations.TryGetValue(nationalityID, out name!);
	}
}

internal sealed class ClassicLanguagePackException : Exception
{
	public ClassicLanguagePackException(string message)
		: base(message)
	{
	}

	public ClassicLanguagePackException(string message, Exception innerException)
		: base(message, innerException)
	{
	}
}
