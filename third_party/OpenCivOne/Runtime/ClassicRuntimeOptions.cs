using System.Reflection;

namespace OpenCivOne.Runtime;

/// <summary>
/// Immutable, platform-neutral locations used by the Classic runtime.
/// The original Civilization data is always separate from mutable runtime data.
/// </summary>
public sealed record ClassicRuntimeOptions
{
	public ClassicRuntimeOptions(
		string ResourcePath,
		string SavePath,
		string LogPath)
		: this(ResourcePath, SavePath, LogPath, null)
	{
	}

	public ClassicRuntimeOptions(
		string ResourcePath,
		string SavePath,
		string LogPath,
		string? CivWinPath)
		: this(
			new OwnerDataRuntimeResourceProvider(ResourcePath),
			SavePath,
			LogPath,
			CivWinPath)
	{
	}

	public ClassicRuntimeOptions(
		IRuntimeResourceProvider ResourceProvider,
		string SavePath,
		string LogPath)
		: this(ResourceProvider, SavePath, LogPath, null)
	{
	}

	public ClassicRuntimeOptions(
		IRuntimeResourceProvider ResourceProvider,
		string SavePath,
		string LogPath,
		string? CivWinPath)
	{
		this.ResourceProvider =
			ResourceProvider ??
			throw new ArgumentNullException(nameof(ResourceProvider));
		this.ResourcePath = this.ResourceProvider.RootPath;
		this.SavePath = NormalizeDirectoryPath(SavePath, nameof(SavePath));
		this.LogPath = NormalizeDirectoryPath(LogPath, nameof(LogPath));
		this.CivWinPath = string.IsNullOrWhiteSpace(CivWinPath)
			? null
			: NormalizeDirectoryPath(CivWinPath, nameof(CivWinPath));

		EnsureWritablePathIsOutsideResources(
			this.ResourcePath,
			this.SavePath,
			nameof(SavePath));
		EnsureWritablePathIsOutsideResources(
			this.ResourcePath,
			this.LogPath,
			nameof(LogPath));
		EnsureDirectoryTreesAreSeparate(
			this.SavePath,
			this.LogPath,
			nameof(LogPath));
		if (this.CivWinPath is not null)
		{
			EnsureDirectoryTreesAreSeparate(
				this.CivWinPath,
				this.ResourcePath,
				nameof(CivWinPath));
			EnsureDirectoryTreesAreSeparate(
				this.CivWinPath,
				this.SavePath,
				nameof(CivWinPath));
			EnsureDirectoryTreesAreSeparate(
				this.CivWinPath,
				this.LogPath,
				nameof(CivWinPath));
		}
	}

	public string ResourcePath { get; }

	public IRuntimeResourceProvider ResourceProvider { get; }

	public string SavePath { get; }

	public string LogPath { get; }

	/// <summary>
	/// Optional read-only location of the owner's Civilization for Windows
	/// installation. Audio is streamed from this directory and is never
	/// copied into Project1991.
	/// </summary>
	public string? CivWinPath { get; }

	public static ClassicRuntimeOptions CreateDesktopDefault()
	{
		string userProfilePath =
			Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
		string? configuredResourcePath =
			Environment.GetEnvironmentVariable("PROJECT1991_CIV1_PATH");
		string resourcePath;

		if (!string.IsNullOrWhiteSpace(configuredResourcePath))
		{
			resourcePath = configuredResourcePath;
		}
		else
		{
#if DEBUG
			resourcePath = Environment.OSVersion.Platform == PlatformID.Win32NT
				? $"C:{Path.DirectorySeparatorChar}Dos{Path.DirectorySeparatorChar}Civ1"
				: Path.Combine(userProfilePath, "Dos", "Civ1");
#else
			resourcePath =
				Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location)
				?? AppContext.BaseDirectory;
#endif
		}

		string mainPath =
			Path.Combine(
				userProfilePath,
				"Games",
				"Project1991",
				"Classic");
		string? civWinPath =
			Environment.GetEnvironmentVariable("PROJECT1991_CIVWIN_PATH");

		return new ClassicRuntimeOptions(
			resourcePath,
			Path.Combine(mainPath, "Saves"),
			Path.Combine(mainPath, "Logs"),
			civWinPath);
	}

	public string GetResourceFilePath(string fileName)
	{
		return this.ResourceProvider.GetFilePath(
			RuntimeResourcePath.ValidateLeafFileName(fileName));
	}

	public bool TryGetResourceFilePath(
		string fileName,
		out string? filePath)
	{
		return this.ResourceProvider.TryGetFilePath(
			RuntimeResourcePath.ValidateLeafFileName(fileName),
			out filePath);
	}

	public string GetSaveFilePath(string fileName)
	{
		return CombineLeafFile(this.SavePath, fileName);
	}

	public string GetLogFilePath(string fileName)
	{
		return CombineLeafFile(this.LogPath, fileName);
	}

	public string GetCivWinFilePath(string fileName)
	{
		if (this.CivWinPath is null)
		{
			throw new InvalidOperationException(
				"No Civilization for Windows directory is configured.");
		}

		return CombineLeafFile(this.CivWinPath, fileName);
	}

	private static string NormalizeDirectoryPath(
		string path,
		string parameterName)
	{
		if (string.IsNullOrWhiteSpace(path))
		{
			throw new ArgumentException(
				"A directory path is required.",
				parameterName);
		}

		string fullPath = Path.GetFullPath(path);
		return Path.EndsInDirectorySeparator(fullPath)
			? fullPath
			: $"{fullPath}{Path.DirectorySeparatorChar}";
	}

	private static void EnsureWritablePathIsOutsideResources(
		string resourcePath,
		string writablePath,
		string parameterName)
	{
		EnsureDirectoryTreesAreSeparate(
			resourcePath,
			writablePath,
			parameterName);
	}

	private static void EnsureDirectoryTreesAreSeparate(
		string firstPath,
		string secondPath,
		string parameterName)
	{
		if (IsSameOrDescendant(firstPath, secondPath) ||
			IsSameOrDescendant(secondPath, firstPath))
		{
			throw new ArgumentException(
				"Classic resources, saves, and logs must use separate directory trees.",
				parameterName);
		}
	}

	private static bool IsSameOrDescendant(
		string parentPath,
		string candidatePath)
	{
		string relativePath = Path.GetRelativePath(parentPath, candidatePath);
		return relativePath == "." ||
			(!Path.IsPathRooted(relativePath) &&
			 relativePath != ".." &&
			 !relativePath.StartsWith(
				 $"..{Path.DirectorySeparatorChar}",
				 StringComparison.Ordinal) &&
			 !relativePath.StartsWith(
				 $"..{Path.AltDirectorySeparatorChar}",
				 StringComparison.Ordinal));
	}

	private static string CombineLeafFile(string directoryPath, string fileName)
	{
		if (string.IsNullOrWhiteSpace(fileName) ||
			fileName is "." or ".." ||
			fileName.IndexOfAny(
				[
					Path.DirectorySeparatorChar,
					Path.AltDirectorySeparatorChar,
					'\\',
					'/',
					':'
				]) >= 0)
		{
			throw new ArgumentException(
				"A plain file name without a directory is required.",
				nameof(fileName));
		}

		return Path.Combine(directoryPath, fileName);
	}
}
