using System.Buffers;
using System.Security.Cryptography;
using System.Text.Json;
using OpenCivOne.Runtime;

namespace OpenCivOne.Platform;

public sealed class ClassicSaveMetadataSerializer
{
	public const int MaximumJsonByteLength = 64 * 1024;

	private const int Sha256HexLength = 64;
	private const int MaximumStableIdLength = 128;

	private static readonly HashSet<string> Schema1PropertyNames =
		new(StringComparer.Ordinal)
		{
			"formatId",
			"schemaVersion",
			"aiProfileId",
			"runtimeCompatibilityId",
			"hashAlgorithm",
			"sveLength",
			"sveSha256",
			"mapLength",
			"mapSha256",
			"difficultyId",
			"seed",
			"handicapModifierIds",
		};

	private static readonly HashSet<string> Schema2PropertyNames =
		new(
			Schema1PropertyNames.Append("unitAutomation"),
			StringComparer.Ordinal);

	private static readonly HashSet<string> Schema3PropertyNames =
		new(
			Schema2PropertyNames.Append(
				"profileSplitCompatibilityId"),
			StringComparer.Ordinal);

	private static readonly HashSet<string>
		UnitAutomationPropertyNames =
			new(StringComparer.Ordinal)
			{
				"schemaVersion",
				"orders",
			};

	private static readonly HashSet<string>
		UnitAutomationOrderPropertyNames =
			new(StringComparer.Ordinal)
			{
				"playerId",
				"unitId",
				"unitTypeId",
				"kindId",
				"phaseId",
				"destinationCityId",
				"targetX",
				"targetY",
				"workKindId",
				"unitStateFingerprint",
			};

	private readonly HashSet<string> supportedHandicapModifierIds;

	public ClassicSaveMetadataSerializer(
		IEnumerable<string>? supportedHandicapModifierIds = null)
	{
		this.supportedHandicapModifierIds =
			new HashSet<string>(StringComparer.Ordinal);

		foreach (string modifierId in
			supportedHandicapModifierIds ?? [])
		{
			if (!IsStableId(modifierId))
			{
				throw new ArgumentException(
					$"Handicap modifier ID '{modifierId}' is not a stable ID.",
					nameof(supportedHandicapModifierIds));
			}

			if (!this.supportedHandicapModifierIds.Add(modifierId))
			{
				throw new ArgumentException(
					$"Handicap modifier ID '{modifierId}' is registered more than once.",
					nameof(supportedHandicapModifierIds));
			}
		}
	}

	public ClassicSaveMetadata Create(
		ClassicAiProfile aiProfile,
		string runtimeCompatibilityId,
		string difficultyId,
		ushort seed,
		ReadOnlyMemory<byte> sveBytes,
		ReadOnlyMemory<byte> mapBytes,
		IEnumerable<string> handicapModifierIds,
		ClassicUnitAutomationMetadata? unitAutomation = null)
	{
		if (!Enum.IsDefined(aiProfile))
		{
			throw new ArgumentOutOfRangeException(
				nameof(aiProfile),
				aiProfile,
				"AI profile is not supported.");
		}

		if (!IsStableId(runtimeCompatibilityId))
		{
			throw new ArgumentException(
				"A stable runtime compatibility ID is required.",
				nameof(runtimeCompatibilityId));
		}

		if (!ClassicDifficultyIds.IsKnown(difficultyId))
		{
			throw new ArgumentException(
				$"Difficulty ID '{difficultyId}' is not supported.",
				nameof(difficultyId));
		}

		string[] normalizedModifierIds =
			NormalizeModifierIdsForCreate(
				handicapModifierIds);
		ClassicUnitAutomationMetadata normalizedAutomation =
			NormalizeUnitAutomationForCreate(
				unitAutomation ??
					ClassicUnitAutomationMetadata.Empty);

		return new ClassicSaveMetadata(
			ClassicSaveMetadata.CurrentSchemaVersion,
			aiProfile,
			ClassicSaveMetadata
				.CurrentProfileSplitCompatibilityId,
			runtimeCompatibilityId,
			ClassicSaveMetadata.HashAlgorithmId,
			sveBytes.Length,
			ComputeSha256(sveBytes.Span),
			mapBytes.Length,
			ComputeSha256(mapBytes.Span),
			difficultyId,
			seed,
			normalizedModifierIds,
			normalizedAutomation);
	}

