using System.Globalization;
using System.Reflection;
using System.Text;
using System.Text.Json;

namespace OpenCivOne.Localization;

/// <summary>
/// Loads and validates immutable Classic framebuffer language resources.
/// </summary>
internal static class ClassicLanguagePackLoader
{
	private const int SupportedSchemaVersion = 1;
	private const string ResourcePrefix =
		"OpenCivOne.Localization.Resources.classic.";
	private const string ResourceSuffix = ".json";

	private static readonly IReadOnlySet<string> RootProperties =
		new HashSet<string>(StringComparer.Ordinal)
		{
			"schemaVersion",
			"language",
			"framebuffer",
			"displayNames"
		};

	private static readonly IReadOnlySet<string> DisplayNameProperties =
		new HashSet<string>(StringComparer.Ordinal)
		{
			"units",
			"terrains",
			"improvements",
			"wonders",
			"nations"
		};

	public static ClassicGameTextCatalog LoadEmbedded(
		string languageCode,
		ClassicGameTextCatalog? fallback,
		bool requireComplete)
	{
		string normalizedLanguage = NormalizeLanguageCode(languageCode);
		string resourceName =
			$"{ResourcePrefix}{normalizedLanguage}{ResourceSuffix}";
		Assembly assembly = typeof(ClassicLanguagePackLoader).Assembly;
		using Stream stream =
			assembly.GetManifestResourceStream(resourceName) ??
			throw new ClassicLanguagePackException(
				$"Embedded Classic language resource '{resourceName}' was not found.");

		return Load(
			stream,
			normalizedLanguage,
			fallback,
			requireComplete,
			resourceName);
	}

	internal static ClassicGameTextCatalog LoadJson(
		string json,
		string languageCode,
		ClassicGameTextCatalog? fallback = null,
		bool requireComplete = false)
	{
		ArgumentNullException.ThrowIfNull(json);
		using MemoryStream stream = new(
			System.Text.Encoding.UTF8.GetBytes(json),
			writable: false);
		return Load(
			stream,
			NormalizeLanguageCode(languageCode),
			fallback,
			requireComplete,
			"<memory>");
	}

	private static ClassicGameTextCatalog Load(
		Stream stream,
		string expectedLanguage,
		ClassicGameTextCatalog? fallback,
		bool requireComplete,
		string sourceName)
	{
		try
		{
			using JsonDocument document = JsonDocument.Parse(
				stream,
				new JsonDocumentOptions
				{
					AllowTrailingCommas = false,
					CommentHandling = JsonCommentHandling.Disallow
				});

			JsonElement root = RequireObject(document.RootElement, "root");
			Dictionary<string, JsonElement> rootValues =
				ReadProperties(root, RootProperties, "root");

			int schemaVersion = RequireInt32(
				RequireProperty(rootValues, "schemaVersion", "root"),
				"root.schemaVersion");
			if (schemaVersion != SupportedSchemaVersion)
			{
				throw new ClassicLanguagePackException(
					$"Unsupported Classic language schema version " +
					$"'{schemaVersion}' in {sourceName}.");
			}

			string language = NormalizeLanguageCode(
				RequireString(
					RequireProperty(rootValues, "language", "root"),
					"root.language"));
			if (!language.Equals(
				expectedLanguage,
				StringComparison.OrdinalIgnoreCase))
			{
				throw new ClassicLanguagePackException(
					$"Classic language resource '{sourceName}' declares " +
					$"'{language}' instead of '{expectedLanguage}'.");
			}

			IReadOnlyDictionary<ClassicGameTextKey, string> framebuffer =
				ReadFramebuffer(
					RequireProperty(rootValues, "framebuffer", "root"),
					fallback,
					requireComplete);
			ClassicDisplayNameCatalog displayNames = ReadDisplayNames(
				RequireProperty(rootValues, "displayNames", "root"));

			return new ClassicGameTextCatalog(
				framebuffer,
				fallback,
				language,
				displayNames);
		}
		catch (ClassicLanguagePackException)
		{
			throw;
		}
		catch (JsonException exception)
		{
			throw new ClassicLanguagePackException(
				$"Classic language resource '{sourceName}' is not valid JSON.",
				exception);
		}
		catch (Exception exception)
			when (exception is FormatException or OverflowException)
		{
			throw new ClassicLanguagePackException(
				$"Classic language resource '{sourceName}' is invalid.",
				exception);
		}
	}

