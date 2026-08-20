namespace OpenCivOne;

public static class ClassicCityCapturePolicy
{
	public static short ResolveShortTune(
		GameData gameData,
		int playerID)
	{
		if (playerID < 0 ||
			playerID >= gameData.Players.Length)
		{
			return 0;
		}

		int nationalityID =
			gameData.Players[playerID].NationalityID;
		if (nationalityID < 0 ||
			nationalityID >= gameData.Nations.Length)
		{
			nationalityID = playerID == 0 ? 0 : -1;
		}

		return nationalityID >= 0
			? (short)gameData.Nations[nationalityID].ShortTune
			: (short)0;
	}

	public static bool HasCityOrSettler(
		GameData gameData,
		int playerID)
	{
		if (playerID < 0 ||
			playerID >= gameData.Players.Length)
		{
			return false;
		}

		foreach (City city in gameData.Cities)
		{
			if (city.StatusFlag != byte.MaxValue &&
				city.ActualSize > 0 &&
				city.PlayerID == playerID)
			{
				return true;
			}
		}

		for (int unitID = 0; unitID < 128; unitID++)
		{
			if (gameData.Players[playerID]
					.Units[unitID]
					.UnitType == UnitTypeEnum.Settler)
			{
				return true;
			}
		}

		return false;
	}
}
