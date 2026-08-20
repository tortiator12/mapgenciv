namespace OpenCivOne;

/// <summary>
/// Converts the original personality-weighted settlement threshold into a
/// deterministic 1991+ production target. The original AI path does not call
/// this policy.
/// </summary>
public static class SmartSettlerExpansionPolicy
{
	private const int OriginalDensityDivisor = 16;
	private const int CityGapPerConcurrentSettler = 3;

	public const int MaximumConcurrentSettlers = 3;

	public static SmartSettlerExpansionPlan Calculate(
		int personalityPolicy,
		int buildSiteCount,
		int cityCount)
	{
		int normalizedBuildSites = Math.Max(0, buildSiteCount);
		int normalizedCityCount = Math.Max(0, cityCount);
		int personalityMultiplier =
			Math.Clamp(personalityPolicy + 1, 0, 2);
		int weightedBuildSites =
			personalityMultiplier * normalizedBuildSites;
		bool hasExpansionRoom =
			weightedBuildSites >
			(normalizedCityCount * OriginalDensityDivisor);
		int targetCityCount =
			weightedBuildSites == 0
				? 0
				: (weightedBuildSites +
					OriginalDensityDivisor - 1) /
					OriginalDensityDivisor;
		int cityGap = hasExpansionRoom
			? Math.Max(0, targetCityCount - normalizedCityCount)
			: 0;
		int desiredConcurrentSettlers = cityGap == 0
			? 0
			: Math.Min(
				MaximumConcurrentSettlers,
				Math.Max(
					1,
					(cityGap + CityGapPerConcurrentSettler - 1) /
						CityGapPerConcurrentSettler));

		return new SmartSettlerExpansionPlan(
			personalityPolicy,
			normalizedBuildSites,
			normalizedCityCount,
			targetCityCount,
			cityGap,
			desiredConcurrentSettlers,
			hasExpansionRoom);
	}
}

public readonly record struct SmartSettlerExpansionPlan(
	int PersonalityPolicy,
	int BuildSiteCount,
	int CityCount,
	int TargetCityCount,
	int CityGap,
	int DesiredConcurrentSettlers,
	bool HasExpansionRoom);
