namespace OpenCivOne
{
	public readonly record struct ClassicEconomyAllocation(
		int TaxRate,
		int ScienceRate,
		int LuxuryRate);

	public static class ClassicEconomyRatePolicy
	{
		public const int TotalRate = 10;

		public static bool TryReadStoredRates(
			int taxRate,
			int scienceRate,
			out ClassicEconomyAllocation allocation)
		{
			return TryCreate(
				taxRate,
				scienceRate,
				TotalRate - taxRate - scienceRate,
				out allocation);
		}

		public static bool TrySelectTaxRate(
			int currentTaxRate,
			int currentScienceRate,
			int selectedTaxRate,
			out ClassicEconomyAllocation allocation)
		{
			if (!TryReadStoredRates(
				currentTaxRate,
				currentScienceRate,
				out ClassicEconomyAllocation currentAllocation))
			{
				allocation = default;
				return false;
			}

			int taxAndScienceRate =
				currentAllocation.TaxRate + currentAllocation.ScienceRate;

			return TryCreate(
				selectedTaxRate,
				taxAndScienceRate - selectedTaxRate,
				currentAllocation.LuxuryRate,
				out allocation);
		}

		public static bool TrySelectLuxuryRate(
			int currentTaxRate,
			int selectedLuxuryRate,
			out ClassicEconomyAllocation allocation)
		{
			return TryCreate(
				currentTaxRate,
				TotalRate - currentTaxRate - selectedLuxuryRate,
				selectedLuxuryRate,
				out allocation);
		}

		private static bool TryCreate(
			int taxRate,
			int scienceRate,
			int luxuryRate,
			out ClassicEconomyAllocation allocation)
		{
			if (taxRate < 0 || taxRate > TotalRate ||
				scienceRate < 0 || scienceRate > TotalRate ||
				luxuryRate < 0 || luxuryRate > TotalRate ||
				taxRate + scienceRate + luxuryRate != TotalRate)
			{
				allocation = default;
				return false;
			}

			allocation = new ClassicEconomyAllocation(
				taxRate,
				scienceRate,
				luxuryRate);
			return true;
		}
	}
}