	private static IReadOnlyDictionary<ClassicGameTextKey, string>
		ReadFramebuffer(
			JsonElement element,
			ClassicGameTextCatalog? fallback,
			bool requireComplete)
	{
		JsonElement framebuffer = RequireObject(element, "root.framebuffer");
		Dictionary<ClassicGameTextKey, string> texts = new();
		HashSet<string> sourceNames = new(StringComparer.Ordinal);

		foreach (JsonProperty property in framebuffer.EnumerateObject())
		{
			if (!sourceNames.Add(property.Name))
			{
				throw DuplicateProperty("root.framebuffer", property.Name);
			}

			if (!Enum.TryParse(
					property.Name,
					ignoreCase: false,
					out ClassicGameTextKey key) ||
				!Enum.IsDefined(key))
			{
				throw new ClassicLanguagePackException(
					$"Unknown Classic framebuffer key '{property.Name}'.");
			}

			if (!texts.TryAdd(
					key,
					ReadFramebufferString(
						property.Value,
						$"root.framebuffer.{property.Name}")))
			{
				throw new ClassicLanguagePackException(
					$"Duplicate Classic framebuffer key '{property.Name}'.");
			}
		}

		foreach (ClassicGameTextKey key in Enum.GetValues<ClassicGameTextKey>())
		{
			if (requireComplete && !texts.ContainsKey(key))
			{
				throw new ClassicLanguagePackException(
					$"Classic framebuffer key '{key}' is required.");
			}

			if (texts.TryGetValue(key, out string? text))
			{
				ValidateCompositeFormat(key, text, fallback);
			}
		}

		return texts;
	}

	private static ClassicDisplayNameCatalog ReadDisplayNames(
		JsonElement element)
	{
		JsonElement displayNames = RequireObject(
			element,
			"root.displayNames");
		Dictionary<string, JsonElement> sections = ReadProperties(
			displayNames,
			DisplayNameProperties,
			"root.displayNames");

		return new ClassicDisplayNameCatalog(
			ReadEnumDisplayNames<UnitTypeEnum>(
				RequireProperty(sections, "units", "root.displayNames"),
				"root.displayNames.units",
				type => type is not UnitTypeEnum.None and not UnitTypeEnum.Max),
			ReadEnumDisplayNames<TerrainTypeEnum>(
				RequireProperty(sections, "terrains", "root.displayNames"),
				"root.displayNames.terrains",
				type => type != TerrainTypeEnum.Invalid),
			ReadOptionalEnumDisplayNames<ImprovementEnum>(
				sections,
				"improvements",
				"root.displayNames.improvements",
				type => type != ImprovementEnum.None),
			ReadOptionalEnumDisplayNames<WonderEnum>(
				sections,
				"wonders",
				"root.displayNames.wonders",
				type => type != WonderEnum.None),
			ReadNationDisplayNames(
				RequireProperty(sections, "nations", "root.displayNames")));
	}

	private static IReadOnlyDictionary<TEnum, string>
		ReadOptionalEnumDisplayNames<TEnum>(
			IReadOnlyDictionary<string, JsonElement> sections,
			string sectionName,
			string path,
			Func<TEnum, bool> isAllowed)
		where TEnum : struct, Enum
	{
		return sections.TryGetValue(
			sectionName,
			out JsonElement section)
				? ReadEnumDisplayNames(section, path, isAllowed)
				: new Dictionary<TEnum, string>();
	}

	private static IReadOnlyDictionary<TEnum, string>
		ReadEnumDisplayNames<TEnum>(
			JsonElement element,
			string path,
			Func<TEnum, bool> isAllowed)
		where TEnum : struct, Enum
	{
		JsonElement objectElement = RequireObject(element, path);
		Dictionary<TEnum, string> values = new();
		HashSet<string> sourceNames = new(StringComparer.Ordinal);

		foreach (JsonProperty property in objectElement.EnumerateObject())
		{
			if (!sourceNames.Add(property.Name))
			{
				throw DuplicateProperty(path, property.Name);
			}

			if (!Enum.TryParse(
					property.Name,
					ignoreCase: false,
					out TEnum key) ||
				!Enum.IsDefined(key) ||
				!isAllowed(key))
			{
				throw new ClassicLanguagePackException(
					$"Unknown Classic display-name key " +
					$"'{path}.{property.Name}'.");
			}

			if (!values.TryAdd(
					key,
					ReadFramebufferString(
						property.Value,
						$"{path}.{property.Name}")))
			{
				throw new ClassicLanguagePackException(
					$"Duplicate Classic display-name key " +
					$"'{path}.{property.Name}'.");
			}
		}

		return values;
	}

	private static IReadOnlyDictionary<int, string> ReadNationDisplayNames(
		JsonElement element)
	{
		const string Path = "root.displayNames.nations";
		JsonElement objectElement = RequireObject(element, Path);
		Dictionary<int, string> values = new();
		HashSet<string> sourceNames = new(StringComparer.Ordinal);

		foreach (JsonProperty property in objectElement.EnumerateObject())
		{
			if (!sourceNames.Add(property.Name))
			{
				throw DuplicateProperty(Path, property.Name);
			}

			if (!int.TryParse(
					property.Name,
					NumberStyles.None,
					CultureInfo.InvariantCulture,
					out int nationID) ||
				nationID < 0 ||
				nationID > 15 ||
				nationID == 8)
			{
				throw new ClassicLanguagePackException(
					$"Unknown Classic nation display-name key " +
					$"'{property.Name}'.");
			}

			if (!values.TryAdd(
					nationID,
					ReadFramebufferString(
						property.Value,
						$"{Path}.{property.Name}")))
			{
				throw new ClassicLanguagePackException(
					$"Duplicate Classic nation display-name key " +
					$"'{property.Name}'.");
			}
		}

		return values;
	}

