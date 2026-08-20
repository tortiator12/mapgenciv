namespace OpenCivOne.Platform;

public enum ClassicSaveBundlePresence
{
	Empty,
	Incomplete,
	Complete,
}

public readonly record struct ClassicSaveBundleInspection(
	ClassicSaveBundlePresence Presence,
	ClassicSaveBundlePaths Bundle);
