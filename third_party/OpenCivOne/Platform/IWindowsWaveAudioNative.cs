using System.Runtime.InteropServices;

namespace OpenCivOne.Platform;

/// <summary>
/// Isolates WinMM waveform playback for deterministic tests.
/// </summary>
public interface IWindowsWaveAudioNative
{
	bool IsSupported { get; }

	bool PlayFile(string filePath, uint flags);

	bool Stop();
}

internal sealed class WinMmWaveAudioNative : IWindowsWaveAudioNative
{
	public bool IsSupported => OperatingSystem.IsWindows();

	public bool PlayFile(string filePath, uint flags)
	{
		return PlaySound(filePath, nint.Zero, flags);
	}

	public bool Stop()
	{
		return PlaySound(null, nint.Zero, 0);
	}

	[DllImport(
		"winmm.dll",
		EntryPoint = "PlaySoundW",
		CharSet = CharSet.Unicode,
		ExactSpelling = true)]
	[return: MarshalAs(UnmanagedType.Bool)]
	private static extern bool PlaySound(
		string? sound,
		nint module,
		uint flags);
}
