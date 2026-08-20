namespace OpenCivOne.Platform;

/// <summary>
/// Receives the legacy tune commands without exposing a platform audio API
/// to the reconstructed game loop.
/// </summary>
/// <remarks>
/// Implementations must return promptly and queue expensive decoding,
/// synthesis or device work away from the game and timer threads.
/// <para>
/// The runtime owns the command lifecycle after injection. It queries
/// <see cref="IsAvailable"/> before initialization, calls
/// <see cref="PlayTune"/> only after a successful <see cref="Initialize"/>,
/// may call <see cref="Stop"/> after a playback failure, and may call
/// <see cref="Close"/> even when initialization never occurred. Lifecycle
/// commands retain their order, but <see cref="AdvanceTick"/> can arrive from
/// the timer thread while a game command is changing playback. Implementations
/// must serialize their own mutable state.
/// </para>
/// <para>
/// <see cref="Stop"/> and <see cref="Close"/> must be idempotent. A closed
/// sink may later receive a new initialization only when its implementation
/// explicitly supports another Classic run.
/// </para>
/// </remarks>
public interface IClassicAudioSink
{
	/// <summary>
	/// Indicates whether this sink can produce audible output.
	/// </summary>
	bool IsAvailable { get; }

	void Initialize();

	void PlayTune(short tune, ushort parameter);

	/// <summary>
	/// Delivers the runtime's approximately 60 Hz compatibility pulse.
	/// </summary>
	/// <remarks>
	/// The runtime may call this method from its timer thread while a game
	/// command is starting or stopping a tune. Implementations must therefore
	/// serialize their own state and return promptly. A timing-sensitive sink
	/// may use its own monotonic clock and treat this call as a health check.
	/// </remarks>
	void AdvanceTick()
	{
	}

	void Stop();

	void Close();
}

/// <summary>
/// Default sink used until a platform provides a reviewed audio backend.
/// </summary>
public sealed class NullClassicAudioSink : IClassicAudioSink
{
	private NullClassicAudioSink()
	{
	}

	public static NullClassicAudioSink Instance { get; } = new();

	public bool IsAvailable => false;

	public void Initialize()
	{
	}

	public void PlayTune(short tune, ushort parameter)
	{
	}

	public void AdvanceTick()
	{
	}

	public void Stop()
	{
	}

	public void Close()
	{
	}
}
