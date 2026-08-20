using OpenCivOne.Runtime;

namespace OpenCivOne
{
	public static class ClassicTriremeLossPolicy
	{
		public static bool ShouldSink(
			ClassicAiProfile profile,
			bool hasNavigation,
			bool hasAdjacentLand,
			Func<bool> lossRoll)
		{
			ArgumentNullException.ThrowIfNull(lossRoll);

			if (ClassicAiRuntimeProfiles
					.UsesSmartEnhancements(profile) &&
				hasNavigation)
			{
				return false;
			}

			return !hasAdjacentLand && lossRoll();
		}
	}
}
