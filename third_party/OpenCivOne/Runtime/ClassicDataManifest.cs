using System.Collections.Frozen;

namespace OpenCivOne.Runtime;

public enum ClassicDataFileCategory
{
	GraphicsPaletteOrFont = 0,
	TextOrHelp = 1,
	GameplayData = 2,
	MutableRuntimeSeed = 3,
	LegacyExecutableMarker = 4,
}

/// <summary>
/// Describes the original data files required to start the Classic runtime.
/// The manifest contains names only and never reads original game data.
/// </summary>
public static class ClassicDataManifest
{
	private static readonly string[] CanonicalRequiredFileNames =
	[
		"ADSCREEN.PIC",
		"ARCH.PIC",
		"BACK0A.PAL",
		"BACK0A.PIC",
		"BACK0M.PAL",
		"BACK0M.PIC",
		"BACK1A.PAL",
		"BACK1A.PIC",
		"BACK1M.PAL",
		"BACK1M.PIC",
		"BACK2A.PAL",
		"BACK2A.PIC",
		"BACK2M.PAL",
		"BACK2M.PIC",
		"BACK3A.PAL",
		"BACK3A.PIC",
		"BIRTH0.PAL",
		"BIRTH0.PIC",
		"BIRTH1.PAL",
		"BIRTH1.PIC",
		"BIRTH2.PAL",
		"BIRTH2.PIC",
		"BIRTH3.PAL",
		"BIRTH3.PIC",
		"BIRTH4.PAL",
		"BIRTH4.PIC",
		"BIRTH5.PAL",
		"BIRTH5.PIC",
		"BIRTH6.PAL",
		"BIRTH6.PIC",
		"BIRTH7.PAL",
		"BIRTH7.PIC",
		"BIRTH8.PAL",
		"BIRTH8.PIC",
		"BLURB0.TXT",
		"BLURB1.TXT",
		"BLURB2.TXT",
		"BLURB3.TXT",
		"BLURB4.TXT",
		"CASTLE0.PIC",
		"CASTLE1.PIC",
		"CASTLE2.PIC",
		"CASTLE3.PIC",
		"CASTLE4.PIC",
		"CBACK.PIC",
		"CBACKS1.PIC",
		"CBACKS2.PIC",
		"CBACKS3.PIC",
		"CBRUSH0.PIC",
		"CBRUSH1.PIC",
		"CBRUSH2.PIC",
		"CBRUSH3.PIC",
		"CBRUSH4.PIC",
		"CBRUSH5.PIC",
		"CITYPIX1.PIC",
		"CITYPIX2.PIC",
		"CITYPIX3.PIC",
		"CIV.EXE",
		"CREDITS.TXT",
		"CUSTOM.PIC",
		"DIFFS.PIC",
		"DISCOVR1.PAL",
		"DISCOVR1.PIC",
		"DISCOVR2.PAL",
		"DISCOVR2.PIC",
		"DOCKER.PIC",
		"ERROR.TXT",
		"FAME.DTA",
		"FONTS.CV",
		"GOVT0A.PIC",
		"GOVT0M.PIC",
		"GOVT1A.PIC",
		"GOVT1M.PIC",
		"GOVT2A.PIC",
		"GOVT2M.PIC",
		"GOVT3A.PIC",
		"HELP.TXT",
		"HILL.PAL",
		"HILL.PIC",
		"ICONPG1.PAL",
		"ICONPG1.PIC",
		"ICONPG2.PIC",
		"ICONPG3.PIC",
		"ICONPG4.PIC",
		"ICONPG5.PIC",
		"ICONPG6.PIC",
		"ICONPG7.PIC",
		"ICONPG8.PIC",
		"ICONPGA.PAL",
		"ICONPGA.PIC",
		"ICONPGB.PIC",
		"ICONPGC.PIC",
		"ICONPGD.PIC",
		"ICONPGE.PIC",
		"ICONPGT1.PIC",
		"ICONPGT2.PIC",
		"INTRO.TXT",
		"INTRO3.TXT",
		"INVADER2.PIC",
		"INVADER3.PIC",
		"INVADERS.PIC",
		"KING.TXT",
		"KING00.PAL",
		"KING00.PIC",
		"KING01.PAL",
		"KING01.PIC",
		"KING02.PAL",
		"KING02.PIC",
		"KING03.PAL",
		"KING03.PIC",
		"KING04.PAL",
		"KING04.PIC",
		"KING05.PAL",
		"KING05.PIC",
		"KING06.PAL",
		"KING06.PIC",
		"KING07.PAL",
		"KING07.PIC",
		"KING08.PAL",
		"KING08.PIC",
		"KING09.PAL",
		"KING09.PIC",
		"KING10.PAL",
		"KING10.PIC",
		"KING11.PAL",
		"KING11.PIC",
		"KING12.PAL",
		"KING12.PIC",
		"KING13.PAL",
		"KING13.PIC",
		"KINK00.PIC",
		"KINK03.PIC",
		"LOGO.PIC",
		"LOVE1.PIC",
		"LOVE2.PIC",
		"MAP.PIC",
		"NUKE1.PIC",
		"PLANET1.PIC",
		"PLANET2.PIC",
		"POP.PIC",
		"PRODUCE.TXT",
		"RIOT.PIC",
		"RIOT2.PIC",
		"SAD.PIC",
		"SETTLERS.PIC",
		"SLAG2.PIC",
		"SLAM1.PAL",
		"SLAM1.PIC",
		"SLAM2.PIC",
		"SP256.PAL",
		"SP257.PAL",
		"SP257.PIC",
		"SP299.PIC",
		"SPACEST.PIC",
		"SPRITES.PIC",
		"STORY.TXT",
		"TER257.PIC",
		"TORCH.PIC",
		"WONDERS.PIC",
		"WONDERS2.PIC",
	];

	/// <summary>
	/// Required root-level file names, compared using ordinal
	/// case-insensitive semantics on every platform.
	/// </summary>
	public static IReadOnlySet<string> RequiredFileNames { get; } =
		CanonicalRequiredFileNames.ToFrozenSet(StringComparer.OrdinalIgnoreCase);

	public static bool IsRequiredFileName(string fileName)
	{
		ArgumentException.ThrowIfNullOrWhiteSpace(fileName);
		return RequiredFileNames.Contains(fileName);
	}

	public static ClassicDataFileCategory GetCategory(string fileName)
	{
		ArgumentException.ThrowIfNullOrWhiteSpace(fileName);
		if (!IsRequiredFileName(fileName))
		{
			throw new ArgumentOutOfRangeException(
				nameof(fileName),
				fileName,
				"The file is not part of the Classic data manifest.");
		}

		if (fileName.Equals("MAP.PIC", StringComparison.OrdinalIgnoreCase))
		{
			return ClassicDataFileCategory.GameplayData;
		}

		if (fileName.Equals("FAME.DTA", StringComparison.OrdinalIgnoreCase))
		{
			return ClassicDataFileCategory.MutableRuntimeSeed;
		}

		if (fileName.Equals("CIV.EXE", StringComparison.OrdinalIgnoreCase))
		{
			return ClassicDataFileCategory.LegacyExecutableMarker;
		}

		if (Path.GetExtension(fileName).Equals(
			".TXT",
			StringComparison.OrdinalIgnoreCase))
		{
			return ClassicDataFileCategory.TextOrHelp;
		}

		return ClassicDataFileCategory.GraphicsPaletteOrFont;
	}

	internal static IEnumerable<string> EnumerateCanonicalRequiredFileNames() =>
		CanonicalRequiredFileNames;
}
