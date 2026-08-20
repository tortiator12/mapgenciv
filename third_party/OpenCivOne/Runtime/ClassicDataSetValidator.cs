namespace OpenCivOne.Runtime;

[Flags]
public enum ClassicDataPathProblem
{
	None = 0,
	EmptyPath = 1,
	AbsolutePath = 2,
	TraversalSegment = 4,
	EmptySegment = 8,
}

public readonly record struct ClassicDataPathIssue(
	string? RelativePath,
	ClassicDataPathProblem Problems);

public sealed record ClassicDataNameCollision(
	string NormalizedRelativePath,
	IReadOnlyList<string> RelativePaths);

public sealed class ClassicDataValidationResult
{
	internal ClassicDataValidationResult(
		IEnumerable<string> missingRequiredFileNames,
		IEnumerable<ClassicDataPathIssue> invalidPaths,
		IEnumerable<ClassicDataNameCollision> nameCollisions)
	{
		MissingRequiredFileNames =
			Array.AsReadOnly(missingRequiredFileNames.ToArray());
		InvalidPaths = Array.AsReadOnly(invalidPaths.ToArray());
		NameCollisions = Array.AsReadOnly(nameCollisions.ToArray());
	}

	public bool IsValid =>
		MissingRequiredFileNames.Count == 0 &&
		InvalidPaths.Count == 0 &&
		NameCollisions.Count == 0;

	public IReadOnlyList<string> MissingRequiredFileNames { get; }

	public IReadOnlyList<ClassicDataPathIssue> InvalidPaths { get; }

	public IReadOnlyList<ClassicDataNameCollision> NameCollisions { get; }
}

/// <summary>
/// Validates imported relative path metadata without accessing any files.
/// </summary>
public static class ClassicDataSetValidator
{
	private static readonly char[] DirectorySeparators = ['/', '\\'];

	public static ClassicDataValidationResult Validate(
		IEnumerable<string?> relativePaths)
	{
		ArgumentNullException.ThrowIfNull(relativePaths);

		List<ClassicDataPathIssue> invalidPaths = [];
		Dictionary<string, List<string>> normalizedPaths =
			new(StringComparer.OrdinalIgnoreCase);
		HashSet<string> presentRequiredFileNames =
			new(StringComparer.OrdinalIgnoreCase);

		foreach (string? relativePath in relativePaths)
		{
			ClassicDataPathProblem problems = InspectPath(relativePath);
			if (problems != ClassicDataPathProblem.None)
			{
				invalidPaths.Add(new ClassicDataPathIssue(relativePath, problems));
				continue;
			}

			string[] segments = SplitPath(relativePath!);
			string normalizedPath = string.Join('/', segments);
			if (!normalizedPaths.TryGetValue(
				normalizedPath,
				out List<string>? matchingPaths))
			{
				matchingPaths = [];
				normalizedPaths.Add(normalizedPath, matchingPaths);
			}

			matchingPaths.Add(relativePath!);
			if (segments.Length == 1 &&
				ClassicDataManifest.IsRequiredFileName(segments[0]))
			{
				presentRequiredFileNames.Add(segments[0]);
			}
		}

		IEnumerable<string> missingRequiredFileNames =
			ClassicDataManifest
				.EnumerateCanonicalRequiredFileNames()
				.Where(fileName => !presentRequiredFileNames.Contains(fileName));
		IEnumerable<ClassicDataNameCollision> nameCollisions =
			normalizedPaths
				.Where(entry => entry.Value.Count > 1)
				.Select(entry => new ClassicDataNameCollision(
					entry.Key,
					Array.AsReadOnly(entry.Value.ToArray())));

		return new ClassicDataValidationResult(
			missingRequiredFileNames,
			invalidPaths,
			nameCollisions);
	}

	private static ClassicDataPathProblem InspectPath(string? relativePath)
	{
		if (string.IsNullOrWhiteSpace(relativePath))
		{
			return ClassicDataPathProblem.EmptyPath;
		}

		ClassicDataPathProblem problems = ClassicDataPathProblem.None;
		if (IsAbsoluteOrRooted(relativePath))
		{
			problems |= ClassicDataPathProblem.AbsolutePath;
		}

		string[] segments = SplitPath(relativePath);
		if (segments.Any(string.IsNullOrWhiteSpace))
		{
			problems |= ClassicDataPathProblem.EmptySegment;
		}

		if (segments.Any(segment => segment is "." or ".."))
		{
			problems |= ClassicDataPathProblem.TraversalSegment;
		}

		return problems;
	}

	private static bool IsAbsoluteOrRooted(string path)
	{
		if (path[0] is '/' or '\\')
		{
			return true;
		}

		int firstSeparator = path.IndexOfAny(DirectorySeparators);
		int firstColon = path.IndexOf(':');
		return firstColon >= 0 &&
			(firstSeparator < 0 || firstColon < firstSeparator);
	}

	private static string[] SplitPath(string path) =>
		path.Split(DirectorySeparators, StringSplitOptions.None);
}
