using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using OpenCivOne;
using OpenCivOne.Platform;
using OpenCivOne.Runtime;

// Exports OpenCivOne-generated maps into civ-mapproto snapshot JSON.
// Usage:
//   dotnet run --project tools/OpenCivOneExport -- <output-dir> [count]
//   dotnet run --project tools/OpenCivOneExport -- --single <file.json> <seed> <land> <temp> <climate> <age>
// Default count=12 (fixed beta seeds). count=100 for stress corpus.
//
// --single writes exactly one snapshot for an explicitly chosen seed, which is
// what a game start needs: the corpus formula below only reaches its own fixed
// 81-combination sequence and cannot express an arbitrary world.

const int WorldWidth = 80;
const int WorldHeight = 50;

if (args.Length > 0 && args[0] == "--single")
	return WriteSingle(args);

string outputPath = Path.GetFullPath(args.Length > 0 ? args[0] : "snapshots/opencivone");
int count = args.Length > 1 && int.TryParse(args[1], out int n) ? n : 12;
Directory.CreateDirectory(outputPath);
Directory.CreateDirectory(Path.Combine(outputPath, "maps"));

JsonSerializerOptions jsonOptions = new() { WriteIndented = true };
List<object> index = [];

for (int i = 0; i < count; i++)
{
	WorldConfiguration configuration = ConfigurationFor(i);
	using RuntimeFixture fixture = new();
	GenerateWorld(fixture.Game, configuration);
	int[][] terrain = CaptureTerrainIds(fixture.Game);
	string[][] names = CaptureTerrainNames(fixture.Game);
	string fingerprint = Fingerprint(names);

	var snap = new
	{
		schema = "civ-mapproto.snapshot/v1",
		authority = "OpenCivOne",
		width = WorldWidth,
		height = WorldHeight,
		seed = configuration.Seed,
		land_mass = configuration.LandMass,
		temperature = configuration.Temperature,
		climate = configuration.Climate,
		age = configuration.Age,
		fingerprint,
		terrain = terrain, // row-major int ids matching civ1.mapgen.Terrain
		terrain_names = names.Select(row => string.Join(',', row)).ToArray(),
	};

	string fileName = $"oco_seed_{configuration.Seed}.json";
	string path = Path.Combine(outputPath, "maps", fileName);
	File.WriteAllText(path, JsonSerializer.Serialize(snap, jsonOptions));
	index.Add(new
	{
		file = $"maps/{fileName}",
		seed = configuration.Seed,
		land_mass = configuration.LandMass,
		temperature = configuration.Temperature,
		climate = configuration.Climate,
		age = configuration.Age,
		fingerprint,
	});
	Console.WriteLine($"{i + 1,3}/{count}: seed={configuration.Seed} fp={fingerprint[..12]}");
}

File.WriteAllText(Path.Combine(outputPath, "index.json"),
	JsonSerializer.Serialize(new
	{
		schema = "civ-mapproto.snapshot-index/v1",
		authority = "OpenCivOne",
		count,
		maps = index,
	}, jsonOptions));

Console.WriteLine($"Wrote {count} snapshots -> {outputPath}");
return 0;

// One world, one file, caller-chosen seed and parameters. Same generator call
// and same snapshot schema as the corpus path above, so a snapshot produced
// here is indistinguishable from a corpus one downstream.
static int WriteSingle(string[] args)
{
	if (args.Length < 7)
	{
		Console.Error.WriteLine(
			"usage: --single <file.json> <seed> <land 0-2> <temp 0-2> <climate 0-2> <age 0-2>");
		return 2;
	}

	string file = Path.GetFullPath(args[1]);
	if (!ushort.TryParse(args[2], out ushort seed))
	{
		Console.Error.WriteLine($"seed must be 0..65535, got {args[2]}");
		return 2;
	}

	int[] parameters = new int[4];
	for (int i = 0; i < 4; i++)
	{
		if (!int.TryParse(args[3 + i], out parameters[i]) || parameters[i] is < 0 or > 2)
		{
			Console.Error.WriteLine($"world parameters must be 0..2, got {args[3 + i]}");
			return 2;
		}
	}

	WorldConfiguration configuration = new(seed, parameters[0], parameters[1],
		parameters[2], parameters[3]);
	using RuntimeFixture fixture = new();
	GenerateWorld(fixture.Game, configuration);
	int[][] terrain = CaptureTerrainIds(fixture.Game);
	string[][] names = CaptureTerrainNames(fixture.Game);
	string fingerprint = Fingerprint(names);

	string? directory = Path.GetDirectoryName(file);
	if (!string.IsNullOrEmpty(directory))
		Directory.CreateDirectory(directory);

	File.WriteAllText(file, JsonSerializer.Serialize(new
	{
		schema = "civ-mapproto.snapshot/v1",
		authority = "OpenCivOne",
		width = WorldWidth,
		height = WorldHeight,
		seed = configuration.Seed,
		land_mass = configuration.LandMass,
		temperature = configuration.Temperature,
		climate = configuration.Climate,
		age = configuration.Age,
		fingerprint,
		terrain,
		terrain_names = names.Select(row => string.Join(',', row)).ToArray(),
	}, new JsonSerializerOptions { WriteIndented = true }));

	Console.WriteLine($"seed={configuration.Seed} fp={fingerprint[..12]} -> {file}");
	return 0;
}

