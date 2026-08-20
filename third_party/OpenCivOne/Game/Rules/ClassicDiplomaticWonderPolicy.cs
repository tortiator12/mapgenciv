namespace OpenCivOne
{
	public readonly record struct ClassicDiplomaticWonderPressureState(
		ushort StrategicAggression,
		ushort TributeDemand,
		short ContactCountdown);

	public static class ClassicDiplomaticWonderPolicy
	{
		public static ClassicDiplomaticWonderPressureState Apply(
			bool humanOwnsGreatWall,
			bool humanOwnsUnitedNations,
			ClassicDiplomaticWonderPressureState state)
		{
			if (!humanOwnsGreatWall &&
				!humanOwnsUnitedNations)
			{
				return state;
			}

			return state with
			{
				StrategicAggression = 0,
				TributeDemand = 0,
				ContactCountdown =
					state.ContactCountdown == -2
						? (short)-1
						: state.ContactCountdown
			};
		}
	}
}