	public byte[] Serialize(ClassicSaveMetadata metadata)
	{
		ArgumentNullException.ThrowIfNull(metadata);
		ValidateMetadataForSerialize(metadata);

		ArrayBufferWriter<byte> buffer = new();
		using (Utf8JsonWriter writer = new(
			buffer,
			new JsonWriterOptions
			{
				Indented = false,
				SkipValidation = false,
			}))
		{
			writer.WriteStartObject();
			writer.WriteString(
				"formatId",
				ClassicSaveMetadata.FormatId);
			writer.WriteNumber(
				"schemaVersion",
				metadata.SchemaVersion);
			writer.WriteString(
				"aiProfileId",
				metadata.AiProfileId);
			writer.WriteString(
				"profileSplitCompatibilityId",
				metadata.ProfileSplitCompatibilityId);
			writer.WriteString(
				"runtimeCompatibilityId",
				metadata.RuntimeCompatibilityId);
			writer.WriteString(
				"hashAlgorithm",
				metadata.HashAlgorithm);
			writer.WriteNumber(
				"sveLength",
				metadata.SveLength);
			writer.WriteString(
				"sveSha256",
				metadata.SveSha256);
			writer.WriteNumber(
				"mapLength",
				metadata.MapLength);
			writer.WriteString(
				"mapSha256",
				metadata.MapSha256);
			writer.WriteString(
				"difficultyId",
				metadata.DifficultyId);
			writer.WriteNumber(
				"seed",
				metadata.Seed);
			writer.WriteStartArray("handicapModifierIds");
			foreach (string modifierId in
				metadata.HandicapModifierIds)
			{
				writer.WriteStringValue(modifierId);
			}
			writer.WriteEndArray();
			WriteUnitAutomation(
				writer,
				metadata.UnitAutomation);
			writer.WriteEndObject();
		}

		if (buffer.WrittenCount > MaximumJsonByteLength)
		{
			throw new InvalidDataException(
				"Classic save metadata exceeds the maximum JSON size.");
		}

		return buffer.WrittenSpan.ToArray();
	}

	private static void WriteUnitAutomation(
		Utf8JsonWriter writer,
		ClassicUnitAutomationMetadata automation)
	{
		writer.WriteStartObject("unitAutomation");
		writer.WriteNumber(
			"schemaVersion",
			automation.SchemaVersion);
		writer.WriteStartArray("orders");
		foreach (ClassicUnitAutomationOrderMetadata order in
			automation.Orders)
		{
			writer.WriteStartObject();
			writer.WriteNumber("playerId", order.PlayerID);
			writer.WriteNumber("unitId", order.UnitID);
			writer.WriteNumber("unitTypeId", order.UnitTypeID);
			writer.WriteString("kindId", order.KindID);
			writer.WriteString("phaseId", order.PhaseID);
			WriteNullableNumber(
				writer,
				"destinationCityId",
				order.DestinationCityID);
			WriteNullableNumber(
				writer,
				"targetX",
				order.TargetX);
			WriteNullableNumber(
				writer,
				"targetY",
				order.TargetY);
			if (order.WorkKindID is null)
			{
				writer.WriteNull("workKindId");
			}
			else
			{
				writer.WriteString(
					"workKindId",
					order.WorkKindID);
			}
			writer.WriteString(
				"unitStateFingerprint",
				order.UnitStateFingerprint);
			writer.WriteEndObject();
		}
		writer.WriteEndArray();
		writer.WriteEndObject();
	}

	private static void WriteNullableNumber(
		Utf8JsonWriter writer,
		string propertyName,
		int? value)
	{
		if (value is null)
		{
			writer.WriteNull(propertyName);
		}
		else
		{
			writer.WriteNumber(propertyName, value.Value);
		}
	}

