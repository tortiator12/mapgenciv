using OpenCivOne.Runtime;

namespace OpenCivOne.Platform;

/// <summary>
/// Resolves legacy DOS file requests without allowing the emulated game to
/// write into the legally supplied, read-only Civilization resource directory.
/// </summary>
public sealed class ClassicRuntimeFileResolver
{
	private static readonly HashSet<string> WritableFileNames =
		new(StringComparer.OrdinalIgnoreCase)
		{
			"FAME.DTA",
			"REPLAY.TXT"
		};

	private readonly ClassicRuntimeOptions options;

	public ClassicRuntimeFileResolver(ClassicRuntimeOptions options)
	{
		this.options =
			options ?? throw new ArgumentNullException(nameof(options));
	}

	public string Resolve(string fileName, FileAccess access)
	{
		return Resolve(fileName, FileMode.Open, access);
	}

	public string Resolve(
		string fileName,
		FileMode mode,
		FileAccess access)
	{
		if (string.IsNullOrWhiteSpace(fileName))
		{
			throw new ArgumentException(
				"A runtime file name is required.",
				nameof(fileName));
		}

		bool isReadOnlyOpen =
			mode == FileMode.Open && access == FileAccess.Read;
		bool isWritableRuntimeFile = IsWritableRuntimeFile(fileName);

		if (isReadOnlyOpen)
		{
			if (isWritableRuntimeFile)
			{
				string saveFilePath =
					this.options.GetSaveFilePath(fileName);
				if (File.Exists(saveFilePath))
				{
					return saveFilePath;
				}
			}

			return this.options.GetResourceFilePath(fileName);
		}

		if (!isWritableRuntimeFile)
		{
			throw new UnauthorizedAccessException(
				$"Mutating '{fileName}' outside the save directory is not permitted.");
		}

		string mutableFilePath = this.options.GetSaveFilePath(fileName);
		if (fileName.Equals(
				"FAME.DTA",
				StringComparison.OrdinalIgnoreCase) &&
			ModeNeedsExistingContents(mode) &&
			!File.Exists(mutableFilePath))
		{
			SeedMutableFileFromResources(fileName, mutableFilePath);
		}

		return mutableFilePath;
	}

	// This allow-list is intentionally closed. A newly discovered mutable DOS
	// file must be source-audited and added explicitly; unknown writes fail
	// instead of falling back to the original resource directory.
	private static bool IsWritableRuntimeFile(string fileName)
	{
		if (WritableFileNames.Contains(fileName))
		{
			return true;
		}

		string extension = Path.GetExtension(fileName);
		return extension.Equals(".SVE", StringComparison.OrdinalIgnoreCase) ||
			extension.Equals(".MAP", StringComparison.OrdinalIgnoreCase);
	}

	private static bool ModeNeedsExistingContents(FileMode mode)
	{
		return mode is
			FileMode.Open or
			FileMode.OpenOrCreate or
			FileMode.Append;
	}

	private void SeedMutableFileFromResources(
		string fileName,
		string saveFilePath)
	{
		string resourceFilePath =
			this.options.GetResourceFilePath(fileName);
		if (!File.Exists(resourceFilePath))
		{
			return;
		}

		Directory.CreateDirectory(this.options.SavePath);
		string temporaryPath = Path.Combine(
			this.options.SavePath,
			$".{fileName}.seed-{Guid.NewGuid():N}.tmp");

		try
		{
			using (FileStream source = new(
				resourceFilePath,
				FileMode.Open,
				FileAccess.Read,
				FileShare.Read))
			using (FileStream destination = new(
				temporaryPath,
				FileMode.CreateNew,
				FileAccess.Write,
				FileShare.None))
			{
				source.CopyTo(destination);
				destination.Flush(flushToDisk: true);
			}

			try
			{
				File.Move(
					temporaryPath,
					saveFilePath,
					overwrite: false);
			}
			catch (IOException) when (File.Exists(saveFilePath))
			{
				// Another runtime thread or process won the copy-on-write race.
				// Its complete save copy is the authoritative mutable file.
			}
		}
		finally
		{
			if (File.Exists(temporaryPath))
			{
				try
				{
					File.Delete(temporaryPath);
				}
				catch (IOException)
				{
				}
				catch (UnauthorizedAccessException)
				{
				}
			}
		}
	}
}
