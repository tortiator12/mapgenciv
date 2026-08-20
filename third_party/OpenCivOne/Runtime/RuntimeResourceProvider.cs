using System.Collections.Frozen;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace OpenCivOne.Runtime;

/// <summary>
/// Identifies whether runtime resources come from legally owned original data
/// or from a separately licensed Project1991-compatible pack.
/// </summary>
public enum RuntimeResourceSourceKind
{
	OwnerData = 0,
	FirstPartyPack = 1,
}

/// <summary>
/// Resolves the DOS-compatible logical file names consumed by OpenCivOne.
/// Providers expose immutable files only; saves and logs use separate paths.
/// </summary>
public interface IRuntimeResourceProvider
{
	RuntimeResourceSourceKind SourceKind { get; }

	string RootPath { get; }

	IReadOnlyCollection<string> AvailableFileNames { get; }

	bool TryGetFilePath(string fileName, out string? filePath);

	string GetFilePath(string fileName);
}

/// <summary>
/// Compatibility provider for the owner's legal Civilization data directory.
/// </summary>
public sealed class OwnerDataRuntimeResourceProvider :
	IRuntimeResourceProvider
{
	public OwnerDataRuntimeResourceProvider(string rootPath)
	{
		RootPath = RuntimeResourcePath.NormalizeDirectory(
			rootPath,
			nameof(rootPath));
	}

	public RuntimeResourceSourceKind SourceKind =>
		RuntimeResourceSourceKind.OwnerData;

	public string RootPath { get; }

	public IReadOnlyCollection<string> AvailableFileNames =>
		Directory.Exists(RootPath)
			? Array.AsReadOnly(
				Directory
					.EnumerateFiles(RootPath, "*", SearchOption.TopDirectoryOnly)
					.Select(Path.GetFileName)
					.Where(static fileName => fileName is not null)
					.Cast<string>()
					.ToArray())
			: [];

	public string GetFilePath(string fileName) =>
		Path.Combine(
			RootPath,
			RuntimeResourcePath.ValidateLeafFileName(fileName));

	public bool TryGetFilePath(string fileName, out string? filePath)
	{
		filePath = GetFilePath(fileName);
		return true;
	}
}