	private void ValidateMetadataForSerialize(
		ClassicSaveMetadata metadata)
	{
		if (metadata.SchemaVersion !=
				ClassicSaveMetadata.CurrentSchemaVersion ||
			!Enum.IsDefined(metadata.AiProfile) ||
			!string.Equals(
				metadata.ProfileSplitCompatibilityId,
				ClassicSaveMetadata
					.CurrentProfileSplitCompatibilityId,
				StringComparison.Ordinal) ||
			!IsStableId(metadata.RuntimeCompatibilityId) ||
			!string.Equals(
				metadata.HashAlgorithm,
				ClassicSaveMetadata.HashAlgorithmId,
				StringComparison.Ordinal) ||
			metadata.SveLength < 0 ||
			!IsCanonicalSha256(metadata.SveSha256) ||
			metadata.MapLength < 0 ||
			!IsCanonicalSha256(metadata.MapSha256) ||
			!ClassicDifficultyIds.IsKnown(
				metadata.DifficultyId))
		{
			throw InvalidMetadata(
				"Classic save metadata cannot be serialized because its identity fields are invalid.");
		}

		ValidateUnitAutomationForSerialize(
			metadata.UnitAutomation);

		HashSet<string> uniqueModifierIds =
			new(StringComparer.Ordinal);
		string? previousModifierId = null;
		foreach (string modifierId in
			metadata.HandicapModifierIds)
		{
			if (!IsStableId(modifierId) ||
				!this.supportedHandicapModifierIds.Contains(
					modifierId))
			{
				throw InvalidMetadata(
					$"Handicap modifier ID '{modifierId}' is not supported.");
			}

			if (!uniqueModifierIds.Add(modifierId))
			{
				throw InvalidMetadata(
					$"Handicap modifier ID '{modifierId}' occurs more than once.");
			}

			if (previousModifierId is not null &&
				StringComparer.Ordinal.Compare(
					previousModifierId,
					modifierId) >= 0)
			{
				throw InvalidMetadata(
					"Handicap modifier IDs are not in canonical order.");
			}

			previousModifierId = modifierId;
		}
	}

	internal static void ValidateUnitAutomationForSerialize(
		ClassicUnitAutomationMetadata automation)
	{
		ArgumentNullException.ThrowIfNull(automation);
		if (automation.SchemaVersion !=
			ClassicUnitAutomationMetadata.CurrentSchemaVersion)
		{
			throw InvalidMetadata(
				"Unit automation schema version is not supported.");
		}

		ValidateCanonicalOrders(automation.Orders);
	}

	private static void ValidateCanonicalOrders(
		IReadOnlyList<ClassicUnitAutomationOrderMetadata> orders)
	{
		if (orders.Count >
			ClassicUnitAutomationMetadata.MaximumOrderCount)
		{
			throw InvalidMetadata(
				"Unit automation contains too many orders.");
		}

		(int PlayerID, int UnitID)? previousIdentity = null;
		HashSet<(int PlayerID, int UnitID)> identities = [];
		foreach (ClassicUnitAutomationOrderMetadata order in orders)
		{
			ValidateOrder(order);

			(int PlayerID, int UnitID) identity =
				(order.PlayerID, order.UnitID);
			if (!identities.Add(identity))
			{
				throw InvalidMetadata(
					"Unit automation contains more than one order for the same unit.");
			}

			if (previousIdentity is { } previous &&
				(previous.PlayerID > identity.PlayerID ||
				 (previous.PlayerID == identity.PlayerID &&
				  previous.UnitID >= identity.UnitID)))
			{
				throw InvalidMetadata(
					"Unit automation orders are not in canonical order.");
			}

			previousIdentity = identity;
		}
	}

