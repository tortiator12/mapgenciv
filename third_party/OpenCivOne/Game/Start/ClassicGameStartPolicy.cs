namespace OpenCivOne
{
	public enum ClassicGameStartMode
	{
		None = -1,
		RandomWorld = 0,
		LoadSavedGame = 1,
		Earth = 2,
		CustomizedWorld = 3,
		HallOfFame = 4
	}

	public static class ClassicGameStartPolicy
	{
		public static bool ShouldReturnToMainMenu(
			int gameEndType)
		{
			return gameEndType is -1 or 2;
		}

		public static bool RequiresNewGameInitialization(int selectedGameType)
		{
			return (ClassicGameStartMode)selectedGameType is
				ClassicGameStartMode.RandomWorld or
				ClassicGameStartMode.Earth or
				ClassicGameStartMode.CustomizedWorld;
		}

		public static void InitializeNewGameDataIfRequired(
			int selectedGameType,
			Action initializeNewGameData)
		{
			ArgumentNullException.ThrowIfNull(initializeNewGameData);

			if (RequiresNewGameInitialization(selectedGameType))
			{
				initializeNewGameData();
			}
		}
	}
}
