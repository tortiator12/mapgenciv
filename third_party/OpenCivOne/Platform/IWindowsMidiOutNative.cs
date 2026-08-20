using System.Runtime.InteropServices;
using System.Text;

namespace OpenCivOne.Platform;

/// <summary>
/// Isolates the WinMM MIDI-out calls so command encoding and lifecycle
/// behavior can be verified without opening audio hardware.
/// </summary>
public interface IWindowsMidiOutNative
{
	/// <summary>
	/// Indicates whether this native implementation can be used on the
	/// current platform.
	/// </summary>
	bool IsSupported { get; }

	uint Open(out nint handle, uint deviceId);

	uint SendShortMessage(nint handle, uint message);

	uint Reset(nint handle);

	uint Close(nint handle);

	string GetErrorText(uint resultCode);
}

internal sealed class WinMmMidiOutNative : IWindowsMidiOutNative
{
	private const uint NoError = 0;
	private const int ErrorTextCapacity = 256;

	public bool IsSupported => OperatingSystem.IsWindows();

	public uint Open(out nint handle, uint deviceId)
	{
		if (!this.IsSupported)
		{
			handle = nint.Zero;
			throw new PlatformNotSupportedException(
				"WinMM MIDI output is available only on Windows.");
		}

		return MidiOutOpen(
			out handle,
			deviceId,
			nint.Zero,
			nint.Zero,
			0);
	}

	public uint SendShortMessage(nint handle, uint message)
	{
		return MidiOutShortMessage(handle, message);
	}

	public uint Reset(nint handle)
	{
		return MidiOutReset(handle);
	}

	public uint Close(nint handle)
	{
		return MidiOutClose(handle);
	}

	public string GetErrorText(uint resultCode)
	{
		StringBuilder text = new(ErrorTextCapacity);
		uint errorTextResult = MidiOutGetErrorText(
			resultCode,
			text,
			(uint)text.Capacity);
		return errorTextResult == NoError && text.Length > 0
			? text.ToString()
			: $"WinMM MIDI error {resultCode}.";
	}

	[DllImport(
		"winmm.dll",
		EntryPoint = "midiOutOpen",
		ExactSpelling = true)]
	private static extern uint MidiOutOpen(
		out nint handle,
		uint deviceId,
		nint callback,
		nint instance,
		uint flags);

	[DllImport(
		"winmm.dll",
		EntryPoint = "midiOutShortMsg",
		ExactSpelling = true)]
	private static extern uint MidiOutShortMessage(
		nint handle,
		uint message);

	[DllImport(
		"winmm.dll",
		EntryPoint = "midiOutReset",
		ExactSpelling = true)]
	private static extern uint MidiOutReset(nint handle);

	[DllImport(
		"winmm.dll",
		EntryPoint = "midiOutClose",
		ExactSpelling = true)]
	private static extern uint MidiOutClose(nint handle);

	[DllImport(
		"winmm.dll",
		EntryPoint = "midiOutGetErrorTextW",
		CharSet = CharSet.Unicode,
		ExactSpelling = true)]
	private static extern uint MidiOutGetErrorText(
		uint resultCode,
		StringBuilder text,
		uint textLength);
}