	private static void ValidateOrder(
		ClassicUnitAutomationOrderMetadata order)
	{
		if (order.PlayerID < 0 || order.PlayerID >= 8 ||
			order.UnitID < 0 || order.UnitID >= 128 ||
			order.UnitTypeID < 0 || order.UnitTypeID >= 28 ||
			!Enum.IsDefined(order.Kind) ||
			!Enum.IsDefined(order.Phase) ||
			(order.WorkKind is not null &&
			 !Enum.IsDefined(order.WorkKind.Value)) ||
			!IsCanonicalSha256(order.UnitStateFingerprint))
		{
			throw InvalidMetadata(
				"Unit automation order identity is invalid.");
		}

		if (order.DestinationCityID is < 0 or >= 128)
		{
			throw InvalidMetadata(
				"Unit automation destination city is outside the supported range.");
		}

		bool hasTargetX = order.TargetX is not null;
		bool hasTargetY = order.TargetY is not null;
		if (hasTargetX != hasTargetY ||
			order.TargetX is < 0 or >= 80 ||
			order.TargetY is < 0 or >= 50)
		{
			throw InvalidMetadata(
				"Unit automation target cell is invalid.");
		}

		bool hasTarget = hasTargetX;
		if (order.Phase ==
				ClassicUnitAutomationPhase.SelectingTarget &&
			hasTarget)
		{
			throw InvalidMetadata(
				"A selecting unit automation order cannot already have a target cell.");
		}

		if (order.Phase !=
				ClassicUnitAutomationPhase.SelectingTarget &&
			!hasTarget)
		{
			throw InvalidMetadata(
				"A moving or working unit automation order requires a target cell.");
		}

		switch (order.Kind)
		{
			case ClassicUnitAutomationKind.AutomaticExplore:
				if (order.DestinationCityID is not null ||
					order.WorkKind is not null ||
					order.Phase ==
						ClassicUnitAutomationPhase.WorkingTarget)
				{
					throw InvalidMetadata(
						"Automatic explore contains city or Settler work state.");
				}
				break;

			case ClassicUnitAutomationKind.ImproveNearestCity:
				if (order.DestinationCityID is null ||
					(order.Phase ==
							ClassicUnitAutomationPhase.WorkingTarget &&
					 order.WorkKind is null) ||
					(order.Phase ==
							ClassicUnitAutomationPhase.SelectingTarget &&
					 order.WorkKind is not null))
				{
					throw InvalidMetadata(
						"Nearest-city improvement continuation state is invalid.");
				}
				break;

			case ClassicUnitAutomationKind.BuildRoadToCity:
				if (order.DestinationCityID is null ||
					order.WorkKind !=
						ClassicUnitAutomationWorkKind.Road)
				{
					throw InvalidMetadata(
						"Road-to-city continuation state is invalid.");
				}
				break;
		}
	}

	public ClassicSaveMetadata DeserializeAndValidate(
		ReadOnlyMemory<byte> jsonUtf8,
		ReadOnlyMemory<byte> sveBytes,
		ReadOnlyMemory<byte> mapBytes,
		string expectedRuntimeCompatibilityId,
		string expectedDifficultyId,
		ushort expectedSeed)
	{
		if (!IsStableId(expectedRuntimeCompatibilityId))
		{
			throw new ArgumentException(
				"A stable expected runtime compatibility ID is required.",
				nameof(expectedRuntimeCompatibilityId));
		}

		if (!ClassicDifficultyIds.IsKnown(expectedDifficultyId))
		{
			throw new ArgumentException(
				$"Expected difficulty ID '{expectedDifficultyId}' is not supported.",
				nameof(expectedDifficultyId));
		}

		if (jsonUtf8.IsEmpty ||
			jsonUtf8.Length > MaximumJsonByteLength)
		{
			throw new InvalidDataException(
				"Classic save metadata JSON has an invalid size.");
		}

		try
		{
			using JsonDocument document = JsonDocument.Parse(
				jsonUtf8,
				new JsonDocumentOptions
				{
					AllowTrailingCommas = false,
					CommentHandling =
						JsonCommentHandling.Disallow,
					MaxDepth = 6,
				});

			return ParseAndValidate(
				document.RootElement,
				sveBytes,
				mapBytes,
				expectedRuntimeCompatibilityId,
				expectedDifficultyId,
				expectedSeed);
		}
		catch (InvalidDataException)
		{
			throw;
		}
		catch (JsonException exception)
		{
			throw new InvalidDataException(
				"Classic save metadata JSON is invalid.",
				exception);
		}
		catch (FormatException exception)
		{
			throw new InvalidDataException(
				"Classic save metadata contains an invalid value.",
				exception);
		}
		catch (OverflowException exception)
		{
			throw new InvalidDataException(
				"Classic save metadata contains an out-of-range value.",
				exception);
		}
	}

