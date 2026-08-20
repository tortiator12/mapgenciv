namespace OpenCivOne.Runtime;

/// <summary>
/// Defines the runtime boundary between the original 1991 behavior and
/// explicitly selected Project1991 enhancements.
/// </summary>
public static class ClassicAiRuntimeProfiles
{
	public static bool IsSupported(ClassicAiProfile profile) =>
		profile is
			ClassicAiProfile.Classic1991 or
			ClassicAiProfile.Smart1991Plus;

	public static bool UsesSmartEnhancements(ClassicAiProfile profile) =>
		profile == ClassicAiProfile.Smart1991Plus;
}