/// <summary>
/// Resolves a manifest-declared, distributable replacement resource pack.
/// Loading is explicit: the runtime never scans owner folders for this pack.
/// </summary>
public sealed class FirstPartyRuntimeResourceProvider :
	IRuntimeResourceProvider,
	IDisposable
{
	public const string ManifestFileName =
		"project1991-runtime-resource-pack.json";

	private const int MaximumResourceCount = 160;

	private readonly FrozenDictionary<string, SnapshotResource> resources;
	private readonly IReadOnlyCollection<string> availableFileNames;
	private readonly List<FileStream> snapshotLocks;
	private readonly object lifecycleLock = new();
	private bool disposed;
	private bool snapshotLocksDisposed;
	private bool snapshotCleanupCompleted;

	private FirstPartyRuntimeResourceProvider(
		string rootPath,
		string id,
		string version,
		string license,
		Dictionary<string, SnapshotResource> resources,
		List<FileStream> snapshotLocks)
	{
		RootPath = rootPath;
		Id = id;
		Version = version;
		License = license;
		this.resources = resources.ToFrozenDictionary(
			StringComparer.OrdinalIgnoreCase);
		this.snapshotLocks = snapshotLocks;
		availableFileNames = Array.AsReadOnly(
			resources.Keys
				.Order(StringComparer.OrdinalIgnoreCase)
				.ToArray());
	}

	~FirstPartyRuntimeResourceProvider()
	{
		Dispose(disposing: false);
	}

	public RuntimeResourceSourceKind SourceKind =>
		RuntimeResourceSourceKind.FirstPartyPack;

	public string RootPath { get; }

	public string Id { get; }

	public string Version { get; }

	public string License { get; }

	public IReadOnlyCollection<string> AvailableFileNames
	{
		get
		{
			ThrowIfDisposed();
			return availableFileNames;
		}
	}

	public static FirstPartyRuntimeResourceProvider Load(string manifestPath)
	{
		ArgumentException.ThrowIfNullOrWhiteSpace(manifestPath);
		string fullManifestPath = Path.GetFullPath(manifestPath);
		if (!File.Exists(fullManifestPath))
		{
			throw new FileNotFoundException(
				"Runtime resource pack manifest was not found.",
				fullManifestPath);
		}
		RejectReparsePoint(fullManifestPath);

		string rootPath = RuntimeResourcePath.NormalizeDirectory(
			Path.GetDirectoryName(fullManifestPath) ??
				throw new InvalidDataException(
					"Runtime resource pack manifest has no parent directory."),
			nameof(manifestPath));
		if (!Path.GetFileName(fullManifestPath).Equals(
			ManifestFileName,
			StringComparison.OrdinalIgnoreCase))
		{
			throw new InvalidDataException(
				$"Runtime resource pack manifest must be named " +
				$"'{ManifestFileName}'.");
		}

		RuntimeResourcePackDocument document;
		try
		{
			document =
				JsonSerializer.Deserialize<RuntimeResourcePackDocument>(
					File.ReadAllText(fullManifestPath),
					new JsonSerializerOptions
					{
						PropertyNameCaseInsensitive = false,
						UnmappedMemberHandling =
							JsonUnmappedMemberHandling.Disallow,
					}) ??
				throw new InvalidDataException(
					"Runtime resource pack manifest is empty.");
		}
		catch (JsonException exception)
		{
			throw new InvalidDataException(
				"Runtime resource pack manifest is not valid JSON.",
				exception);
		}

		if (document.SchemaVersion != 1)
		{
			throw new InvalidDataException(
				$"Unsupported runtime resource pack schema version " +
				$"'{document.SchemaVersion}'.");
		}

		string id = ValidateMetadata(document.Id, "id");
		string version = ValidateMetadata(document.Version, "version");
		string license = ValidateMetadata(document.License, "license");
		if (document.Resources is null ||
			document.Resources.Count is < 1 or > MaximumResourceCount)
		{
			throw new InvalidDataException(
				$"Runtime resource packs require 1 to " +
				$"{MaximumResourceCount} resource entries.");
		}

		Dictionary<string, string> resourcePaths =
			new(StringComparer.OrdinalIgnoreCase);
		foreach (RuntimeResourcePackEntry? entry in document.Resources)
		{
			if (entry is null)
			{
				throw new InvalidDataException(
					"Runtime resource pack contains a null entry.");
			}

			string fileName;
			try
			{
				fileName = RuntimeResourcePath.ValidateLeafFileName(
					entry.FileName);
			}
			catch (ArgumentException exception)
			{
				throw new InvalidDataException(
					"Runtime resource pack contains an invalid logical file name.",
					exception);
			}

			if (!ClassicDataManifest.IsRequiredFileName(fileName))
			{
				throw new InvalidDataException(
					$"Runtime resource '{fileName}' is not an approved " +
					"immutable compatibility resource or mutable seed.");
			}

			string filePath = ResolvePackPath(rootPath, entry.Path);
			if (!Path.GetExtension(filePath).Equals(
				Path.GetExtension(fileName),
				StringComparison.OrdinalIgnoreCase))
			{
				throw new InvalidDataException(
					$"Runtime resource '{fileName}' must keep its " +
					$"DOS-compatible file extension.");
			}

			if (!File.Exists(filePath))
			{
				throw new FileNotFoundException(
					$"Runtime resource '{fileName}' was not found.",
					filePath);
			}
			RejectReparsePointPath(rootPath, filePath);

			if (!resourcePaths.TryAdd(fileName, filePath))
			{
				throw new InvalidDataException(
					$"Duplicate DOS-compatible runtime resource name " +
					$"'{fileName}'.");
			}
		}

		string snapshotRootPath = RuntimeResourcePath.NormalizeDirectory(
			Directory
				.CreateTempSubdirectory("Project1991.RuntimePack.")
				.FullName,
			nameof(manifestPath));
		List<FileStream> snapshotLocks = [];
		try
		{
			Dictionary<string, SnapshotResource> snapshotResources =
				CreateSnapshot(
					snapshotRootPath,
					resourcePaths,
					snapshotLocks);
			return new FirstPartyRuntimeResourceProvider(
				snapshotRootPath,
				id,
				version,
				license,
				snapshotResources,
				snapshotLocks);
		}
		catch
		{
			DisposeLocks(snapshotLocks);
			DeleteSnapshotDirectory(snapshotRootPath);
			throw;
		}
	}

	public string GetFilePath(string fileName)
	{
		ThrowIfDisposed();
		string validatedFileName =
			RuntimeResourcePath.ValidateLeafFileName(fileName);
		if (!resources.TryGetValue(
			validatedFileName,
			out SnapshotResource? resource))
		{
			throw new FileNotFoundException(
				$"Runtime resource pack does not declare " +
				$"'{validatedFileName}'.",
				validatedFileName);
		}

		VerifySnapshotResource(resource);
		return resource.FilePath;
	}

	public bool TryGetFilePath(string fileName, out string? filePath)
	{
		ThrowIfDisposed();
		string validatedFileName =
			RuntimeResourcePath.ValidateLeafFileName(fileName);
		if (!resources.TryGetValue(
			validatedFileName,
			out SnapshotResource? resource))
		{
			filePath = null;
			return false;
		}

		VerifySnapshotResource(resource);
		filePath = resource.FilePath;
		return true;
	}

	public void Dispose()
	{
		Dispose(disposing: true);
	}

	private static string ResolvePackPath(
		string rootPath,
		string? relativePath)
	{
		if (string.IsNullOrWhiteSpace(relativePath) ||
			Path.IsPathFullyQualified(relativePath) ||
			relativePath[0] is '/' or '\\' ||
			relativePath.Contains(':', StringComparison.Ordinal))
		{
			throw new InvalidDataException(
				"Runtime resource paths must be relative pack paths.");
		}

		string[] segments = relativePath.Split(
			['/', '\\'],
			StringSplitOptions.None);
		if (segments.Any(
			static segment =>
				string.IsNullOrWhiteSpace(segment) ||
				segment is "." or ".."))
		{
			throw new InvalidDataException(
				"Runtime resource paths cannot contain empty or traversal segments.");
		}

		string fullPath = Path.GetFullPath(
			Path.Combine(rootPath, Path.Combine(segments)));
		string relativeToRoot = Path.GetRelativePath(rootPath, fullPath);
		if (Path.IsPathRooted(relativeToRoot) ||
			relativeToRoot == ".." ||
			relativeToRoot.StartsWith(
				$"..{Path.DirectorySeparatorChar}",
				StringComparison.Ordinal) ||
			relativeToRoot.StartsWith(
				$"..{Path.AltDirectorySeparatorChar}",
				StringComparison.Ordinal))
		{
			throw new InvalidDataException(
				"Runtime resource path leaves the pack directory.");
		}

		return fullPath;
	}

	private static void RejectReparsePointPath(
		string rootPath,
		string filePath)
	{
		RejectReparsePoint(Path.TrimEndingDirectorySeparator(rootPath));
		string relativePath = Path.GetRelativePath(rootPath, filePath);
		string currentPath = Path.TrimEndingDirectorySeparator(rootPath);
		foreach (string segment in relativePath.Split(
			[Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar],
			StringSplitOptions.RemoveEmptyEntries))
		{
			currentPath = Path.Combine(currentPath, segment);
			RejectReparsePoint(currentPath);
		}
	}

	private static void RejectReparsePoint(string path)
	{
		if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
		{
			throw new InvalidDataException(
				"Runtime resource packs cannot use symbolic links or reparse points.");
		}
	}

	private static Dictionary<string, SnapshotResource> CreateSnapshot(
		string snapshotRootPath,
		Dictionary<string, string> sourcePaths,
		List<FileStream> snapshotLocks)
	{
		Dictionary<string, SnapshotResource> snapshotResources =
			new(StringComparer.OrdinalIgnoreCase);
		foreach ((string fileName, string sourcePath) in sourcePaths)
		{
			string snapshotPath = Path.Combine(
				snapshotRootPath,
				fileName.ToUpperInvariant());
			byte[] hash;
			long length;
			using (FileStream source = new(
				sourcePath,
				FileMode.Open,
				FileAccess.Read,
				FileShare.Read))
			using (FileStream destination = new(
				snapshotPath,
				FileMode.CreateNew,
				FileAccess.Write,
				FileShare.None))
			using (IncrementalHash hasher =
				IncrementalHash.CreateHash(HashAlgorithmName.SHA256))
			{
				byte[] buffer = new byte[64 * 1024];
				int read;
				while ((read = source.Read(buffer, 0, buffer.Length)) > 0)
				{
					destination.Write(buffer, 0, read);
					hasher.AppendData(buffer, 0, read);
				}

				destination.Flush(flushToDisk: true);
				hash = hasher.GetHashAndReset();
				length = destination.Length;
			}

			MakeSnapshotFileReadOnly(snapshotPath);
			FileStream snapshotLock = new(
				snapshotPath,
				FileMode.Open,
				FileAccess.Read,
				FileShare.Read);
			snapshotLocks.Add(snapshotLock);
			SnapshotResource resource = new(
				snapshotPath,
				length,
				hash);
			VerifySnapshotResource(resource);
			snapshotResources.Add(fileName, resource);
		}

		return snapshotResources;
	}

	private static void MakeSnapshotFileReadOnly(string filePath)
	{
		if (OperatingSystem.IsWindows())
		{
			File.SetAttributes(
				filePath,
				File.GetAttributes(filePath) | FileAttributes.ReadOnly);
			return;
		}

		File.SetUnixFileMode(
			filePath,
			UnixFileMode.UserRead);
	}

	private static void VerifySnapshotResource(SnapshotResource resource)
	{
		if (!File.Exists(resource.FilePath))
		{
			throw new InvalidDataException(
				"The runtime resource snapshot is no longer available.");
		}

		RejectReparsePoint(resource.FilePath);
		using FileStream stream = new(
			resource.FilePath,
			FileMode.Open,
			FileAccess.Read,
			FileShare.Read);
		if (stream.Length != resource.Length)
		{
			throw new InvalidDataException(
				"The runtime resource snapshot was modified after loading.");
		}

		byte[] actualHash = SHA256.HashData(stream);
		if (!CryptographicOperations.FixedTimeEquals(
			actualHash,
			resource.Sha256))
		{
			throw new InvalidDataException(
				"The runtime resource snapshot failed its integrity check.");
		}
	}

	private static void DisposeLocks(List<FileStream> snapshotLocks)
	{
		foreach (FileStream snapshotLock in snapshotLocks)
		{
			snapshotLock.Dispose();
		}

		snapshotLocks.Clear();
	}

	private static bool DeleteSnapshotDirectory(string snapshotRootPath)
	{
		string directoryPath =
			Path.TrimEndingDirectorySeparator(snapshotRootPath);
		if (!Directory.Exists(directoryPath))
		{
			return true;
		}

		foreach (string filePath in Directory.EnumerateFiles(
			directoryPath,
			"*",
			SearchOption.TopDirectoryOnly))
		{
			try
			{
				if (OperatingSystem.IsWindows())
				{
					File.SetAttributes(filePath, FileAttributes.Normal);
				}
				else
				{
					File.SetUnixFileMode(
						filePath,
						UnixFileMode.UserRead |
						UnixFileMode.UserWrite);
				}
			}
			catch (IOException)
			{
			}
			catch (UnauthorizedAccessException)
			{
			}
		}

		try
		{
			Directory.Delete(directoryPath, recursive: true);
			return true;
		}
		catch (IOException)
		{
			return !Directory.Exists(directoryPath);
		}
		catch (UnauthorizedAccessException)
		{
			return !Directory.Exists(directoryPath);
		}
	}

	private void Dispose(bool disposing)
	{
		bool cleanupCompleted;
		lock (lifecycleLock)
		{
			disposed = true;
			if (!snapshotLocksDisposed)
			{
				DisposeLocks(snapshotLocks);
				snapshotLocksDisposed = true;
			}

			if (!snapshotCleanupCompleted)
			{
				snapshotCleanupCompleted =
					DeleteSnapshotDirectory(RootPath);
			}

			cleanupCompleted = snapshotCleanupCompleted;
		}

		if (cleanupCompleted)
		{
			if (disposing)
			{
				GC.SuppressFinalize(this);
			}

			return;
		}

		if (!disposing)
		{
			// A resource consumer can still hold a read handle after the
			// provider itself becomes unreachable. Re-registering gives the
			// snapshot another cleanup opportunity after that handle closes.
			GC.ReRegisterForFinalize(this);
		}
	}

	private void ThrowIfDisposed()
	{
		ObjectDisposedException.ThrowIf(
			disposed,
			this);
	}

	private static string ValidateMetadata(string? value, string propertyName)
	{
		if (string.IsNullOrWhiteSpace(value) || value.Length > 256)
		{
			throw new InvalidDataException(
				$"Runtime resource pack property '{propertyName}' is invalid.");
		}

		return value;
	}

	private sealed class RuntimeResourcePackDocument
	{
		[JsonPropertyName("$schema")]
		public string? Schema { get; init; }

		[JsonPropertyName("schemaVersion")]
		public int SchemaVersion { get; init; }

		[JsonPropertyName("id")]
		public string? Id { get; init; }

		[JsonPropertyName("version")]
		public string? Version { get; init; }

		[JsonPropertyName("license")]
		public string? License { get; init; }

		[JsonPropertyName("resources")]
		public List<RuntimeResourcePackEntry?>? Resources { get; init; }
	}

	private sealed class RuntimeResourcePackEntry
	{
		[JsonPropertyName("fileName")]
		public string? FileName { get; init; }

		[JsonPropertyName("path")]
		public string? Path { get; init; }
	}

	private sealed record SnapshotResource(
		string FilePath,
		long Length,
		byte[] Sha256);
}

internal static class RuntimeResourcePath
{
	public static string NormalizeDirectory(
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

	public static string ValidateLeafFileName(string? fileName)
	{
		if (string.IsNullOrWhiteSpace(fileName) ||
			fileName.Length > 255 ||
			fileName is "." or ".." ||
			fileName.Any(
				static character =>
					char.IsControl(character) ||
					character is '<' or '>' or '"' or '|' or '?' or '*') ||
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

		return fileName;
	}
}