	private ClassicSaveMetadata ParseAndValidate(
		JsonElement root,
		ReadOnlyMemory<byte> sveBytes,
		ReadOnlyMemory<byte> mapBytes,
		string expectedRuntimeCompatibilityId,
		string expectedDifficultyId,
		ushort expectedSeed)
	{
		int schemaVersion =
			GetAndValidateRootSchemaVersion(root);
		ValidateRootProperties(root, schemaVersion);

		string formatId = GetRequiredString(root, "formatId");
		if (!string.Equals(
			formatId,
			ClassicSaveMetadata.FormatId,
			StringComparison.Ordinal))
		{
			throw InvalidMetadata(
				$"Metadata format ID '{formatId}' is not supported.");
		}

		string aiProfileId =
			GetRequiredString(root, "aiProfileId");
		if (!ClassicAiProfileIds.TryParseStableId(
			aiProfileId,
			out ClassicAiProfile aiProfile))
		{
			throw InvalidMetadata(
				$"AI profile ID '{aiProfileId}' is not supported.");
		}

		string? profileSplitCompatibilityId =
			schemaVersion >=
				ClassicSaveMetadata.ProfileSplitSchemaVersion
				? GetRequiredString(
					root,
					"profileSplitCompatibilityId")
				: null;
		if (schemaVersion >=
				ClassicSaveMetadata.ProfileSplitSchemaVersion &&
			!string.Equals(
				profileSplitCompatibilityId,
				ClassicSaveMetadata
					.CurrentProfileSplitCompatibilityId,
				StringComparison.Ordinal))
		{
			throw InvalidMetadata(
				$"Profile split compatibility ID '{profileSplitCompatibilityId}' is not supported.");
		}

		string runtimeCompatibilityId =
			GetRequiredString(
				root,
				"runtimeCompatibilityId");
		if (!IsStableId(runtimeCompatibilityId) ||
			!string.Equals(
				runtimeCompatibilityId,
				expectedRuntimeCompatibilityId,
				StringComparison.Ordinal))
		{
			throw InvalidMetadata(
				"Runtime compatibility ID does not match.");
		}

		string hashAlgorithm =
			GetRequiredString(root, "hashAlgorithm");
		if (!string.Equals(
			hashAlgorithm,
			ClassicSaveMetadata.HashAlgorithmId,
			StringComparison.Ordinal))
		{
			throw InvalidMetadata(
				$"Hash algorithm '{hashAlgorithm}' is not supported.");
		}

		long sveLength = GetRequiredInt64(
			root,
			"sveLength");
		string sveSha256 = GetRequiredString(
			root,
			"sveSha256");
		long mapLength = GetRequiredInt64(
			root,
			"mapLength");
		string mapSha256 = GetRequiredString(
			root,
			"mapSha256");

		ValidatePayloadIdentity(
			"SVE",
			sveLength,
			sveSha256,
			sveBytes);
		ValidatePayloadIdentity(
			"MAP",
			mapLength,
			mapSha256,
			mapBytes);

		string difficultyId =
			GetRequiredString(root, "difficultyId");
		if (!ClassicDifficultyIds.IsKnown(difficultyId))
		{
			throw InvalidMetadata(
				$"Difficulty ID '{difficultyId}' is not supported.");
		}
		if (!string.Equals(
			difficultyId,
			expectedDifficultyId,
			StringComparison.Ordinal))
		{
			throw InvalidMetadata(
				"Difficulty ID does not match the loaded state.");
		}

		int seedValue = GetRequiredInt32(root, "seed");
		if (seedValue < ushort.MinValue ||
			seedValue > ushort.MaxValue)
		{
			throw InvalidMetadata(
				"Deterministic seed is outside the supported range.");
		}

		ushort seed = (ushort)seedValue;
		if (seed != expectedSeed)
		{
			throw InvalidMetadata(
				"Deterministic seed does not match the loaded state.");
		}

		string[] modifierIds =
			ParseAndValidateModifierIds(root);
		ClassicUnitAutomationMetadata unitAutomation =
			schemaVersion ==
				ClassicSaveMetadata.LegacySchemaVersion
				? ClassicUnitAutomationMetadata.Empty
				: ParseAndValidateUnitAutomation(root);

		return new ClassicSaveMetadata(
			schemaVersion,
			aiProfile,
			profileSplitCompatibilityId,
			runtimeCompatibilityId,
			hashAlgorithm,
			sveLength,
			sveSha256,
			mapLength,
			mapSha256,
			difficultyId,
			seed,
			modifierIds,
			unitAutomation);
	}

