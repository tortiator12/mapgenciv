namespace OpenCivOne.Localization;

/// <summary>
/// Localized display names for the compact Classic map surface.
/// Canonical game data and serialized owner names stay unchanged.
/// </summary>
public static class ClassicDisplayNames
{
	public static string Unit(
		UnitTypeEnum type,
		string originalName,
		ClassicGameTextCatalog? catalog = null)
	{
		ClassicGameTextCatalog selectedCatalog =
			catalog ?? ClassicGameText.Current;
		return selectedCatalog.TryGetUnitDisplayName(
			type,
			out string? translated)
				? translated
				: originalName;
	}

	public static string Terrain(
		TerrainTypeEnum type,
		string originalName,
		ClassicGameTextCatalog? catalog = null)
	{
		ClassicGameTextCatalog selectedCatalog =
			catalog ?? ClassicGameText.Current;
		return selectedCatalog.TryGetTerrainDisplayName(
			type,
			out string? translated)
				? translated
				: originalName;
	}

	public static string Improvement(
		ImprovementEnum type,
		string originalName,
		ClassicGameTextCatalog? catalog = null)
	{
		ClassicGameTextCatalog selectedCatalog =
			catalog ?? ClassicGameText.Current;
		return selectedCatalog.TryGetImprovementDisplayName(
			type,
			out string? translated)
				? translated
				: originalName;
	}

	public static string Wonder(
		WonderEnum type,
		string originalName,
		ClassicGameTextCatalog? catalog = null)
	{
		ClassicGameTextCatalog selectedCatalog =
			catalog ?? ClassicGameText.Current;
		return selectedCatalog.TryGetWonderDisplayName(
			type,
			out string? translated)
				? translated
				: originalName;
	}

	/// <summary>
	/// Resolves the original combined production identifier where city
	/// improvements occupy 1..24 and wonders occupy 25..45.
	/// </summary>
	public static string ImprovementOrWonder(
		int combinedTypeID,
		string originalName,
		ClassicGameTextCatalog? catalog = null)
	{
		if (combinedTypeID >= (int)ImprovementEnum.Palace &&
			combinedTypeID <= (int)ImprovementEnum.SSModule)
		{
			return Improvement(
				(ImprovementEnum)combinedTypeID,
				originalName,
				catalog);
		}

		int wonderID =
			combinedTypeID - (int)ImprovementEnum.SSModule;
		if (wonderID >= (int)WonderEnum.Pyramids &&
			wonderID <= (int)WonderEnum.CureForCancer)
		{
			return Wonder(
				(WonderEnum)wonderID,
				originalName,
				catalog);
		}

		return originalName;
	}

	public static string Nation(
		int nationalityID,
		string currentName,
		string canonicalName,
		ClassicGameTextCatalog? catalog = null)
	{
		if (!string.Equals(
				currentName,
				canonicalName,
				StringComparison.Ordinal))
		{
			return currentName;
		}

		ClassicGameTextCatalog selectedCatalog =
			catalog ?? ClassicGameText.Current;
		return selectedCatalog.TryGetNationDisplayName(
			nationalityID,
			out string? translated)
				? translated
				: currentName;
	}
}
