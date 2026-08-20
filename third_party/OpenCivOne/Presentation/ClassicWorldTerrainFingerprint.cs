using System.Security.Cryptography;
using System.Text;

namespace OpenCivOne.Presentation;

/// <summary>
/// Opaque identity of the static terrain matrix. Resource presentation
/// variants are normalized to their owning terrain. Improvements, cities,
/// units, visibility and turn state are intentionally excluded.
/// </summary>
public static class ClassicWorldTerrainFingerprint
{
	public static string Compute(
		int width,
		int height,
		Func<int, int, TerrainTypeEnum> getTerrain)
	{
		ArgumentOutOfRangeException.ThrowIfNegativeOrZero(width);
		ArgumentOutOfRangeException.ThrowIfNegativeOrZero(height);
		ArgumentNullException.ThrowIfNull(getTerrain);

		StringBuilder canonical = new(checked(width * height * 8));
		for (int y = 0; y < height; y++)
		{
			for (int x = 0; x < width; x++)
			{
				if (canonical.Length > 0)
				{
					canonical.Append('\n');
				}

				canonical.Append(Normalize(getTerrain(x, y)));
			}
		}

		return Convert.ToHexString(
			SHA256.HashData(Encoding.UTF8.GetBytes(canonical.ToString())))
			.ToLowerInvariant();
	}

	public static string Normalize(TerrainTypeEnum terrain)
	{
		if (terrain is >= TerrainTypeEnum.ResourceOasis and
			<= TerrainTypeEnum.ResourceRiver)
		{
			terrain = (TerrainTypeEnum)(
				(int)terrain - (int)TerrainTypeEnum.ResourceOasis);
		}

		return terrain is >= TerrainTypeEnum.Desert and <= TerrainTypeEnum.River
			? terrain.ToString()
			: "Invalid";
	}
}