	private static int GetAndValidateRootSchemaVersion(
		JsonElement root)
	{
		if (root.ValueKind != JsonValueKind.Object)
		{
			throw InvalidMetadata(
				"Classic save metadata root must be an object.");
		}

		HashSet<string> foundProperties =
			new(StringComparer.Ordinal);
		foreach (JsonProperty property in
			root.EnumerateObject())
		{
			if (!foundProperties.Add(property.Name))
			{
				throw InvalidMetadata(
					$"Metadata property '{property.Name}' occurs more than once.");
			}
		}

		if (!foundProperties.Contains("schemaVersion"))
		{
			throw InvalidMetadata(
				"Classic save metadata is missing a required property.");
		}

		int schemaVersion =
			GetRequiredInt32(root, "schemaVersion");
		if (schemaVersion is not
				ClassicSaveMetadata.LegacySchemaVersion and not
				ClassicSaveMetadata.PreProfileSplitSchemaVersion and not
				ClassicSaveMetadata.ProfileSplitSchemaVersion and not
				ClassicSaveMetadata.CurrentSchemaVersion)
		{
			throw InvalidMetadata(
				$"Metadata schema version '{schemaVersion}' is not supported.");
		}

		return schemaVersion;
	}

	private static void ValidateRootProperties(
		JsonElement root,
		int schemaVersion)
	{
		HashSet<string> expectedPropertyNames =
			schemaVersion ==
				ClassicSaveMetadata.LegacySchemaVersion
				? Schema1PropertyNames
				: schemaVersion ==
					ClassicSaveMetadata
						.PreProfileSplitSchemaVersion
					? Schema2PropertyNames
					: Schema3PropertyNames;
		ValidateExactObjectProperties(
			root,
			expectedPropertyNames,
			"Metadata");
	}

	private static ClassicUnitAutomationMetadata
		ParseAndValidateUnitAutomation(JsonElement root)
	{
		JsonElement automation = root.GetProperty(
			"unitAutomation");
		ValidateExactObjectProperties(
			automation,
			UnitAutomationPropertyNames,
			"Unit automation");

		int schemaVersion = GetRequiredInt32(
			automation,
			"schemaVersion");
		if (schemaVersion !=
			ClassicUnitAutomationMetadata.CurrentSchemaVersion)
		{
			throw InvalidMetadata(
				$"Unit automation schema version '{schemaVersion}' is not supported.");
		}

		JsonElement ordersElement =
			automation.GetProperty("orders");
		if (ordersElement.ValueKind != JsonValueKind.Array)
		{
			throw InvalidMetadata(
				"Unit automation orders must be an array.");
		}

		List<ClassicUnitAutomationOrderMetadata> orders = [];
		foreach (JsonElement orderElement in
			ordersElement.EnumerateArray())
		{
			if (orders.Count >=
				ClassicUnitAutomationMetadata.MaximumOrderCount)
			{
				throw InvalidMetadata(
					"Unit automation contains too many orders.");
			}

			orders.Add(
				ParseAndValidateUnitAutomationOrder(
					orderElement));
		}

		ValidateCanonicalOrders(orders);
		return new ClassicUnitAutomationMetadata(
			schemaVersion,
			orders);
	}

	private static ClassicUnitAutomationOrderMetadata
		ParseAndValidateUnitAutomationOrder(JsonElement element)
	{
		ValidateExactObjectProperties(
			element,
			UnitAutomationOrderPropertyNames,
			"Unit automation order");

		string kindID = GetRequiredString(element, "kindId");
		if (!ClassicUnitAutomationKindIds.TryParseStableId(
			kindID,
			out ClassicUnitAutomationKind kind))
		{
			throw InvalidMetadata(
				$"Unit automation kind ID '{kindID}' is not supported.");
		}

		string phaseID = GetRequiredString(element, "phaseId");
		if (!ClassicUnitAutomationPhaseIds.TryParseStableId(
			phaseID,
			out ClassicUnitAutomationPhase phase))
		{
			throw InvalidMetadata(
				$"Unit automation phase ID '{phaseID}' is not supported.");
		}

		string? workKindID = GetOptionalString(
			element,
			"workKindId");
		ClassicUnitAutomationWorkKind? workKind = null;
		if (workKindID is not null)
		{
			if (!ClassicUnitAutomationWorkKindIds.TryParseStableId(
				workKindID,
				out ClassicUnitAutomationWorkKind parsedWorkKind))
			{
				throw InvalidMetadata(
					$"Unit automation work kind ID '{workKindID}' is not supported.");
			}

			workKind = parsedWorkKind;
		}

		ClassicUnitAutomationOrderMetadata order = new(
			GetRequiredInt32(element, "playerId"),
			GetRequiredInt32(element, "unitId"),
			GetRequiredInt32(element, "unitTypeId"),
			kind,
			phase,
			GetOptionalInt32(element, "destinationCityId"),
			GetOptionalInt32(element, "targetX"),
			GetOptionalInt32(element, "targetY"),
			workKind,
			GetRequiredString(
				element,
				"unitStateFingerprint"));
		ValidateOrder(order);
		return order;
	}