	private static Dictionary<string, JsonElement> ReadProperties(
		JsonElement element,
		IReadOnlySet<string> allowedProperties,
		string path)
	{
		Dictionary<string, JsonElement> values =
			new(StringComparer.Ordinal);
		foreach (JsonProperty property in element.EnumerateObject())
		{
			if (!allowedProperties.Contains(property.Name))
			{
				throw new ClassicLanguagePackException(
					$"Unknown property '{path}.{property.Name}'.");
			}

			if (!values.TryAdd(property.Name, property.Value))
			{
				throw DuplicateProperty(path, property.Name);
			}
		}

		return values;
	}

	private static JsonElement RequireProperty(
		IReadOnlyDictionary<string, JsonElement> values,
		string name,
		string path)
	{
		return values.TryGetValue(name, out JsonElement value)
			? value
			: throw new ClassicLanguagePackException(
				$"Required property '{path}.{name}' is missing.");
	}

	private static JsonElement RequireObject(JsonElement element, string path)
	{
		if (element.ValueKind != JsonValueKind.Object)
		{
			throw new ClassicLanguagePackException(
				$"'{path}' must be a JSON object.");
		}

		return element;
	}

	private static string RequireString(JsonElement element, string path)
	{
		if (element.ValueKind != JsonValueKind.String)
		{
			throw new ClassicLanguagePackException(
				$"'{path}' must be a string.");
		}

		return element.GetString() ??
			throw new ClassicLanguagePackException(
				$"'{path}' must not be null.");
	}

	private static int RequireInt32(JsonElement element, string path)
	{
		if (element.ValueKind != JsonValueKind.Number ||
			!element.TryGetInt32(out int value))
		{
			throw new ClassicLanguagePackException(
				$"'{path}' must be an integer.");
		}

		return value;
	}

	private static string ReadFramebufferString(
		JsonElement element,
		string path)
	{
		string value = RequireString(element, path);
		if (value.Length == 0)
		{
			throw new ClassicLanguagePackException(
				$"'{path}' must not be empty.");
		}

		for (int index = 0; index < value.Length; index++)
		{
			if (value[index] > '\x7f')
			{
				throw new ClassicLanguagePackException(
					$"'{path}' contains non-renderable character " +
					$"U+{(int)value[index]:X4}.");
			}
		}

		return value;
	}

	private static void ValidateCompositeFormat(
		ClassicGameTextKey key,
		string text,
		ClassicGameTextCatalog? fallback)
	{
		IReadOnlyList<int> actual = GetPlaceholderSignature(text, key);
		if (fallback is null)
		{
			return;
		}

		IReadOnlyList<int> expected = GetPlaceholderSignature(
			fallback[key],
			key);
		if (!actual.SequenceEqual(expected))
		{
			throw new ClassicLanguagePackException(
				$"Classic framebuffer key '{key}' does not preserve " +
				"the English format placeholders.");
		}
	}

	private static IReadOnlyList<int> GetPlaceholderSignature(
		string format,
		ClassicGameTextKey key)
	{
		try
		{
			CompositeFormat compositeFormat = CompositeFormat.Parse(format);
			List<int> calls = new();
			object?[] arguments = Enumerable.Range(
					0,
					compositeFormat.MinimumArgumentCount)
				.Select(index => (object?)new PlaceholderProbe(index, calls))
				.ToArray();
			_ = string.Format(
				CultureInfo.InvariantCulture,
				compositeFormat,
				arguments);
			calls.Sort();
			return calls;
		}
		catch (FormatException exception)
		{
			throw new ClassicLanguagePackException(
				$"Classic framebuffer key '{key}' has an invalid " +
				"composite format.",
				exception);
		}
	}

	private static ClassicLanguagePackException DuplicateProperty(
		string path,
		string propertyName)
	{
		return new ClassicLanguagePackException(
			$"Duplicate property '{path}.{propertyName}'.");
	}

	private static string NormalizeLanguageCode(string languageCode)
	{
		if (string.IsNullOrWhiteSpace(languageCode))
		{
			throw new ClassicLanguagePackException(
				"Classic language code must not be empty.");
		}

		string neutralLanguage = languageCode
			.Split(['-', '_'], 2, StringSplitOptions.RemoveEmptyEntries)[0]
			.Trim()
			.ToLowerInvariant();
		if (neutralLanguage.Length != 2 ||
			neutralLanguage.Any(character =>
				character is < 'a' or > 'z'))
		{
			throw new ClassicLanguagePackException(
				$"Classic language code '{languageCode}' is invalid.");
		}

		return neutralLanguage;
	}

	private sealed class PlaceholderProbe : IFormattable
	{
		private readonly int index;
		private readonly List<int> calls;

		public PlaceholderProbe(int index, List<int> calls)
		{
			this.index = index;
			this.calls = calls;
		}

		public string ToString(string? format, IFormatProvider? formatProvider)
		{
			this.calls.Add(this.index);
			return this.index.ToString(CultureInfo.InvariantCulture);
		}

		public override string ToString()
		{
			this.calls.Add(this.index);
			return this.index.ToString(CultureInfo.InvariantCulture);
		}
	}
}
