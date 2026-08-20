namespace OpenCivOne;

/// <summary>
/// Source-faithful Civilization 1 zone-of-control transition rule.
/// The rule is shared by Original 1991 and 1991+; the latter may improve
/// route selection, but it must not make otherwise illegal moves legal.
/// </summary>
public static class ClassicZoneOfControlPolicy
{
	public static bool Applies(
		UnitMovementTypeEnum movementType,
		UnitTypeEnum unitType,
		TerrainTypeEnum sourceTerrain,
		bool destinationOccupied)
	{
		return movementType == UnitMovementTypeEnum.Land &&
			unitType is not UnitTypeEnum.Diplomat and
				not UnitTypeEnum.Caravan &&
			sourceTerrain != TerrainTypeEnum.Water &&
			!destinationOccupied;
	}

	public static bool Blocks(
		UnitMovementTypeEnum movementType,
		UnitTypeEnum unitType,
		TerrainTypeEnum sourceTerrain,
		bool destinationOccupied,
		bool sourceInEnemyControl,
		bool destinationInEnemyControl)
	{
		return Applies(
				movementType,
				unitType,
				sourceTerrain,
				destinationOccupied) &&
			sourceInEnemyControl &&
			destinationInEnemyControl;
	}
}