	private static void ValidateExactObjectProperties(
		JsonElement element,
		HashSet<string> expectedPropertyNames,
		string objectName)
	{
		if (element.ValueKind != JsonValueKind.Object)
		{
			throw InvalidMetadata(
				$"{objectName} must be an object.");
		}

		HashSet<string> foundPropertyNames =
			new(StringComparer.Ordinal);
		foreach (JsonProperty property in
			element.EnumerateObject())
		{
			if (!expectedPropertyNames.Contains(property.Name))
			{
				throw InvalidMetadata(
					$"{objectName} property '{property.Name}' is not supported.");
			}

			if (!foundPropertyNames.Add(property.Name))
			{
				throw InvalidMetadata(
					$"{objectName} property '{property.Name}' occurs more than once.");
			}
		}

		if (foundPropertyNames.Count !=
			expectedPropertyNames.Count)
		{
			throw InvalidMetadata(
				$"{objectName} is missing a required property.");
		}
	}

	private string[] ParseAndValidateModifierIds(
		JsonElement root)
	{
		if (!root.TryGetProperty(
				"handicapModifierIds",
				out JsonElement modifiersElement) ||
			modifiersElement.ValueKind !=
			JsonValueKind.Array)
		{
			throw InvalidMetadata(
				"Handicap modifier IDs must be an array.");
		}

		List<string> modifierIds = [];
		HashSet<string> uniqueModifierIds =
			new(StringComparer.Ordinal);
		foreach (JsonElement modifierElement in
			modifiersElement.EnumerateArray())
		{
			if (modifierElement.ValueKind !=
				JsonValueKind.String)
			{
				throw InvalidMetadata(
					"Every handicap modifier ID must be a string.");
			}

			string modifierId =
				modifierElement.GetString() ??
				string.Empty;
			if (!IsStableId(modifierId) ||
				!this.supportedHandicapModifierIds.Contains(
					modifierId))
			{
				throw InvalidMetadata(
					$"Handicap modifier ID '{modifierId}' is not supported.");
			}

			if (!uniqueModifierIds.Add(modifierId))
			{
				throw InvalidMetadata(
					$"Handicap modifier ID '{modifierId}' occurs more than once.");
			}

			modifierIds.Add(modifierId);
		}

		string[] sortedModifierIds =
			modifierIds
				.OrderBy(
					static modifierId => modifierId,
					StringComparer.Ordinal)
				.ToArray();
		if (!modifierIds.SequenceEqual(
			sortedModifierIds,
			StringComparer.Ordinal))
		{
			throw InvalidMetadata(
				"Handicap modifier IDs are not in canonical order.");
		}

		return sortedModifierIds;
	}

	private string[] NormalizeModifierIdsForCreate(
		IEnumerable<string> modifierIds)
	{
		ArgumentNullException.ThrowIfNull(modifierIds);

		HashSet<string> uniqueModifierIds =
			new(StringComparer.Ordinal);
		foreach (string modifierId in modifierIds)
		{
			if (!IsStableId(modifierId) ||
				!this.supportedHandicapModifierIds.Contains(
					modifierId))
			{
				throw new ArgumentException(
					$"Handicap modifier ID '{modifierId}' is not supported.",
					nameof(modifierIds));
			}

			if (!uniqueModifierIds.Add(modifierId))
			{
				throw new ArgumentException(
					$"Handicap modifier ID '{modifierId}' occurs more than once.",
					nameof(modifierIds));
			}
		}

		return uniqueModifierIds
			.OrderBy(
				static modifierId => modifierId,
				StringComparer.Ordinal)
				.ToArray();
	}

