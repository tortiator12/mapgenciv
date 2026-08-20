using System.Runtime.InteropServices;

namespace OpenCivOne.Platform;

/// <summary>
/// Serialized WinMM WAV playback owned by the Classic audio worker.
/// </summary>
/// <remarks>
/// File validation and every native call must be made from the existing
/// <see cref="RolandCvlAudioSink"/> worker, never from the game or UI thread.
/// </remarks>
public sealed class WindowsWaveAudioPlayer : IDisposable
{
	// The Win16 executable used asynchronous sndPlaySound without SND_NOSTOP,
	// so each new cue replaced the prior cue. PlaySoundW with an explicit file
	// name preserves that behavior. NODEFAULT prevents an invented system beep
	// if a OneDrive-backed file becomes unavailable.
	internal const uint PlaybackFlags =
		0x0001 | // SND_ASYNC
		0x0002 | // SND_NODEFAULT
		0x00020000; // SND_FILENAME

	private readonly object synchronization = new();
	private readonly IWindowsWaveAudioNative native;
	private string? lastFailure;
	private bool initialized;
	private bool disposed;

	public WindowsWaveAudioPlayer()
		: this(new WinMmWaveAudioNative())
	{
	}

	public WindowsWaveAudioPlayer(IWindowsWaveAudioNative native)
	{
		ArgumentNullException.ThrowIfNull(native);
		this.native = native;
	}

	public bool IsAvailable
	{
		get
		{
			lock (this.synchronization)
			{
				return
					!this.disposed &&
					this.native.IsSupported;
			}
		}
	}

	public string? LastFailure
	{
		get
		{
			lock (this.synchronization)
			{
				return this.lastFailure;
			}
		}
	}

	public void Initialize()
	{
		lock (this.synchronization)
		{
			if (this.disposed)
			{
				throw new ObjectDisposedException(
					nameof(WindowsWaveAudioPlayer));
			}

			if (!this.native.IsSupported)
			{
				throw new PlatformNotSupportedException(
					"WinMM waveform playback is available only on Windows.");
			}

			this.lastFailure = null;
			this.initialized = true;
		}
	}

	public bool TryPlayFile(string filePath)
	{
		lock (this.synchronization)
		{
			if (!this.initialized || this.disposed)
			{
				this.lastFailure =
					"The Civilization for Windows WAV player is not initialized.";
				return false;
			}

			if (!Path.IsPathFullyQualified(filePath) ||
				!CivWinWaveCatalog.IsPcmWaveFile(filePath))
			{
				this.lastFailure =
					$"The mapped WAV is missing or is not original-format " +
					$"PCM mono/11025 Hz/8-bit audio: {filePath}";
				return false;
			}

			try
			{
				if (this.native.PlayFile(filePath, PlaybackFlags))
				{
					this.lastFailure = null;
					return true;
				}

				this.lastFailure =
					$"WinMM refused mapped WAV playback: {filePath}";
				return false;
			}
			catch (Exception exception)
				when (IsExpectedPlaybackFailure(exception))
			{
				this.lastFailure =
					$"WinMM WAV playback failed ({exception.GetType().Name}): " +
					exception.Message;
				return false;
			}
		}
	}

	public bool TryStop()
	{
		lock (this.synchronization)
		{
			return this.TryStopCore();
		}
	}

	private bool TryStopCore()
	{
		if (!this.initialized || this.disposed)
		{
			return true;
		}

		try
		{
			if (this.native.Stop())
			{
				this.lastFailure = null;
				return true;
			}

			this.lastFailure = "WinMM refused to stop WAV playback.";
			return false;
		}
		catch (Exception exception)
			when (IsExpectedPlaybackFailure(exception))
		{
			this.lastFailure =
				$"WinMM WAV stop failed ({exception.GetType().Name}): " +
				exception.Message;
			return false;
		}
	}

	public void Close()
	{
		lock (this.synchronization)
		{
			if (this.disposed)
			{
				return;
			}

			if (this.initialized && !this.TryStopCore())
			{
				throw new InvalidOperationException(this.lastFailure);
			}

			this.initialized = false;
			this.disposed = true;
		}
	}

	public void Dispose()
	{
		this.Close();
	}

	private static bool IsExpectedPlaybackFailure(Exception exception)
	{
		return exception is
			IOException or
			UnauthorizedAccessException or
			DllNotFoundException or
			EntryPointNotFoundException or
			BadImageFormatException or
			ExternalException;
	}
}