static WorldConfiguration ConfigurationFor(int index)
{
	// Same formula as Project1991.WorldCorpusAnalyzer — reproducible corpus.
	int combination = index % 81;
	return new WorldConfiguration(checked((ushort)(1991 + (index * 257))),
		combination % 3, (combination / 3) % 3,
		(combination / 9) % 3, (combination / 27) % 3);
}

static void GenerateWorld(OpenCivOneGame game, WorldConfiguration configuration)
{
	game.GameData.RandomSeed = configuration.Seed;
	game.CAPI.srand(configuration.Seed);
	game.Var_d76a_EarthMap = false;
	game.Var_7ef6_PlanetLandMass = configuration.LandMass;
	game.Var_7ef8_PlanetTemperature = configuration.Temperature;
	game.Var_7efa_PlanetClimate = configuration.Climate;
	game.Var_7efc_PlanetAge = configuration.Age;
	game.MapInitAndIntro.F7_0000_0012_GenerateMap();
}

static int[][] CaptureTerrainIds(OpenCivOneGame game)
{
	int[][] result = new int[WorldHeight][];
	for (int y = 0; y < WorldHeight; y++)
	{
		result[y] = new int[WorldWidth];
		for (int x = 0; x < WorldWidth; x++)
		{
			result[y][x] = ToTerrainId(game.MapManagement.GetTerrainType(x, y));
		}
	}
	return result;
}

static string[][] CaptureTerrainNames(OpenCivOneGame game)
{
	string[][] result = new string[WorldHeight][];
	for (int y = 0; y < WorldHeight; y++)
	{
		result[y] = new string[WorldWidth];
		for (int x = 0; x < WorldWidth; x++)
		{
			result[y][x] = NormalizeTerrain(game.MapManagement.GetTerrainType(x, y));
		}
	}
	return result;
}

// Matches civ1.mapgen.Terrain IntEnum ordinals.
static int ToTerrainId(TerrainTypeEnum terrain) => NormalizeTerrain(terrain) switch
{
	"Desert" => 0,
	"Plains" => 1,
	"Grassland" => 2,
	"Forest" => 3,
	"Hills" => 4,
	"Mountains" => 5,
	"Tundra" => 6,
	"Arctic" => 7,
	"Swamp" => 8,
	"Jungle" => 9,
	"Water" => 10,
	"River" => 11,
	_ => throw new InvalidOperationException($"Unexpected {terrain}"),
};

static string NormalizeTerrain(TerrainTypeEnum terrain) => terrain switch
{
	TerrainTypeEnum.Desert or TerrainTypeEnum.ResourceOasis => "Desert",
	TerrainTypeEnum.Plains or TerrainTypeEnum.ResourceHorses => "Plains",
	TerrainTypeEnum.Grassland or TerrainTypeEnum.ResourceGrassland => "Grassland",
	TerrainTypeEnum.Forest or TerrainTypeEnum.ResourceGame => "Forest",
	TerrainTypeEnum.Hills or TerrainTypeEnum.ResourceCoal => "Hills",
	TerrainTypeEnum.Mountains or TerrainTypeEnum.ResourceGold => "Mountains",
	TerrainTypeEnum.Tundra or TerrainTypeEnum.ResourceGame2 => "Tundra",
	TerrainTypeEnum.Arctic or TerrainTypeEnum.ResourceSeals => "Arctic",
	TerrainTypeEnum.Swamp or TerrainTypeEnum.ResourceOil => "Swamp",
	TerrainTypeEnum.Jungle or TerrainTypeEnum.ResourceGems => "Jungle",
	TerrainTypeEnum.Water or TerrainTypeEnum.ResourceFish => "Water",
	TerrainTypeEnum.River or TerrainTypeEnum.ResourceRiver => "River",
	_ => throw new InvalidOperationException($"Unexpected terrain {terrain}."),
};

static string Fingerprint(string[][] terrain) => Convert.ToHexString(
	SHA256.HashData(Encoding.UTF8.GetBytes(string.Join('\n',
		terrain.Select(row => string.Join(',', row)))))).ToLowerInvariant();

sealed record WorldConfiguration(ushort Seed, int LandMass, int Temperature, int Climate, int Age);

sealed class RuntimeFixture : IDisposable
{
	private readonly string rootPath;
	public RuntimeFixture()
	{
		rootPath = Path.Combine(Path.GetTempPath(), "CivMapProto.OpenCivOneExport",
			Guid.NewGuid().ToString("N"));
		ClassicRuntimeOptions options = new(Path.Combine(rootPath, "resources"),
			Path.Combine(rootPath, "runtime", "saves"),
			Path.Combine(rootPath, "runtime", "logs"));
		Directory.CreateDirectory(options.ResourcePath);
		File.WriteAllText(options.GetResourceFilePath("STORY.TXT"), string.Empty);
		Game = new OpenCivOneGame(new InspectorHost(), options);
		Game.CPU.SP.UInt16 = 0xfffe;
		Game.Graphics.F0_VGA_04ae_AllocateScreen(1);
		Game.Graphics.F0_VGA_04ae_AllocateScreen(2);
	}
	public OpenCivOneGame Game { get; }
	public void Dispose()
	{
		Game.CommonTools.StopGameMainTimer();
		if (Directory.Exists(rootPath)) Directory.Delete(rootPath, recursive: true);
	}
}

sealed class InspectorHost : IClassicGameHost
{
	public string? ShowTextInput(string title, string? placeholderText,
		string? defaultValue, int maxTextLength, bool allowEmptyText) => defaultValue;
	public void ShowInformation(string text, string title) { }
}