	private static ClassicUnitAutomationMetadata
		NormalizeUnitAutomationForCreate(
			ClassicUnitAutomationMetadata automation)
	{
		ArgumentNullException.ThrowIfNull(automation);
		if (automation.SchemaVersion !=
			ClassicUnitAutomationMetadata.CurrentSchemaVersion)
		{
			throw new ArgumentException(
				"Unit automation schema version is not supported.",
				nameof(automation));
		}

		ClassicUnitAutomationMetadata normalized = new(
			automation.Orders);
		try
		{
			ValidateCanonicalOrders(normalized.Orders);
		}
		catch (InvalidDataException exception)
		{
			throw new ArgumentException(
				"Unit automation state is invalid.",
				nameof(automation),
				exception);
		}

		return normalized;
	}

	private static void ValidatePayloadIdentity(
		string payloadName,
		long expectedLength,
		string expectedSha256,
		ReadOnlyMemory<byte> actualBytes)
	{
		if (expectedLength < 0 ||
			expectedLength != actualBytes.Length)
		{
			throw InvalidMetadata(
				$"{payloadName} byte length does not match.");
		}

		if (!IsCanonicalSha256(expectedSha256))
		{
			throw InvalidMetadata(
				$"{payloadName} SHA-256 is not canonical.");
		}

		byte[] expectedHash =
			Convert.FromHexString(expectedSha256);
		byte[] actualHash =
			SHA256.HashData(actualBytes.Span);
		if (!CryptographicOperations.FixedTimeEquals(
			expectedHash,
			actualHash))
		{
			throw InvalidMetadata(
				$"{payloadName} SHA-256 does not match.");
		}
	}

	private static string GetRequiredString(
		JsonElement root,
		string propertyName)
	{
		JsonElement value = root.GetProperty(propertyName);
		if (value.ValueKind != JsonValueKind.String)
		{
			throw InvalidMetadata(
				$"Metadata property '{propertyName}' must be a string.");
		}

		return value.GetString() ?? string.Empty;
	}

	private static string? GetOptionalString(
		JsonElement root,
		string propertyName)
	{
		JsonElement value = root.GetProperty(propertyName);
		if (value.ValueKind == JsonValueKind.Null)
		{
			return null;
		}

		if (value.ValueKind != JsonValueKind.String)
		{
			throw InvalidMetadata(
				$"Metadata property '{propertyName}' must be a string or null.");
		}

		return value.GetString() ?? string.Empty;
	}

	private static int GetRequiredInt32(
		JsonElement root,
		string propertyName)
	{
		JsonElement value = root.GetProperty(propertyName);
		if (value.ValueKind != JsonValueKind.Number ||
			!value.TryGetInt32(out int result))
		{
			throw InvalidMetadata(
				$"Metadata property '{propertyName}' must be an integer.");
		}

		return result;
	}

	private static int? GetOptionalInt32(
		JsonElement root,
		string propertyName)
	{
		JsonElement value = root.GetProperty(propertyName);
		if (value.ValueKind == JsonValueKind.Null)
		{
			return null;
		}

		if (value.ValueKind != JsonValueKind.Number ||
			!value.TryGetInt32(out int result))
		{
			throw InvalidMetadata(
				$"Metadata property '{propertyName}' must be an integer or null.");
		}

		return result;
	}

	private static long GetRequiredInt64(
		JsonElement root,
		string propertyName)
	{
		JsonElement value = root.GetProperty(propertyName);
		if (value.ValueKind != JsonValueKind.Number ||
			!value.TryGetInt64(out long result))
		{
			throw InvalidMetadata(
				$"Metadata property '{propertyName}' must be an integer.");
		}

		return result;
	}

	private static string ComputeSha256(
		ReadOnlySpan<byte> bytes) =>
		Convert.ToHexString(SHA256.HashData(bytes))
			.ToLowerInvariant();

	private static bool IsCanonicalSha256(
		string value)
	{
		if (value.Length != Sha256HexLength)
		{
			return false;
		}

		foreach (char character in value)
		{
			if (!char.IsAsciiHexDigitLower(character))
			{
				return false;
			}
		}

		return true;
	}

	private static bool IsStableId(string? value)
	{
		if (string.IsNullOrEmpty(value) ||
			value.Length > MaximumStableIdLength)
		{
			return false;
		}

		foreach (char character in value)
		{
			if (!char.IsAsciiLetterOrDigit(character) &&
				character is not '-' and not '_' and not '.')
			{
				return false;
			}

			if (char.IsAsciiLetterUpper(character))
			{
				return false;
			}
		}

		return true;
	}

	private static InvalidDataException InvalidMetadata(
		string message) =>
		new(message);
}
