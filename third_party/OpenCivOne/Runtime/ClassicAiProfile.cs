namespace OpenCivOne.Runtime;

public enum ClassicAiProfile
{
	Classic1991 = 0,
	Smart1991Plus = 1,
}

public static class ClassicAiProfileIds
{
	public const string Classic1991 = "classic-1991";

	public const string Smart1991Plus = "smart-1991-plus";

	public static string ToStableId(ClassicAiProfile profile) =>
		profile switch
		{
			ClassicAiProfile.Classic1991 => Classic1991,
			ClassicAiProfile.Smart1991Plus => Smart1991Plus,
			_ => throw new ArgumentOutOfRangeException(
				nameof(profile),
				profile,
				"AI profile is not supported."),
		};

	public static bool TryParseStableId(
		string? stableId,
		out ClassicAiProfile profile)
	{
		switch (stableId)
		{
			case Classic1991:
				profile = ClassicAiProfile.Classic1991;
				return true;
			case Smart1991Plus:
				profile = ClassicAiProfile.Smart1991Plus;
				return true;
			default:
				profile = default;
				return false;
		}
	}
}

public static class ClassicRuntimeCompatibilityIds
{
	public const string Current =
		"opencivone-classic-runtime-v1";
}
