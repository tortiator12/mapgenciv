namespace OpenCivOne.Platform;

/// <summary>
/// Identifies the legacy Classic save pair and its optional Project1991
/// metadata sidecar on one storage side.
/// </summary>
public readonly record struct ClassicSaveBundlePaths(
	string StatePath,
	string MapPath,
	string MetadataPath,
	bool UsesSaveDirectory)
{
	public ClassicSavePairPaths Pair =>
		new(this.StatePath, this.MapPath, this.UsesSaveDirectory);
}
