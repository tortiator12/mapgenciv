using System.Text;

namespace OpenCivOne.Platform;

/// <summary>
/// Resolves the tune-to-WAV table recovered from the original
/// Civilization for Windows executable.
/// </summary>
/// <remarks>
/// Only fixed leaf names from the statically verified table are accepted.
/// Files remain in the owner's installation and are only opened read-only.
/// </remarks>
public sealed class CivWinWaveCatalog
{
	internal const long MaximumWaveFileSize = 16 * 1024 * 1024;

	private static readonly IReadOnlyDictionary<short, string> FileNames =
		new Dictionary<short, string>
		{
			[3] = "OPENING.WAV",
			[4] = "OPENING.WAV",
			[5] = "LINC.WAV",
			[6] = "MONT.WAV",
			[7] = "RAMS.WAV",
			[8] = "SHAK.WAV",
			[9] = "NAPO.WAV",
			[10] = "CEAS.WAV",
			[11] = "STAL.WAV",
			[12] = "ALEX.WAV",
			[13] = "ELIZ.WAV",
			[14] = "HAMA.WAV",
			[15] = "MAO.WAV",
			[16] = "GENG.WAV",
			[17] = "GAND.WAV",
			[18] = "FRED.WAV",
			[19] = "LINC.WAV",
			[20] = "MONT.WAV",
			[21] = "RAMS.WAV",
			[22] = "SHAK.WAV",
			[23] = "NAPO.WAV",
			[24] = "CEAS.WAV",
			[25] = "STAL.WAV",
			[26] = "ALEX.WAV",
			[27] = "ELIZ.WAV",
			[28] = "HAMA.WAV",
			[29] = "MAO.WAV",
			[30] = "GENG.WAV",
			[31] = "GAND.WAV",
			[32] = "FRED.WAV",
			[34] = "WINTUNE.WAV",
			[35] = "LOSE2.WAV",
			[37] = "S_BEEP.WAV",
			[38] = "THEY_DIE.WAV",
			[39] = "WE_DIE.WAV",
			[40] = "S_LAND.WAV",
			[41] = "S_LAND.WAV",
			[42] = "AIRNUKE.WAV",
			[43] = "CANNON.WAV",
		};

	public CivWinWaveCatalog(string? directoryPath)
	{
		if (string.IsNullOrWhiteSpace(directoryPath))
		{
			return;
		}

		this.DirectoryPath = NormalizeDirectoryPath(directoryPath);
	}

	public string? DirectoryPath { get; }

	public bool IsConfigured => this.DirectoryPath is not null;

	/// <summary>
	/// The distinct original file names needed for the proven mapping.
	/// </summary>
	public static IReadOnlyCollection<string> RequiredFileNames { get; } =
		FileNames.Values
			.Distinct(StringComparer.OrdinalIgnoreCase)
			.Order(StringComparer.OrdinalIgnoreCase)
			.ToArray();

	public static bool TryGetFileName(short tune, out string fileName)
	{
		return FileNames.TryGetValue(tune, out fileName!);
	}

	public bool TryResolve(short tune, out string filePath)
	{
		if (this.DirectoryPath is null ||
			!TryGetFileName(tune, out string fileName))
		{
			filePath = string.Empty;
			return false;
		}

		filePath = Path.Combine(this.DirectoryPath, fileName);
		return true;
	}

	internal bool TryValidateRequiredFiles(out string failure)
	{
		if (this.DirectoryPath is null)
		{
			failure =
				"No Civilization for Windows WAV directory is configured.";
			return false;
		}

		foreach (string fileName in RequiredFileNames)
		{
			string filePath = Path.Combine(this.DirectoryPath, fileName);
			if (!IsPcmWaveFile(filePath))
			{
				failure =
					$"Required mapped WAV is missing or is not " +
					$"original-format PCM mono/11025 Hz/8-bit audio: " +
					fileName;
				return false;
			}
		}

		failure = string.Empty;
		return true;
	}

	internal static bool IsPcmWaveFile(string filePath)
	{
		try
		{
			using FileStream stream = new(
				filePath,
				FileMode.Open,
				FileAccess.Read,
				FileShare.Read);
			using BinaryReader reader =
				new(stream, Encoding.ASCII, leaveOpen: false);

			if (stream.Length < 44 ||
				stream.Length > MaximumWaveFileSize ||
				ReadFourCc(reader) != "RIFF")
			{
				return false;
			}

			uint riffSize = reader.ReadUInt32();
			if (riffSize + 8L > stream.Length)
			{
				return false;
			}

			if (ReadFourCc(reader) != "WAVE")
			{
				return false;
			}

			bool hasPcmFormat = false;
			bool hasAudioData = false;
			while (stream.Position + 8 <= stream.Length)
			{
				string chunkId = ReadFourCc(reader);
				uint chunkSize = reader.ReadUInt32();
				long chunkEnd = stream.Position + chunkSize;
				if (chunkEnd < stream.Position ||
					chunkEnd > stream.Length)
				{
					return false;
				}

				if (chunkId == "fmt " && chunkSize >= 16)
				{
					ushort format = reader.ReadUInt16();
					ushort channels = reader.ReadUInt16();
					uint sampleRate = reader.ReadUInt32();
					_ = reader.ReadUInt32();
					_ = reader.ReadUInt16();
					ushort bitsPerSample = reader.ReadUInt16();
					hasPcmFormat =
						format == 1 &&
						channels == 1 &&
						sampleRate == 11025 &&
						bitsPerSample == 8;
				}
				else if (chunkId == "data")
				{
					hasAudioData = chunkSize > 0;
				}

				long paddedEnd = chunkEnd + (chunkSize & 1);
				if (paddedEnd > stream.Length)
				{
					// Some original CivWin files end on an odd-sized data
					// chunk without the optional RIFF padding byte. Their
					// RIFF size still matches the physical file exactly and
					// Windows accepts them. Only permit that omission at EOF.
					if (chunkEnd != stream.Length)
					{
						return false;
					}

					paddedEnd = chunkEnd;
				}

				stream.Position = paddedEnd;
			}

			return hasPcmFormat && hasAudioData;
		}
		catch (IOException)
		{
			return false;
		}
		catch (UnauthorizedAccessException)
		{
			return false;
		}
	}

	private static string ReadFourCc(BinaryReader reader)
	{
		byte[] bytes = reader.ReadBytes(4);
		return bytes.Length == 4
			? Encoding.ASCII.GetString(bytes)
			: string.Empty;
	}

	private static string NormalizeDirectoryPath(string directoryPath)
	{
		string fullPath = Path.GetFullPath(directoryPath);
		return Path.EndsInDirectorySeparator(fullPath)
			? fullPath
			: $"{fullPath}{Path.DirectorySeparatorChar}";
	}
}
