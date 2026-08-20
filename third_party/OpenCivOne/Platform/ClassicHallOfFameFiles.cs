using OpenCivOne.Runtime;

namespace OpenCivOne.Platform;

/// <summary>
/// Persists the fixed-size Classic Hall of Fame without ever exposing a
/// partially written FAME.DTA to the next game start.
/// </summary>
public sealed class ClassicHallOfFameFiles
{
	public const int FileLength = 0x114;

	private const string FileName = "FAME.DTA";

	private readonly ClassicRuntimeOptions options;
	private readonly Action<string, string> promoteTemporaryFile;

	public ClassicHallOfFameFiles(ClassicRuntimeOptions options)
		: this(
			options,
			static (temporaryPath, finalPath) =>
				File.Move(
					temporaryPath,
					finalPath,
					overwrite: true))
	{
	}

	internal ClassicHallOfFameFiles(
		ClassicRuntimeOptions options,
		Action<string, string> promoteTemporaryFile)
	{
		this.options =
			options ?? throw new ArgumentNullException(nameof(options));
		this.promoteTemporaryFile =
			promoteTemporaryFile ??
			throw new ArgumentNullException(
				nameof(promoteTemporaryFile));
	}

	public bool TryRead(Span<byte> destination)
	{
		if (destination.Length != FileLength)
		{
			throw new ArgumentException(
				$"The Classic Hall of Fame buffer must contain exactly {FileLength} bytes.",
				nameof(destination));
		}

		string path = new ClassicRuntimeFileResolver(
			this.options)
			.Resolve(
				FileName,
				FileMode.Open,
				FileAccess.Read);
		byte[] completeContents =
			new byte[FileLength];

		try
		{
			using FileStream stream = new(
				path,
				FileMode.Open,
				FileAccess.Read,
				FileShare.Read);
			if (stream.Length != FileLength)
			{
				return false;
			}

			stream.ReadExactly(completeContents);
		}
		catch (IOException)
		{
			return false;
		}
		catch (UnauthorizedAccessException)
		{
			return false;
		}

		completeContents.CopyTo(destination);
		return true;
	}

	public void Write(ReadOnlySpan<byte> contents)
	{
		if (contents.Length != FileLength)
		{
			throw new ArgumentException(
				$"The Classic Hall of Fame must contain exactly {FileLength} bytes.",
				nameof(contents));
		}

		Directory.CreateDirectory(this.options.SavePath);
		string finalPath =
			this.options.GetSaveFilePath(FileName);
		string temporaryPath =
			this.options.GetSaveFilePath(
				$".{FileName}.{Guid.NewGuid():N}.tmp");

		try
		{
			using (FileStream stream = new(
				temporaryPath,
				FileMode.CreateNew,
				FileAccess.Write,
				FileShare.None))
			{
				stream.Write(contents);
				stream.Flush(flushToDisk: true);
			}

			// Both paths are in the save directory, so the platform rename
			// replaces the old complete file atomically on the same volume.
			this.promoteTemporaryFile(
				temporaryPath,
				finalPath);
		}
		finally
		{
			TryDeleteTemporaryFile(temporaryPath);
		}
	}

	private static void TryDeleteTemporaryFile(string path)
	{
		try
		{
			File.Delete(path);
		}
		catch (IOException)
		{
		}
		catch (UnauthorizedAccessException)
		{
		}
	}
}
