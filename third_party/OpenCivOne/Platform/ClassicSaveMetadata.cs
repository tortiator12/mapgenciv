using OpenCivOne.Runtime;

namespace OpenCivOne.Platform;

public sealed class ClassicSaveMetadata
{
	public const string FormatId =
		"project1991-classic-save-metadata";

	public const int LegacySchemaVersion = 1;

	public const int PreProfileSplitSchemaVersion = 2;

	public const int ProfileSplitSchemaVersion = 3;

	public const int CurrentSchemaVersion = 4;

	public const string CurrentProfileSplitCompatibilityId =
		"project1991-profile-split-v1";

	public const string HashAlgorithmId = "sha256";

	internal ClassicSaveMetadata(
		int schemaVersion,
		ClassicAiProfile aiProfile,
		string? profileSplitCompatibilityId,
		string runtimeCompatibilityId,
		string hashAlgorithm,
		long sveLength,
		string sveSha256,
		long mapLength,
		string mapSha256,
		string difficultyId,
		ushort seed,
		IEnumerable<string> handicapModifierIds,
		ClassicUnitAutomationMetadata unitAutomation)
	{
		ArgumentNullException.ThrowIfNull(unitAutomation);
		SchemaVersion = schemaVersion;
		AiProfile = aiProfile;
		ProfileSplitCompatibilityId =
			profileSplitCompatibilityId;
		RuntimeCompatibilityId = runtimeCompatibilityId;
		HashAlgorithm = hashAlgorithm;
		SveLength = sveLength;
		SveSha256 = sveSha256;
		MapLength = mapLength;
		MapSha256 = mapSha256;
		DifficultyId = difficultyId;
		Seed = seed;
		HandicapModifierIds = Array.AsReadOnly(
			handicapModifierIds.ToArray());
		UnitAutomation = unitAutomation;
	}

	public string MetadataFormatId => FormatId;

	public int SchemaVersion { get; }

	public ClassicAiProfile AiProfile { get; }

	public string AiProfileId =>
		ClassicAiProfileIds.ToStableId(AiProfile);

	public string? ProfileSplitCompatibilityId { get; }

	public bool HasExplicitProfileSplit =>
		SchemaVersion >= ProfileSplitSchemaVersion &&
		string.Equals(
			ProfileSplitCompatibilityId,
			CurrentProfileSplitCompatibilityId,
			StringComparison.Ordinal);

	public string RuntimeCompatibilityId { get; }

	public string HashAlgorithm { get; }

	public long SveLength { get; }

	public string SveSha256 { get; }

	public long MapLength { get; }

	public string MapSha256 { get; }

	public string DifficultyId { get; }

	public ushort Seed { get; }

	public IReadOnlyList<string> HandicapModifierIds { get; }

	public ClassicUnitAutomationMetadata UnitAutomation { get; }
}

public static class ClassicDifficultyIds
{
	public const string Chieftain = "chieftain";

	public const string Warlord = "warlord";

	public const string Prince = "prince";

	public const string King = "king";

	public const string Emperor = "emperor";

	public static bool IsKnown(string? difficultyId) =>
		difficultyId is
			Chieftain or
			Warlord or
			Prince or
			King or
			Emperor;

	public static string ToStableId(short difficultyLevel) =>
		difficultyLevel switch
		{
			0 => Chieftain,
			1 => Warlord,
			2 => Prince,
			3 => King,
			4 => Emperor,
			_ => throw new ArgumentOutOfRangeException(
				nameof(difficultyLevel),
				difficultyLevel,
				"Classic difficulty must be between zero and four."),
		};
}
