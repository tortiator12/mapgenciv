using IRB.VirtualCPU;

namespace OpenCivOne.Input;

/// <summary>
/// Resolves pointer movement and hover selection for a classic menu box
/// without changing its original 320x200 geometry.
/// </summary>
public static class ClassicMenuPointerSelection
{
	public static bool HasMoved(int currentX, int currentY, int previousX, int previousY)
	{
		return currentX != previousX || currentY != previousY;
	}

	public static bool ShouldUpdateHover(
		int currentX,
		int currentY,
		int previousX,
		int previousY,
		bool isButtonDown)
	{
		return isButtonDown || HasMoved(currentX, currentY, previousX, previousY);
	}

	public static bool ShouldConfirmSelection(
		MouseButtonsEnum buttons,
		bool optionResolvedFromCurrentEvent,
		int selectedOptionIndex,
		int previousSelectedOptionIndex,
		int disabledOptions)
	{
		if (buttons != MouseButtonsEnum.Left || selectedOptionIndex < 0)
		{
			return false;
		}

		bool selectedOptionIsDisabled =
			(disabledOptions & (0x1 << selectedOptionIndex)) != 0;

		if (selectedOptionIsDisabled)
		{
			return false;
		}

		if (selectedOptionIndex == previousSelectedOptionIndex)
		{
			return true;
		}

		return optionResolvedFromCurrentEvent;
	}

	public static bool TryGetOptionIndex(
		int pointerY,
		int contentTop,
		int lineHeight,
		IReadOnlyList<int> optionLines,
		out int optionIndex)
	{
		ArgumentOutOfRangeException.ThrowIfNegativeOrZero(lineHeight);
		ArgumentNullException.ThrowIfNull(optionLines);

		int selectedLine = (pointerY - contentTop) / lineHeight;

		for (int i = 0; i < optionLines.Count; i++)
		{
			if (selectedLine == optionLines[i])
			{
				optionIndex = i;
				return true;
			}
		}

		optionIndex = -1;
		return false;
	}
}
