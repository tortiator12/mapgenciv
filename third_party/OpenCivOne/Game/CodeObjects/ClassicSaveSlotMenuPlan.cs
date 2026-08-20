using OpenCivOne.Localization;
using System.Text;

namespace OpenCivOne;

public enum ClassicSaveDialogPurpose
{
	Load,
	Save,
}

public readonly record struct ClassicSaveSlotMenuPlan(
	string Text,
	int DisabledOptionsMask,
	int DefaultOptionIndex)
{
	public static ClassicSaveSlotMenuPlan Create(
		IReadOnlyList<ClassicSaveSlotInfo> slots,
		ClassicSaveDialogPurpose purpose,
		int preferredOptionIndex = 0)
	{
		ArgumentNullException.ThrowIfNull(slots);

		ClassicGameTextKey titleKey =
			purpose == ClassicSaveDialogPurpose.Load
				? ClassicGameTextKey.LoadGameMenuTitle
				: ClassicGameTextKey.SaveGameMenuTitle;
		StringBuilder text = new();
		text.Append('\x008c');
		text.Append(ClassicGameText.Current[titleKey]);
		text.Append('\n');

		int disabledOptionsMask = 0;
		for (int index = 0; index < slots.Count; index++)
		{
			ClassicSaveSlotInfo slot = slots[index];
			text.Append(slot.DisplayText);
			if (purpose == ClassicSaveDialogPurpose.Load &&
				!slot.CanLoad)
			{
				disabledOptionsMask |= 0x1 << index;
			}
		}

		int defaultOptionIndex =
			FindDefaultOption(
				slots,
				purpose,
				preferredOptionIndex);
		return new ClassicSaveSlotMenuPlan(
			text.ToString(),
			disabledOptionsMask,
			defaultOptionIndex);
	}

	private static int FindDefaultOption(
		IReadOnlyList<ClassicSaveSlotInfo> slots,
		ClassicSaveDialogPurpose purpose,
		int preferredOptionIndex)
	{
		if (slots.Count == 0)
		{
			return -1;
		}

		if (purpose == ClassicSaveDialogPurpose.Save)
		{
			return Math.Clamp(
				preferredOptionIndex,
				0,
				slots.Count - 1);
		}

		if (preferredOptionIndex >= 0 &&
			preferredOptionIndex < slots.Count &&
			slots[preferredOptionIndex].CanLoad)
		{
			return preferredOptionIndex;
		}

		for (int index = 0; index < slots.Count; index++)
		{
			if (slots[index].CanLoad)
			{
				return index;
			}
		}

		return -1;
	}
}
