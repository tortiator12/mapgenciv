namespace OpenCivOne;

public enum ClassicSaveSlotStatus
{
	Empty,
	LegacyCompatible,
	ClassicCompatible,
	ProfileUnavailable,
	Invalid,
}

public readonly record struct ClassicSaveSlotInfo(
	ClassicSaveSlotStatus Status,
	string DisplayText)
{
	public bool CanLoad =>
		this.Status is
			ClassicSaveSlotStatus.LegacyCompatible or
			ClassicSaveSlotStatus.ClassicCompatible;
}
