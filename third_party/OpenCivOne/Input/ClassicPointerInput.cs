using IRB.VirtualCPU;
using OpenCivOne.Graphics;

namespace OpenCivOne.Input;

/// <summary>
/// Translates host pointer coordinates to the original 320x200 input space
/// and preserves OpenCivOne's mouse-event coalescing behavior.
/// </summary>
public sealed class ClassicPointerInput
{
	public const int LogicalWidth = 320;
	public const int LogicalHeight = 200;

	private MouseEvent lastEvent = new(
		new GPoint(LogicalWidth / 2, LogicalHeight / 2),
		MouseButtonsEnum.None);

	public bool Submit(
		int x,
		int y,
		int inputWidth,
		int inputHeight,
		MouseButtonsEnum buttons,
		IList<MouseEvent> events)
	{
		ArgumentOutOfRangeException.ThrowIfNegativeOrZero(inputWidth);
		ArgumentOutOfRangeException.ThrowIfNegativeOrZero(inputHeight);
		ArgumentNullException.ThrowIfNull(events);

		if (x < 0 || x >= inputWidth || y < 0 || y >= inputHeight)
		{
			return false;
		}

		GPoint position = new(
			(int)((long)x * LogicalWidth / inputWidth),
			(int)((long)y * LogicalHeight / inputHeight));

		if (this.lastEvent.Position == position && this.lastEvent.Buttons == buttons)
		{
			return false;
		}

		this.lastEvent = new MouseEvent(position, buttons);

		if (buttons == MouseButtonsEnum.None)
		{
			if (events.Count > 0 && events[events.Count - 1].Buttons == MouseButtonsEnum.None)
			{
				events.RemoveAt(events.Count - 1);
			}

			events.Add(this.lastEvent);
			return true;
		}

		if (events.Count == 0 || events[events.Count - 1].Buttons != buttons)
		{
			events.Add(this.lastEvent);
			return true;
		}

		return false;
	}
}
