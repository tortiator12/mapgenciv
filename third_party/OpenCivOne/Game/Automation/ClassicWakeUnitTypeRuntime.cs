using OpenCivOne.Runtime;

namespace OpenCivOne
{
	public static class ClassicWakeUnitTypeRuntime
	{
		private const UnitStatusEnum SleepingStatuses =
			UnitStatusEnum.Sentry |
			UnitStatusEnum.Fortifying |
			UnitStatusEnum.Fortified;

		public static int TryWakeAll(
			GameData gameData,
			int playerID,
			UnitTypeEnum unitType)
		{
			ArgumentNullException.ThrowIfNull(gameData);
			if (!ClassicAiRuntimeProfiles.UsesSmartEnhancements(
					gameData.AiProfile) ||
				playerID != gameData.HumanPlayerID ||
				playerID < 0 ||
				playerID >= gameData.Players.Length ||
				unitType is UnitTypeEnum.None or UnitTypeEnum.Max)
			{
				return 0;
			}

			int wakeCount = 0;
			foreach (Unit unit in gameData.Players[playerID].Units)
			{
				if (unit.UnitType != unitType ||
					(unit.Status & SleepingStatuses) ==
						UnitStatusEnum.None)
				{
					continue;
				}

				unit.ClearStatusFlags(SleepingStatuses);
				wakeCount++;
			}

			return wakeCount;
		}
	}
}
